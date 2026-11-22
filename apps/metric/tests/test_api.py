"""test_api.py — API-Routen-Tests fuer app/main.py (k8s-Aufrufe gemockt) plus
slim_sample()/offer() aus sample.py/realtime.py. TestClient ohne `with`:
dadurch laeuft das lifespan NICHT, es startet also kein Producer-Prozess."""

import asyncio
import time

import main
import pytest
import realtime
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from sample import slim_sample


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main, "collect_state", lambda verbose=True: {
        "time": "2026-11-21T12:00:00+00:00",
        "stations": [{"name": "website", "tracks": []}],
    })
    monkeypatch.setattr(main, "_STATE_CACHE", None)
    main.BUFFER.buf.clear()
    main.BUFFER._cache.clear()
    main.SUBSCRIBERS.clear()
    c = TestClient(main.app)
    yield c
    main.BUFFER.buf.clear()
    main.BUFFER._cache.clear()
    main.SUBSCRIBERS.clear()
    main._STATE_CACHE = None


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_state_mocked(client):
    r = client.get("/state")
    assert r.status_code == 200
    assert r.json()["stations"][0]["name"] == "website"


def test_state_is_cached_for_one_second(client, monkeypatch):
    """/state serviert 1 s lang den Cache — ein Poll-Flood loest nicht pro
    Request einen K8s-Call (collect_state ~30 ms) aus."""
    calls = {"n": 0}

    def counting(verbose=True):
        calls["n"] += 1
        return {"time": "t", "stations": []}

    monkeypatch.setattr(main, "collect_state", counting)
    main._STATE_CACHE = None
    assert client.get("/state").status_code == 200
    assert client.get("/state").status_code == 200
    assert calls["n"] == 1
    # Cache abgelaufen -> neu gesammelt
    main._STATE_CACHE = (main.time.monotonic() - 2 * main._STATE_TTL_S,
                         {"time": "stale", "stations": [{"name": "stale"}]})
    r = client.get("/state")
    assert calls["n"] == 2
    assert r.json()["stations"] == []


def test_history_empty(client):
    r = client.get("/history")
    assert r.status_code == 200
    body = r.json()
    assert body["buffered"] == 0
    assert body["samples"] == []
    assert body["sample_hz"] == main.SAMPLE_HZ


def test_history_seeded_and_clamped(client):
    now_ms = time.time() * 1000
    for i in range(20):
        main.BUFFER.append({"t": now_ms - i * 1000, "s": []})
    r = client.get("/history", params={"seconds": 5, "max_points": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["buffered"] == 20
    # max_points wird auf mindestens 10 geclamped, seconds auf die Retention
    assert len(body["samples"]) == 10


def test_stream_503_when_subscribers_full(client, monkeypatch):
    monkeypatch.setattr(main, "SUBSCRIBERS",
                        {asyncio.Queue() for _ in range(main.MAX_SUBSCRIBERS)})
    r = client.get("/stream")
    assert r.status_code == 503
    assert "too many stream subscribers" in r.json()["detail"]


def test_slim_sample_shape():
    state = {
        "stations": [{
            "name": "website",
            "tracks": [
                {"pod": {"cpu_nano": 250_000_000, "mem_bytes": 1024**2,
                         "state": "running"}},
                {"pod": {"cpu_nano": None, "mem_bytes": None, "state": "entering"}},
                {"pod": None},
            ],
        }],
    }
    s = slim_sample(state)
    assert set(s.keys()) == {"t", "s"}
    st = s["s"][0]
    assert st["n"] == "website"
    assert st["c"] == 250_000_000
    assert st["m"] == 1024**2
    assert st["p"] == 2
    assert st["st"] == "entering+running"


def test_offer_drop_oldest(monkeypatch):
    monkeypatch.setattr(realtime, "DROPPED", 0)
    q = asyncio.Queue(2)  # 3.14: maxlen nur noch positional
    realtime.offer(q, "a")
    realtime.offer(q, "b")
    realtime.offer(q, "c")  # voll -> "a" wird verworfen, "c" landet drin
    assert realtime.DROPPED == 1
    assert q.get_nowait() == "b"
    assert q.get_nowait() == "c"


# --- Review Runde 2: Subscriber add/discard atomar, forwarder_loop ---

def test_stream_subscriber_added_and_discarded_on_close():
    async def run():
        main.SUBSCRIBERS.clear()
        resp = await main.api_stream()
        assert isinstance(resp, StreamingResponse)
        assert len(main.SUBSCRIBERS) == 1  # add passiert im Endpoint (unter Lock)
        it = resp.body_iterator
        hello = await it.__anext__()
        assert hello.startswith("event: hello\n")
        await it.aclose()
        assert len(main.SUBSCRIBERS) == 0  # finally in gen() discardt
        main.SUBSCRIBERS.clear()
    asyncio.run(run())


def test_stream_503_under_lock_when_full(client, monkeypatch):
    # Max-1 belegen, dann duerfen zwei "parallele" Connects nur einen durchlassen
    monkeypatch.setattr(main, "MAX_SUBSCRIBERS", 2)
    main.SUBSCRIBERS.clear()
    main.SUBSCRIBERS.add(asyncio.Queue())

    async def run():
        r1 = await main.api_stream()
        assert isinstance(r1, StreamingResponse)   # Platz 2 frei -> durch
        r2 = await main.api_stream()               # jetzt voll -> 503
        assert isinstance(r2, JSONResponse) and r2.status_code == 503
        await r1.body_iterator.aclose()
        main.SUBSCRIBERS.clear()
    asyncio.run(run())


def test_forwarder_loop_moves_sample_to_buffer_and_subscribers():
    async def run():
        main.SUBSCRIBERS.clear()
        main.BUFFER.buf.clear()
        main.BUFFER._cache.clear()
        while not realtime.INBOUND.empty():
            realtime.INBOUND.get_nowait()
        q = asyncio.Queue(10)
        main.SUBSCRIBERS.add(q)
        task = asyncio.create_task(realtime.forwarder_loop())
        await realtime.INBOUND.put({"t": 1_700_000_000_000, "s": []})
        for _ in range(50):  # Forwarder-Tick abwarten (10 ms Poll)
            if len(main.BUFFER) == 1:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert len(main.BUFFER) == 1
        frame = q.get_nowait()
        assert frame.startswith("event: sample\n")
        assert '"b":1' in frame
        main.SUBSCRIBERS.clear()
        main.BUFFER.buf.clear()
    asyncio.run(run())
