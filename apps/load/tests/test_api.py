"""API-Tests fuer app/main.py — k8s-Aufrufe gemockt, echter FastAPI-TestClient."""

import json
from types import SimpleNamespace

import main
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main, "_TRIGGERS", {})
    monkeypatch.setattr(main, "_STATUS_CACHE", None)
    calls = {}

    def fake_create_run(source="button", duration_s=None, rate=None, signals=None):
        calls["args"] = {"source": source, "duration_s": duration_s,
                         "rate": rate, "signals": signals}
        if calls.get("mode") == "busy":
            return None
        return SimpleNamespace(metadata=SimpleNamespace(name="load-run-abc"))

    def fake_status():
        # Mock haelt sich an den echten Shape von k8s.status() — interne Felder
        # wie "target" duerfen oeffentlich nie vorkommen (Gegentest in test_k6s).
        return {"state": "running", "job": "load-run-abc", "rate": 1000,
                "duration_s": 300}

    monkeypatch.setattr(main, "create_run", fake_create_run)
    monkeypatch.setattr(main, "status", fake_status)
    with TestClient(main.app) as c:
        c.fake_calls = calls
        yield c


def test_trigger_ok(client):
    r = client.post("/", params={"source": "cli", "rate": 500})
    assert r.status_code == 200
    assert r.json()["state"] == "running"
    assert client.fake_calls["args"]["rate"] == 500


def test_status_endpoints_use_one_second_cache(client, monkeypatch):
    """GET /status und GET / servieren den 1-s-Cache — ein Flood auf dem
    ungedrosselten Prefix-Pfad loest nicht pro Poll einen K8s-Call aus."""
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return {"state": "idle", "job": None}

    monkeypatch.setattr(main, "status", counting)
    main._STATUS_CACHE = None
    assert client.get("/status").json()["state"] == "idle"
    assert client.get("/").json()["state"] == "idle"
    assert calls["n"] == 1


def test_trigger_409_single_state(client):
    client.fake_calls["mode"] = "busy"
    r = client.post("/")
    assert r.status_code == 409
    assert r.json()["detail"]["message"] == "load already running"


def test_origin_foreign_forbidden(client):
    r = client.post("/", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_origin_own_allowed(client):
    r = client.post("/", headers={"Origin": "https://metzler.systems"})
    assert r.status_code == 200


def test_body_too_large_413(client):
    r = client.post("/", content=b"x" * (main.MAX_BODY_BYTES + 1),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_body_invalid_json_422(client):
    r = client.post("/", content=b"{not json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_signals_body_lands_in_create(client):
    r = client.post("/", content=json.dumps({"signals": {"webdriver": False}}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert client.fake_calls["args"]["signals"] == {"webdriver": False}


def test_rate_limit_429(client, monkeypatch):
    monkeypatch.setattr(main, "TRIGGER_MAX_PER_WINDOW", 2)
    assert client.post("/").status_code == 200   # 1. zaehlt
    assert client.post("/").status_code == 200   # 2. zaehlt
    assert client.post("/").status_code == 429   # 3. ueber Limit


def test_create_failure_is_503_not_500(client, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("k8s ApiException: quota exceeded")

    monkeypatch.setattr(main, "create_run", boom)
    r = client.post("/")
    assert r.status_code == 503
    assert "quota" not in r.text  # keine Internals leaken


# --- Review Runde 2: Mid-Stream-413, invalid Content-Length, Eviction ---

def test_body_too_large_mid_stream_413(client):
    # chunked (kein Content-Length): der Stream-Read muss mitten drin 413 liefern
    def gen():
        yield b"x" * 9000
        yield b"x" * 9000   # > 16 kB im zweiten Chunk
    r = client.post("/", content=gen(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_invalid_content_length_400(client):
    r = client.post("/", content=b"{}", headers={"Content-Length": "not-a-number"})
    assert r.status_code == 400


def test_throttled_evicts_oldest_ip(monkeypatch):
    monkeypatch.setattr(main, "_TRIGGERS", {})
    monkeypatch.setattr(main, "_TRIGGER_MAX_IPS", 3)
    monkeypatch.setattr(main, "TRIGGER_MAX_PER_WINDOW", 1000)
    for i in range(5):
        assert main._throttled(f"10.0.0.{i}") is False
    # nach 5 IPs bei Cap 3 sind die aeltesten evicten
    assert len(main._TRIGGERS) == 3
    assert "10.0.0.0" not in main._TRIGGERS
    assert "10.0.0.4" in main._TRIGGERS
