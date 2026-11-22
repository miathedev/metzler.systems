"""FastAPI-App "metrics" — nur noch Wiring: Routen hängen an den Modulen

- config:    Env-Konfiguration (SAMPLE_HZ, RETENTION_MIN, NAMESPACE)
- k8s:       K8s-Client + collect_state()
- buffer:    RAM-Ringbuffer (SampleBuffer)
- realtime:  Producer-Prozess + SSE-Fan-out (BUFFER, SUBSCRIBERS, lifespan)
- sample:    slim_sample() (im Producer-Prozess, siehe realtime)

OpenAPI-/Doku-Endpunkte sind deaktiviert: die API hängt öffentlich am Netz
(metzler.systems/api/metrics) und soll keine Doku exponieren.
"""

import asyncio
import json
import time

from config import NAMESPACE, RETENTION_MIN, SAMPLE_HZ
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse
from k8s import collect_state
from realtime import (
    BUFFER,
    MAX_SUBSCRIBERS,
    QUEUE_MAXLEN,
    SUBSCRIBERS,
    SUBSCRIBERS_LOCK,
    lifespan,
)

app = FastAPI(title="metrics", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)


# 1-s-Cache fuer /state: der Pfad ist zwar per Traefik-RateLimit gedeckelt,
# aber ueber viele Client-IPs umgehbar — der Cache begrenzt die K8s-Calls
# (collect_state ~30 ms) auf 1/s, egal wie viele Clients pollen.
_STATE_CACHE: tuple[float, dict] | None = None
_STATE_TTL_S = 1.0


async def _state_cached() -> dict:
    global _STATE_CACHE
    now = time.monotonic()
    if _STATE_CACHE is not None and now - _STATE_CACHE[0] < _STATE_TTL_S:
        return _STATE_CACHE[1]
    st = await run_in_threadpool(collect_state)
    _STATE_CACHE = (now, st)
    return st


@app.get("/health")
async def api_health():
    """Liveness/Readiness — async auf dem Event-Loop (ein sync def wuerde den
    Threadpool mit den blockierenden K8s-Calls teilen), bewusst ohne
    K8s-API-Abhängigkeiten, damit der Pod auch bei stehender metrics.k8s.io-API
    (metrics-server nicht Ready) Ready bleibt."""
    return {"status": "ok"}


@app.get("/state")
async def api_state():
    """Snapshot: Pro Deployment eine Track pro Replica (mit 1-s-Cache)."""
    return await _state_cached()


@app.get("/history")
async def api_history(seconds: float = 0.0, max_points: int = 3000):
    """RAM-Cache als JSON. seconds > 0 begrenzt auf die juengsten seconds
    (volle Aufloesung), aeltere Samples werden gestrideet (max_points).
    Direkt als JSON-String serviert — ohne json.loads-Roundtrip des gecachten
    Dumps (der Roundtrip wuerde den Speicherbedarf kurz verdoppeln).

    Bewusst `async def` (statt sync/Threadpool): dump_cached() iteriert die
    deque, die der forwarder_loop im selben Event-Loop per append() mutiert.
    Sync im Threadpool gab es deshalb eine Race ("deque mutated during
    iteration" -> 500). Async laeuft der Dump atomar gegenueber dem Loop."""
    seconds = min(max(seconds, 0.0), float(BUFFER.retention_seconds))
    max_points = min(max(int(max_points), 10), 60000)
    body = (
        f'{{"sample_hz":{SAMPLE_HZ},"retention_minutes":{RETENTION_MIN},'
        f'"buffered":{len(BUFFER)},"subscribers":{len(SUBSCRIBERS)},'
        f'"samples":{BUFFER.dump_cached(seconds or None, max_points)}}}'
    )
    return Response(content=body, media_type="application/json")


@app.get("/stream")
async def api_stream(window_seconds: float = 60.0, max_points: int = 3000):
    """SSE-Stream: event hello (Config), event history (RAM-Cache), dann pro
    Sample event sample (bis zu SAMPLE_HZ/s, mit "b" = Buffer-Fuellstand fuer
    live aktualisierte Cache-Anzeigen). Ping-Kommentar alle 15 s, wenn kein
    Sample anfaellt. X-Accel-Buffering: no gegen puffernde Proxies."""
    window_seconds = min(max(window_seconds, 1.0), float(BUFFER.retention_seconds))
    max_points = min(max(int(max_points), 10), 60000)
    # Check+Add atomar unter Lock — sonst ueberschiessen N parallele Connects
    # das Limit um N (Race zwischen Endpoint-Check und SUBSCRIBERS.add in gen).
    async with SUBSCRIBERS_LOCK:
        if len(SUBSCRIBERS) >= MAX_SUBSCRIBERS:
            return JSONResponse(
                {"detail": f"too many stream subscribers (max {MAX_SUBSCRIBERS})"},
                status_code=503)
        # Begrenzte Queue: langsame Clients verlieren bei Vollauf aelteste
        # Frames (drop-oldest im Producer), statt RAM zu akkumulieren.
        # 3.14: maxlen nur noch positional (Attribut heisst maxsize)
        q: asyncio.Queue = asyncio.Queue(QUEUE_MAXLEN)
        SUBSCRIBERS.add(q)

    async def gen():
        try:
            hello = {"sample_hz": SAMPLE_HZ, "retention_minutes": RETENTION_MIN,
                     "namespace": NAMESPACE, "buffered": len(BUFFER),
                     "max_samples": BUFFER.maxlen,
                     "subscribers": len(SUBSCRIBERS),
                     "queue_maxlen": QUEUE_MAXLEN}
            yield f"event: hello\ndata: {json.dumps(hello)}\n\n"
            yield (f"event: history\n"
                   f"data: {{\"samples\":{BUFFER.dump_cached(window_seconds, max_points)}}}\n\n")
            while True:
                try:
                    # fertiger SSE-Frame kommt direkt aus dem Producer
                    batch = await asyncio.wait_for(q.get(), timeout=15.0)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                # Batching: alle bis dahin angefallenen Frames auf einen
                # Schlag mitnehmen (ein Wakeup + ein Write statt vieler).
                # Die SSE-Bytes bleiben identisch, nur gebündelt.
                while True:
                    try:
                        batch += q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                yield batch
        finally:
            SUBSCRIBERS.discard(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
