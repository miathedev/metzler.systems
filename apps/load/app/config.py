"""Zentrale Konfiguration: Env-Variablen (geclamped) + Logging + Konstanten."""

import os
from datetime import UTC, datetime

# Namespace, in dem die k6-Run-Jobs erstellt werden (gleichzeitig der Namespace
# des Ziels website). Im Deployment via Downward-API injiziert (POD_NAMESPACE,
# siehe charts/load/templates/deployment.yaml) — ein hartkodierter Wert wuerde
# in einem anderen Release-Namespace falsch liegen.
NAMESPACE = os.environ.get("POD_NAMESPACE", "") or "website"


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, "") or default)
    except ValueError:
        v = default
    return min(hi, max(lo, v))


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, "") or default


def _env_origins(raw: str) -> frozenset:
    """Komma-getrennte Origin-Liste parsen (leer -> Default, trailing / egal)."""
    return frozenset(o.strip().rstrip("/") for o in raw.split(",") if o.strip())


# Ziel des k6-Loads: der Website-Service im selben Namespace. Oeffentlich
# haengt die App an /api/load (StripPrefix), intern "/", "/status", "/health".
LOAD_TARGET_URL = _env_str("LOAD_TARGET_URL", "http://website:8080/")
# Dauer eines Load-Runs: 5 Minuten (Default), clamp 5 s .. 1 h.
LOAD_DURATION_S = _env_int("LOAD_DURATION_S", 300, 5, 3600)
# k6-Szenario (constant-arrival-rate): Ziel-Rate in Requests/s und VU-Pools.
LOAD_RATE = _env_int("LOAD_RATE", 1000, 1, 100000)
LOAD_VUS = _env_int("LOAD_VUS", 100, 1, 2000)
LOAD_MAX_VUS = _env_int("LOAD_MAX_VUS", 600, 1, 5000)
# k6-Job: Image, Script-ConfigMap und Ressourcen kommen aus dem Chart
# (values.k6.* -> env im Deployment).
LOAD_K6_IMAGE = _env_str("LOAD_K6_IMAGE", "grafana/k6:2.4.0")
LOAD_K6_CONFIGMAP = _env_str("LOAD_K6_CONFIGMAP", "load-k6")
LOAD_K6_RESOURCES = _env_str(
    "LOAD_K6_RESOURCES",
    '{"requests":{"cpu":"100m","memory":"128Mi"},'
    '"limits":{"cpu":"1000m","memory":"512Mi"}}',
)

# --- Harte Limits fuer den oeffentlichen, auth-losen POST / -------------------
# Self-DoS-Schutz: ein einzelner anonymer POST darf die eigene Site nicht mit
# 100k rps fuer 1 h beschiessen. Per-Run-Overrides (Query-Params) werden auf
# diese Caps clamped; die Env-Defaults (LOAD_RATE/LOAD_DURATION_S) gelten fuer
# Button/CLI und duerfen vom Operator bewusst hoeher gesetzt werden.
OVERRIDE_DURATION_MAX_S = 600  # max 10 min pro Per-Run-Override
OVERRIDE_RATE_MAX = 2000       # max 2000 rps pro Per-Run-Override
# In-App Rate-Limit fuer POST / (pro Client-IP, Sliding Window): mehr als
# TRIGGER_MAX_PER_WINDOW Starts innerhalb von TRIGGER_WINDOW_S -> 429.
TRIGGER_WINDOW_S = 600
TRIGGER_MAX_PER_WINDOW = 3
# Max. Request-Body (signals-JSON) — gegen Memory-DoS des 128Mi-Pods.
MAX_BODY_BYTES = 16 * 1024
# CSRF-Schutz: Browser senden bei POST immer einen Origin-Header. Ist er
# gesetzt, muss er einer der erlaubten Origins entsprechen (curl/CLI ohne
# Origin-Header bleiben erlaubt). Dev-Cluster antwortet auf einem Port
# (https://metzler.systems:8443) und kommt dort per LOAD_ALLOWED_ORIGINS dazu.
ALLOWED_ORIGINS = _env_origins(
    os.environ.get("LOAD_ALLOWED_ORIGINS", "") or "https://metzler.systems")


def clamp_int(v, lo: int, hi: int, default: int) -> int:
    """Per-Run-Override (Query-Param) clampen — None -> Default."""
    if v is None:
        return default
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v))


def clamp_source(source: str | None) -> str:
    return source if source in ("button", "visitor", "cli") else "button"


def log(msg: str) -> None:
    print(f"[{datetime.now(UTC).isoformat()}] {msg}", flush=True)
