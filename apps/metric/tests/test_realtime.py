"""test_realtime.py — Producer/Pipe-Pfad von realtime.py: producer_loop
(sendet slim_sample, stirbt bei BrokenPipe, ueberlebt Sample-Fehler) und
_pipe_reader (foerdert bis EOF in die INBOUND-Queue). forwarder_loop, offer()
und das hello-Event von gen() stehen in test_api.py; hier das Sample-Event."""

import asyncio
from types import SimpleNamespace

import main
import realtime


def _fake_time(monkeypatch):
    """realtime.time lokal ersetzen (monotonic echt, sleep no-op), ohne das
    globale time-Modul anzufassen — sonst wuerde der Loop in Tests endlos
    weiterlaufen."""
    import time as real_time
    monkeypatch.setattr(realtime, "time",
                        SimpleNamespace(monotonic=real_time.monotonic,
                                        sleep=lambda s: None))


def test_producer_loop_sends_slim_sample_then_dies_on_broken_pipe(monkeypatch):
    sent = []

    class Conn:
        def send(self, obj):
            sent.append(obj)
            raise BrokenPipeError  # Server weg -> Loop kehrt zurueck

    monkeypatch.setattr(realtime, "collect_state",
                        lambda verbose=True: {"time": "t", "stations": []})
    _fake_time(monkeypatch)
    realtime.producer_loop(Conn())
    assert len(sent) == 1
    assert set(sent[0].keys()) == {"t", "s"}  # slim_sample-Shape


def test_producer_loop_survives_sample_error(monkeypatch):
    """Ein fehlerhaftes collect_state wird geloggt, der Producer lebt weiter
    und sendet das naechste Sample (stirbt erst am BrokenPipe)."""
    calls = {"n": 0}

    def flaky(verbose=True):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {"time": "t", "stations": []}

    class Conn:
        def send(self, obj):
            raise BrokenPipeError

    monkeypatch.setattr(realtime, "collect_state", flaky)
    _fake_time(monkeypatch)
    realtime.producer_loop(Conn())
    assert calls["n"] == 2  # Fehler + ein erfolgreiches Sample


def test_pipe_reader_forwards_samples_until_eof():
    async def run():
        loop = asyncio.get_running_loop()
        q = asyncio.Queue(10)

        class Conn:
            def __init__(self):
                self.calls = 0

            def recv(self):
                self.calls += 1
                if self.calls == 1:
                    return {"t": 1, "s": []}
                raise EOFError  # Pipe zu -> Reader kehrt zurueck

        conn = Conn()
        realtime._pipe_reader(conn, loop, q)  # blockierend, endet bei EOFError
        assert conn.calls == 2
        await asyncio.sleep(0)  # call_soon_threadsafe-Callback ausfuehren lassen
        assert q.get_nowait() == {"t": 1, "s": []}

    asyncio.run(run())


def test_stream_yields_sample_frame_from_subscriber_queue():
    """gen(): nach hello+history landet ein Producer-Frame im Stream."""
    async def run():
        main.SUBSCRIBERS.clear()
        resp = await main.api_stream()
        it = resp.body_iterator
        assert (await it.__anext__()).startswith("event: hello\n")
        assert (await it.__anext__()).startswith("event: history\n")
        q = next(iter(main.SUBSCRIBERS))
        q.put_nowait("event: sample\ndata: {\"t\":1,\"s\":[]}\n\n")
        frame = await it.__anext__()
        assert frame == "event: sample\ndata: {\"t\":1,\"s\":[]}\n\n"
        await it.aclose()
        assert len(main.SUBSCRIBERS) == 0
        main.SUBSCRIBERS.clear()

    asyncio.run(run())
