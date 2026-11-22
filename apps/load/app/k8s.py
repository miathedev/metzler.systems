"""K8s-Orchestrierung der k6-Runs: die App erstellt pro Load-Run einen
batch/v1-Job (grafana/k6, Script aus der ConfigMap LOAD_K6_CONFIGMAP) und
liest dessen Status fuer /status.

Single-State: solange ein Run-Job aktiv ist (nicht Succeeded/Failed), liefert
create_run() None -> API antwortet 409. Fertige Jobs werden beim naechsten
Trigger geloescht (TTL auf dem Job ist das Sicherheitsnetz).

RBAC (charts/load/templates/rbac.yaml): nur batch/jobs im eigenen Namespace.
"""

import json
import re
import threading
from datetime import UTC, datetime

from config import (
    LOAD_DURATION_S,
    LOAD_K6_CONFIGMAP,
    LOAD_K6_IMAGE,
    LOAD_K6_RESOURCES,
    LOAD_MAX_VUS,
    LOAD_RATE,
    LOAD_TARGET_URL,
    LOAD_VUS,
    NAMESPACE,
    OVERRIDE_DURATION_MAX_S,
    OVERRIDE_RATE_MAX,
    clamp_int,
    clamp_source,
    log,
)
from kubernetes import client, config

try:
    config.load_kube_config()
except config.ConfigException:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        # z.B. lokaler Lauf ohne Cluster: /health geht, /status meldet "error"
        pass

batch = client.BatchV1Api()
core = client.CoreV1Api()  # nur fuer pods/log (k6-Summary aus dem Job-Log)

# Label, ueber das alle Run-Jobs gefunden werden (Single-State + Status).
RUN_LABEL_SELECTOR = "app.kubernetes.io/component=load-run"
K6_UID = 12345  # USER des grafana/k6-Images

# Serialisiert check+cleanup+create in create_run(): zwei parallele POSTs
# (run_in_threadpool) duerfen nicht beide einen Run-Job anlegen. Chart hat
# replicaCount 1 — ein Prozess-Lock genuegt (bei >1 Replica brauchte es einen
# clusterweiten Lock, z.B. Lease).
_RUN_LOCK = threading.Lock()


def _labels(source: str) -> dict:
    return {
        "app.kubernetes.io/name": "load",
        "app.kubernetes.io/component": "load-run",
        "metzler.systems/load-source": source,
    }


def list_runs() -> list | None:
    """Alle Run-Jobs (neueste zuletzt). None bei API-Fehler (nie 500) —
    so kann status() "error" statt "idle" melden, wenn die K8s-API steht."""
    try:
        return batch.list_namespaced_job(
            NAMESPACE, label_selector=RUN_LABEL_SELECTOR).items
    except Exception as e:  # noqa: BLE001 - Endpoint darf nie 500 liefern
        log(f"job list failed: {e}")
        return None


def _is_active(job) -> bool:
    st = job.status
    if st is None:
        return True  # gerade erstellt, noch kein Status -> als aktiv zaehlen
    return not (st.succeeded or st.failed)


def active_run():
    """Aktiver Run-Job oder None (auch bei API-Fehler — create_run schlaegt
    dann eben beim Anlegen fehl und die API antwortet 503)."""
    for job in list_runs() or []:
        if _is_active(job):
            return job
    return None


def _job_body(duration_s: int, rate: int, source: str, signals) -> dict:
    """Job-Spec fuer einen k6-Run: Script per ConfigMap, Env aus der Config
    (duration/rate ggf. per Run ueberschrieben), activeDeadlineSeconds als
    Sicherheitsnetz (Run haelt nie laenger als duration + 120 s). Quelle und
    Human-Signals landen als Annotationen am Job (Nachvollziehbarkeit im Cluster)."""
    annotations = {
        "metzler.systems/load-source": source,
        "metzler.systems/load-duration-s": str(duration_s),
        "metzler.systems/load-rate": str(rate),
    }
    if signals:
        annotations["metzler.systems/load-signals"] = json.dumps(signals)[:1000]
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "generateName": "load-run-",
            "labels": _labels(source),
            "annotations": annotations,
        },
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 3600,
            "activeDeadlineSeconds": duration_s + 120,
            "template": {
                "metadata": {"labels": _labels(source)},
                "spec": {
                    "restartPolicy": "Never",
                    # k6 braucht keinen K8s-API-Zugriff — Token nicht mounten.
                    "automountServiceAccountToken": False,
                    "securityContext": {
                        "fsGroup": K6_UID,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [{
                        "name": "k6",
                        "image": LOAD_K6_IMAGE,
                        "command": ["k6", "run", "/scripts/loadtest.js"],
                        "env": [
                            {"name": "K6_TARGET_URL", "value": LOAD_TARGET_URL},
                            {"name": "K6_DURATION", "value": f"{duration_s}s"},
                            {"name": "K6_RATE", "value": str(rate)},
                            {"name": "K6_VUS", "value": str(LOAD_VUS)},
                            {"name": "K6_MAX_VUS", "value": str(LOAD_MAX_VUS)},
                        ],
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": K6_UID,
                            "runAsGroup": K6_UID,
                            "allowPrivilegeEscalation": False,
                            "readOnlyRootFilesystem": True,
                            "capabilities": {"drop": ["ALL"]},
                        },
                        "resources": json.loads(LOAD_K6_RESOURCES),
                        "volumeMounts": [{
                            "name": "script",
                            "mountPath": "/scripts",
                            "readOnly": True,
                        }, {
                            "name": "tmp",
                            "mountPath": "/tmp",
                        }],
                    }],
                    "volumes": [{
                        "name": "script",
                        "configMap": {"name": LOAD_K6_CONFIGMAP},
                    }, {
                        "name": "tmp",
                        "emptyDir": {},
                    }],
                },
            },
        },
    }


def create_run(source: str = "button", duration_s=None, rate=None, signals=None):
    """Erstellt den k6-Run-Job — None, wenn bereits einer aktiv ist.
    duration_s/rate sind optionale Per-Run-Overrides (geclamped).
    Lock gegen check-then-act-Race bei parallelen POSTs (siehe _RUN_LOCK)."""
    with _RUN_LOCK:
        if active_run() is not None:
            return None
        source = clamp_source(source)
        # Per-Run-Overrides auf harte Caps begrenzen (oeffentlicher, auth-loser
        # POST — Self-DoS-Schutz, siehe config.OVERRIDE_*).
        duration_s = clamp_int(duration_s, 5, OVERRIDE_DURATION_MAX_S, LOAD_DURATION_S)
        rate = clamp_int(rate, 1, OVERRIDE_RATE_MAX, LOAD_RATE)
        # fertige Jobs vom letzten Run aufraeumen (best effort)
        for job in list_runs() or []:
            try:
                batch.delete_namespaced_job(
                    job.metadata.name, NAMESPACE, propagation_policy="Foreground")
            except Exception as e:  # noqa: BLE001 - AlreadyGone ist ok
                log(f"cleanup of {job.metadata.name} failed: {e}")
        job = batch.create_namespaced_job(
            NAMESPACE, _job_body(duration_s, rate, source, signals))
        log(f"k6 run job created: {job.metadata.name} (source={source}, "
            f"{rate} rps for {duration_s}s -> {LOAD_TARGET_URL})")
        return job


def _iso(dt) -> str | None:
    return dt.astimezone(UTC).isoformat() if dt else None


# k6-Summary-Zeilen aus dem Job-Log parsen (best effort — nie 500).
_SIZE = {"B": 1, "kB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12,
         "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
_TIME = {"us": 1e-3, "ms": 1.0, "s": 1e3, "m": 60e3}


def _grab(log: str, pattern: str):
    m = re.search(pattern, log)
    return m.groups() if m else None


def parse_k6_summary(pod_log: str) -> dict | None:
    """Reine Parse-Funktion: k6-Summary-Metriken aus einem Pod-Log-String.
    None, wenn keine http_reqs-Zeile enthalten ist (Run laeuft noch oder Log
    nicht parsebar). Von k6_metrics() getrennt, damit unit-testbar."""
    # Zahlen-Gruppen mit Lookaround gehärtet: das alte [\d.]+ matcht auch
    # "1.2.3" — float("1.2.3") wuerfe ValueError und /status kaeme 500.
    # (?<!/?!)[\d.] verhindert, dass aus "1.2.3" die "1" oder "2.3" matcht.
    num = r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])"
    g = _grab(pod_log, rf"http_reqs\.+:\s+{num}(?:\s+{num}/s)?")
    if not g:
        return None
    p95 = _grab(pod_log, rf"p\(95\)={num}(us|ms|s|m)")
    failed = _grab(pod_log, rf"http_req_failed\.+:\s+{num}%")
    data = _grab(pod_log, rf"data_received\.+:\s+{num}\s*(B|kB|MB|GB|TB|KiB|MiB|GiB)")
    vus = _grab(pod_log, rf"vus_max\.+:\s+{num}") or _grab(pod_log, rf"vus\.+:\s+{num}")
    try:
        return {
            "http_reqs": round(float(g[0])),
            "rps": round(float(g[1]), 1) if g[1] else None,
            "p95_ms": round(float(p95[0]) * _TIME[p95[1]], 2) if p95 else None,
            "failed_pct": round(float(failed[0]), 3) if failed else None,
            "data_received_bytes": round(float(data[0]) * _SIZE[data[1]]) if data else None,
            "vus": round(float(vus[0])) if vus else None,
        }
    except (ValueError, TypeError, KeyError):
        # Defensiv: ein kaputtes Log darf nie den /status mit 500 schiessen.
        return None


def k6_metrics(job) -> dict | None:
    """Echte k6-Summary-Metriken aus dem Pod-Log eines Succeeded-Jobs.
    Liefert None, solange der Run laeuft oder das Log nicht parsebar ist."""
    st = job.status
    if not (st and st.succeeded):
        return None
    name = job.metadata.name
    pods = []
    for sel in (f"job-name={name}", f"batch.kubernetes.io/job-name={name}"):
        try:
            pods = core.list_namespaced_pod(NAMESPACE, label_selector=sel).items
        except Exception:  # noqa: BLE001
            pods = []
        if pods:
            break
    if not pods:
        return None
    try:
        pod_log = core.read_namespaced_pod_log(
            pods[0].metadata.name, NAMESPACE, tail_lines=300)
    except Exception as e:  # noqa: BLE001 - pods/log-RBAC oder Pod schon weg
        log(f"k6 log read failed for {name}: {e}")
        return None
    return parse_k6_summary(pod_log)


def run_summary(job) -> dict:
    """Status eines Run-Jobs: running/idle + Restlaufzeit aus startTime."""
    st = job.status
    if st is None or _is_active(job):
        state, job_state = "running", "Running" if st and st.active else "Pending"
    elif st.succeeded:
        state, job_state = "idle", "Succeeded"
    else:
        state, job_state = "idle", "Failed"
    started = st.start_time if st else None
    elapsed = (datetime.now(UTC) - started).total_seconds() if started else 0.0
    ann = job.metadata.annotations or {}
    try:
        duration_s = int(ann.get("metzler.systems/load-duration-s", LOAD_DURATION_S))
        rate = int(ann.get("metzler.systems/load-rate", LOAD_RATE))
    except (TypeError, ValueError):
        # Kaputte Annotation darf nie den /status mit 500 schiessen —
        # auf die Config-Defaults zurueckfallen.
        duration_s, rate = LOAD_DURATION_S, LOAD_RATE
    source = (job.metadata.labels or {}).get("metzler.systems/load-source", "?")
    return {
        "state": state,
        "job": job.metadata.name,
        "job_state": job_state,
        "source": source,
        # "target" (interne Service-URL) und "k6_image" bleiben intern —
        # der oeffentliche /status soll keine Cluster-Internals leaken.
        "duration_s": duration_s,
        "rate": rate,
        "vus": LOAD_VUS,
        "max_vus": LOAD_MAX_VUS,
        "started_at": _iso(started),
        "remaining_s": round(max(0.0, duration_s - elapsed), 1),
        "active_pods": st.active if st else 0,
        "metrics": k6_metrics(job),
    }


def status() -> dict:
    """Gesamtstatus: Config + aktueller/letzter Run (nie 500). Oeffentlich —
    interne Felder (Ziel-URL, Image) werden nicht mit ausgegeben."""
    cfg = {
        "duration_s": LOAD_DURATION_S,
        "rate": LOAD_RATE,
        "vus": LOAD_VUS,
        "max_vus": LOAD_MAX_VUS,
    }
    runs = list_runs()
    if runs is None:
        # K8s-API nicht erreichbar — "error" statt "idle" melden, sonst taeuscht
        # der Status einen ruhenden Betrieb vor.
        return {"state": "error", **cfg, "job": None, "job_state": None,
                "source": None, "remaining_s": 0.0, "last_run": None}
    if not runs:
        return {"state": "idle", **cfg, "job": None, "job_state": None,
                "source": None, "remaining_s": 0.0, "last_run": None}
    job = max(runs, key=lambda j: j.metadata.creation_timestamp
              or datetime.min.replace(tzinfo=UTC))
    cur = run_summary(job)
    return {**cur, "last_run": cur if cur["state"] != "running" else None}
