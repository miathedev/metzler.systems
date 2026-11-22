"""FastAPI-App "load" — orchestriert k6 als Kubernetes-Job.

Oeffentlich (hinter Traefik, StripPrefix /api/load):
  POST /api/load/         k6-Run-Job starten (Default 5 min gegen die website),
                          409 wenn bereits einer aktiv (Single-State)
  GET  /api/load/status   idle/running/error + Job-State, Restlaufzeit, Rate
  GET  /api/load/health   Liveness/Readiness

Hardening des oeffentlichen, auth-losen POST / (Self-DoS- und CSRF-Schutz):
Origin-Check (403), Body-Limit 16 kB (413), kaputtes JSON (422), In-App
Rate-Limit pro Client-IP (429), Per-Run-Overrides auf harte Caps clamped
(config.OVERRIDE_*), K8s-Fehler beim Job-Anlegen -> 503 statt 500 mit
Internals. Blocking K8s-Calls laufen via run_in_threadpool; /health laeuft
async auf dem Event-Loop und /status serviert einen 1-s-Cache — ein Flood
auf den ( fuer Status-Polls bewusst ungedrosselten) Prefix-Pfad kann so
weder den Threadpool noch die Liveness auslasten.

Die eigentliche Last erzeugt ein k6-Job (grafana/k6, Script aus der ConfigMap
des Charts) — die App selbst feuert keine Requests. RBAC dafuer: nur
batch/jobs + pods/log im eigenen Namespace (charts/load/templates/rbac.yaml).
Ob der HPA der website skaliert hat, liest die metric-App (Pods-Serie im
Live-Graph).

OpenAPI-/Doku-Endpunkte sind deaktiviert: die API haengt oeffentlich am Netz
und soll keine Doku exponieren.
"""

import json
import time

from config import (
    ALLOWED_ORIGINS,
    MAX_BODY_BYTES,
    TRIGGER_MAX_PER_WINDOW,
    TRIGGER_WINDOW_S,
    log,
)
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from k8s import create_run, status

app = FastAPI(title="load", docs_url=None, redoc_url=None, openapi_url=None)

# Sliding-Window Rate-Limit fuer POST /: client-ip -> [start-timestamps]
_TRIGGERS: dict[str, list[float]] = {}
# Harter Cap fuer die IP-Tabelle: bei XFF-Spoofing mit wechselnden Werten darf
# _TRIGGERS nicht unbegrenzt wachsen (waere ein Memory-DoS auf dem 128Mi-Pod).
_TRIGGER_MAX_IPS = 10_000

# 1-s-Cache fuer /status: das Frontend pollt alle 2 s, aber der Prefix-Ingress
# traegt bewusst kein RateLimit — ein Flood auf GET /status darf nicht jeden
# Poll einen K8s-Call (list_namespaced_job) im Threadpool ausloesen, sonst
# waere der Pool (40 Tokens) irgendwann voll.
_STATUS_CACHE: tuple[float, dict] | None = None
_STATUS_TTL_S = 1.0


async def _status_cached() -> dict:
    """status() mit kurzem Cache — begrenzt die K8s-Calls auf 1/s global."""
    global _STATUS_CACHE
    now = time.monotonic()
    if _STATUS_CACHE is not None and now - _STATUS_CACHE[0] < _STATUS_TTL_S:
        return _STATUS_CACHE[1]
    st = await run_in_threadpool(status)
    _STATUS_CACHE = (now, st)
    return st


def _client_ip(request: Request) -> str:
    # Hinter Traefik steht die echte Client-IP RECHTS in X-Forwarded-For
    # (Traefik haengt sie an); links stehen client-gesetzte Werte, die sich
    # spoofen lassen und das Rate-Limit umgehen wuerden. Lokal (kein Proxy)
    # zaehlt der direkte Peer.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _origin_ok(request: Request) -> bool:
    """CSRF-Schutz: Browser senden bei POST immer einen Origin-Header. Fehlt
    er (curl/CLI), ist es kein Cross-Site-POST aus einem fremden Tab und der
    Request bleibt erlaubt."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    return origin.rstrip("/") in ALLOWED_ORIGINS


def _throttled(ip: str) -> bool:
    """True, wenn die IP das Limit schon erreicht hat. Jeder POST zaehlt —
    auch 409/429-er — damit schnelles Re-Proben gleich mitgebremst wird."""
    now = time.time()
    window = [t for t in _TRIGGERS.get(ip, []) if now - t < TRIGGER_WINDOW_S]
    if len(window) >= TRIGGER_MAX_PER_WINDOW:
        _TRIGGERS[ip] = window
        return True
    window.append(now)
    _TRIGGERS[ip] = window
    if len(_TRIGGERS) > _TRIGGER_MAX_IPS:
        # aeltesten Eintrag evicten (Spoofing-Schutz gegen unbegrenztes Wachstum)
        oldest = min(_TRIGGERS, key=lambda k: _TRIGGERS[k][-1])
        del _TRIGGERS[oldest]
    return False


@app.get("/health")
async def api_health():
    """Liveness/Readiness — async auf dem Event-Loop (ein sync def wuerde den
    Threadpool mit den blockierenden K8s-Calls teilen und bei Vollauf die
    Liveness blockieren), ohne K8s-API-Abhaengigkeit, immer ok."""
    return {"status": "ok"}


@app.post("/")
async def api_trigger(request: Request, source: str = "button",
                      duration_s: int | None = None, rate: int | None = None):
    """Startet einen k6-Run-Job. Single-State: laeuft bereits einer, gibt es
    409 mit dem aktuellen Status — es wird kein zweiter Job gestartet.

    Query-Params: source=button|visitor|cli, optionale Overrides duration_s/rate
    (auf harte Caps clamped, siehe config.OVERRIDE_*). Optionaler JSON-Body
    {"signals": {...}} — Human-Signals des Besuchers, landen als Annotation
    am Job. Limits: 403 fremder Origin, 413 Body > 16 kB, 422 kaputtes JSON,
    429 Rate-Limit, 503 wenn der Job nicht angelegt werden kann."""
    if not _origin_ok(request):
        raise HTTPException(status_code=403,
                            detail={"message": "forbidden origin"})
    if _throttled(_client_ip(request)):
        raise HTTPException(status_code=429, detail={
            "message": f"too many trigger attempts: max {TRIGGER_MAX_PER_WINDOW} "
                       f"per {TRIGGER_WINDOW_S}s per IP"})
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail={
                    "message": f"body too large: max {MAX_BODY_BYTES} bytes"})
        except ValueError:
            raise HTTPException(status_code=400,
                                detail={"message": "invalid content-length"}) from None
    # Body streamend lesen und dabei deckeln: ein unbegrenzter Read (chunked
    # ohne Content-Length) vor dem Limit waere ein Memory-DoS auf dem 128Mi-Pod.
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail={
                "message": f"body too large: max {MAX_BODY_BYTES} bytes"})
    signals = None
    if raw:
        try:
            body = json.loads(raw)
        except (ValueError, RecursionError):
            raise HTTPException(status_code=422,
                                detail={"message": "body is not valid JSON"}) from None
        if isinstance(body, dict) and isinstance(body.get("signals"), dict):
            signals = body["signals"]
    try:
        # Blocking K8s-Calls (list/create) duerfen den Event-Loop nicht
        # blockieren — deshalb im Threadpool.
        job = await run_in_threadpool(
            create_run, source=source, duration_s=duration_s, rate=rate,
            signals=signals)
    except Exception as e:  # noqa: BLE001 - ApiException/Quota/Admission: nie 500 mit Internals
        log(f"create_run failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=503, detail={
            "message": "could not create load-run job"}) from None
    if job is None:
        st = await _status_cached()
        raise HTTPException(status_code=409,
                            detail={"message": "load already running",
                                    "status": st})
    return await _status_cached()


@app.get("/")
async def api_status_root():
    """GET /api/load/ -> gleicher Status wie /status (Bequemlichkeit)."""
    return await _status_cached()


@app.get("/status")
async def api_status():
    """Aktueller Load-Status: state idle/running/error, Job-State, Restlaufzeit."""
    return await _status_cached()
