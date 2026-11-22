"""K8s-Zugriff: Client-Init, Quantity-Parsing und collect_state().

collect_state() ist die teuerste Operation des Dienstes (~30 ms pro Tick:
K8s-HTTP-Calls + JSON-Parsing der python-client-Lib) und wird deshalb nur vom
Producer-Prozess in realtime.py aufgerufen — nie aus dem Server-Event-Loop.
"""

from datetime import UTC, datetime

from config import NAMESPACE, log
from kubernetes import client, config

try:
    config.load_kube_config()
except config.ConfigException:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        # z.B. lokaler Lauf ohne Cluster: /health geht, /state meldet "error"
        pass

core = client.CoreV1Api()
apps_api = client.AppsV1Api()
custom = client.CustomObjectsApi()


def pod_metrics() -> list[dict]:
    raw = custom.list_namespaced_custom_object(
        "metrics.k8s.io", "v1beta1", NAMESPACE, "pods"
    )
    return [
        {
            "namespace": i["metadata"]["namespace"],
            "name": i["metadata"]["name"],
            "containers": [
                {"cpu": c["usage"]["cpu"], "memory": c["usage"]["memory"]}
                for c in i["containers"]
            ],
        }
        for i in raw["items"]
    ]


def parse_quantity(s: str, suffixes: dict[str, int], plain_mult: int = 1) -> int:
    """K8s-Quantity ('250m', '512Mi', '2') in die Basiseinheit umrechnen.

    Suffixe werden in Dict-Reihenfolge geprueft (binaer vor dezimal, z. B.
    'Ki' vor 'K'); eine reine Zahl wird mit plain_mult multipliziert.
    """
    for suffix, mult in suffixes.items():
        if s.endswith(suffix):
            return int(float(s[: -len(suffix)]) * mult)
    return int(float(s) * plain_mult)


def cpu_to_nano(s: str) -> int:
    """CPU-Quantity ('296384584n', '250m', '2') in Nanocores."""
    return parse_quantity(s, {"n": 1, "u": 1_000, "m": 1_000_000},
                          plain_mult=1_000_000_000)


def mem_to_bytes(s: str) -> int:
    """Memory-Quantity ('6408628Ki', '1Gi', '512Mi') in Bytes."""
    return parse_quantity(s, {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3,
                              "K": 1_000, "M": 1_000**2, "G": 1_000**3})


def pod_info(p, metrics_map: dict) -> dict:
    phase = p.status.phase or "Unknown"
    reason = p.status.reason
    for cs in p.status.container_statuses or []:
        if cs.state and cs.state.waiting:
            reason = reason or cs.state.waiting.reason
    deleting = p.metadata.deletion_timestamp is not None
    if phase in ("Succeeded", "Failed") or deleting:
        state = "leaving"
    elif phase == "Pending":
        state = "entering"
    else:
        state = "running"
    usage = metrics_map.get((p.metadata.namespace, p.metadata.name), {})
    return {
        "uid": p.metadata.uid,
        "name": p.metadata.name,
        "phase": phase,
        "reason": reason,
        "state": state,
        "cpu_nano": usage.get("cpu_nano"),
        "mem_bytes": usage.get("mem_bytes"),
    }


def collect_state(verbose: bool = True) -> dict:
    """Snapshot des Namespace: pro Deployment eine Track pro Replica, Pods
    nach Alter sortiert.

    Fehler an einzelnen K8s-Calls werden geloggt und fuehren zu einem
    Teil-Resultat (bzw. "error"-Feld), nie zu einem 500. verbose=False fuer
    den Sampler (sonst 1 Logzeile pro Sample)."""
    out: dict = {"time": datetime.now(UTC).isoformat(), "stations": []}
    metrics_map: dict[tuple[str, str], dict] = {}
    try:
        for pm in pod_metrics():
            metrics_map[(pm["namespace"], pm["name"])] = {
                "cpu_nano": sum(cpu_to_nano(c["cpu"]) for c in pm["containers"]),
                "mem_bytes": sum(mem_to_bytes(c["memory"]) for c in pm["containers"]),
            }
    except Exception as e:  # noqa: BLE001 - K8s-Client wirft ApiException, URLError, ...; Endpoint darf nie 500 liefern
        # metrics.k8s.io nicht verfügbar (z.B. metrics-server noch nicht Ready):
        # State ohne CPU/Mem ausliefern statt den ganzen Endpoint mit 500.
        log(f"metrics API unavailable ({e}), cpu/mem omitted")

    try:
        stations = []
        for d in sorted(
            apps_api.list_namespaced_deployment(NAMESPACE).items,
            key=lambda d: d.metadata.name,
        ):
            ns = d.metadata.namespace
            sel = d.spec.selector.match_labels or {}
            label_selector = ",".join(f"{k}={v}" for k, v in sel.items())
            pods = core.list_namespaced_pod(ns, label_selector=label_selector).items
            pods.sort(key=lambda p: p.metadata.creation_timestamp
                     or datetime.min.replace(tzinfo=UTC))
            replicas = d.spec.replicas or 0
            tracks = []
            for i in range(max(replicas, len(pods))):
                pod = pods[i] if i < len(pods) else None
                tracks.append({"index": i, "pod": pod_info(pod, metrics_map) if pod else None})
            stations.append({"uid": d.metadata.uid, "namespace": ns, "name": d.metadata.name,
                             "tracks": tracks})
        out["stations"] = stations
        running = sum(1 for s in stations for t in s["tracks"]
                      if t["pod"] and t["pod"]["state"] == "running")
        if verbose:
            log(f"yard state: {len(stations)} deployments, {running} running pods")
    except Exception as e:  # noqa: BLE001 - siehe oben: Teil-Resultat statt 500
        log(f"state collection failed: {e}")
        # Keine internen Fehlerdetails oeffentlich ausliefern (der Endpoint
        # haengt am Netz) — generischer Marker, Details stehen im Pod-Log.
        out["error"] = "state collection failed"
    return out
