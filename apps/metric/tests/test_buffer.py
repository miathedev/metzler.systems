"""Unit-Tests fuer den RAM-Ringbuffer (app/buffer.py) — ohne Cluster."""

import json

from buffer import CACHE_MAX_KEYS, SampleBuffer
from config import MAX_SAMPLES_CAP


def _sample(i: int) -> dict:
    return {"t": 1_700_000_000_000 + i * 100,
            "s": [{"n": "website", "c": i, "m": i * 2, "p": 1, "st": "running"}]}


def test_maxlen_hardcap():
    # 240 min x 30 Hz = 432_000 > Cap -> gedeckelt
    assert SampleBuffer(30.0, 240).maxlen == MAX_SAMPLES_CAP
    # normale Werte bleiben unberuehrt
    assert SampleBuffer(10.0, 30).maxlen == 18_000


def test_dump_max_points_keeps_newest():
    buf = SampleBuffer(10.0, 30)
    for i in range(100):
        buf.append(_sample(i))
    out = json.loads(buf.dump(None, 10))
    assert len(out) == 10
    assert out[-1]["t"] == _sample(99)["t"]


def test_dump_cached_hit_returns_same_object():
    buf = SampleBuffer(10.0, 30)
    for i in range(20):
        buf.append(_sample(i))
    a = buf.dump_cached(None, 5)
    b = buf.dump_cached(None, 5)
    assert a is b  # Cache-Hit: identisches String-Objekt, kein Re-Join


def test_dump_cached_lru_evicts_oldest_never_clears():
    buf = SampleBuffer(10.0, 30)
    for i in range(20):
        buf.append(_sample(i))
    buf.dump_cached(None, 5)
    for w in range(CACHE_MAX_KEYS):  # (0.0, 5) .. (7.0, 5)
        buf.dump_cached(float(w), 5)
    assert len(buf._cache) == CACHE_MAX_KEYS
    assert (None, 5) not in buf._cache  # aeltester Key evicten
    assert (0.0, 5) in buf._cache


def test_dump_cached_byte_cap_evicts_oldest(monkeypatch):
    # Byte-Cap (nicht nur Key-Anzahl): bei kleinem Cap muss der aelteste
    # Eintrag rausfliegen, sobald das neue Ergebnis nicht mehr daneben passt
    import buffer as bufmod
    monkeypatch.setattr(bufmod, "CACHE_MAX_BYTES", 1000)  # 2 Eintraege ~790 B passen, 3 nicht
    buf = SampleBuffer(10.0, 30)
    for i in range(200):
        buf.append(_sample(i))
    buf.dump_cached(None, 5)
    buf.dump_cached(60.0, 5)
    assert len(buf._cache) == 2
    buf.dump_cached(120.0, 5)  # passt nicht mehr daneben -> aeltester Key raus
    assert (None, 5) not in buf._cache
    assert (60.0, 5) in buf._cache
    assert (120.0, 5) in buf._cache
