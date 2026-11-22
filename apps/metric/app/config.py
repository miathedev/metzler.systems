"""Zentrale Konfiguration: Env-Variablen (geclamped) + Logging + Konstanten."""

import os
from datetime import UTC, datetime

# Nur Metriken dieses Namespace veröffentlichen. Im Deployment via
# Downward-API injiziert (POD_NAMESPACE, siehe charts/metric/templates/
# deployment.yaml) — ein hartkodierter Wert wuerde in einem anderen
# Release-Namespace falsch liegen.
NAMESPACE = os.environ.get("POD_NAMESPACE", "") or "website"


def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        v = float(os.environ.get(name, "") or default)
    except ValueError:
        v = default
    return min(hi, max(lo, v))


SAMPLE_HZ = _env_float("METRIC_SAMPLE_HZ", 10.0, 1.0, 30.0)
# Retention clamp 240 min (statt 1440): zusammen mit MAX_SAMPLES_CAP bleibt der
# RAM-Ringbuffer unter dem Container-Limit (128Mi prod) — 1440 min x 30 Hz
# waeren ~2,6 Mio Samples (~500 MB) und wuerden den Pod OOM-killen.
RETENTION_MIN = int(_env_float("METRIC_RETENTION_MINUTES", 30.0, 1.0, 240.0))
# Harter Cap fuer die Buffer-Groesse, unabhaengig von den Env-Werten
# (~200k Samples a ~150-300 B = ~30-60 MB RAM).
MAX_SAMPLES_CAP = 200_000


def log(msg: str) -> None:
    print(f"[{datetime.now(UTC).isoformat()}] {msg}", flush=True)
