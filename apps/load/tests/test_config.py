"""Unit-Tests fuer config.py — Clamps und harte Override-Caps."""

from config import (
    ALLOWED_ORIGINS,
    OVERRIDE_DURATION_MAX_S,
    OVERRIDE_RATE_MAX,
    _env_origins,
    clamp_int,
    clamp_source,
)


def test_clamp_int_bounds():
    assert clamp_int(None, 5, 600, 300) == 300      # None -> Default
    assert clamp_int(1, 5, 600, 300) == 5            # unter lo -> lo
    assert clamp_int(99999, 5, 600, 300) == 600      # ueber hi -> hi
    assert clamp_int("abc", 5, 600, 300) == 300      # kaputt -> Default
    assert clamp_int("42", 5, 600, 300) == 42


def test_clamp_source_whitelist():
    # source landet als K8s-LABEL-Wert am Job — nur Whitelist erlaubt
    assert clamp_source("button") == "button"
    assert clamp_source("visitor") == "visitor"
    assert clamp_source("cli") == "cli"
    assert clamp_source("evil'; drop table") == "button"
    assert clamp_source(None) == "button"


def test_override_caps_sind_hart():
    # Self-DoS-Schutz des oeffentlichen POST: harte Obergrenzen
    assert OVERRIDE_RATE_MAX <= 2000
    assert OVERRIDE_DURATION_MAX_S <= 600


def test_env_origins_parsing():
    assert _env_origins("https://metzler.systems") == {"https://metzler.systems"}
    # Dev-Port und trailing slash duerfen mit rein, Leerzeichen egal
    assert _env_origins(" https://metzler.systems:8443 , https://metzler.systems/ ") == {
        "https://metzler.systems:8443", "https://metzler.systems"}
    assert _env_origins("") == frozenset()


def test_allowed_origins_default_prod():
    # ohne Env-Override (Testlauf) gilt der Prod-Origin
    assert ALLOWED_ORIGINS == frozenset({"https://metzler.systems"})
