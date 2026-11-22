"""RAM-Ringbuffer fuer Samples: haelt bis zu retention_minutes * 60 * sample_hz
Eintraege als (epoch_s, json_str); aelteste werden verdraengt."""

import json
import time
from collections import deque

from config import MAX_SAMPLES_CAP

# Bounded LRU fuer dump_cached(): bei mehr als CACHE_MAX_KEYS Parameter-
# Kombinationen wird der aelteste Key evicten — nie der ganze Cache geleert,
# sonst thrashen parallele Requests mit wechselnden window/max_points-Params.
CACHE_MAX_KEYS = 8
# Zusaetzlich byte-basiert gedeckelt: 8 Keys x bis zu 60k Samples (~300 B pro
# Sample) koennten sonst den 128Mi-Pod per oeffentlichem /history OOM-killen.
CACHE_MAX_BYTES = 32 * 1024 * 1024


class SampleBuffer:
    def __init__(self, sample_hz: float, retention_minutes: int):
        self.retention_seconds = retention_minutes * 60
        # Harter Cap: auch bei maximalen Env-Werten bleibt der RAM gedeckelt.
        self.maxlen = min(max(1, int(retention_minutes * 60 * sample_hz)),
                          MAX_SAMPLES_CAP)
        self.buf: deque[tuple[float, str]] = deque(maxlen=self.maxlen)
        self._cache: dict[tuple, tuple] = {}

    def append(self, sample: dict) -> None:
        s = json.dumps(sample, separators=(",", ":"))
        self.buf.append((sample["t"] / 1000.0, s))

    def dump(self, window_seconds: float | None = None, max_points: int = 3000) -> str:
        """JSON-Array-String aller Samples (aelteste zuerst). Bei window_seconds
        bleiben die juengsten vollstaendig erhalten, aeltere werden gestrideet,
        sodass insgesamt max_points nicht ueberschritten wird."""
        cutoff = time.time() - window_seconds if window_seconds else 0.0
        recent = [s for (t, s) in self.buf if t >= cutoff]
        older = [s for (t, s) in self.buf if t < cutoff]
        if len(recent) >= max_points:
            recent = recent[-max_points:]
            older = []
        else:
            budget = max_points - len(recent)
            if len(older) > budget:
                stride = -(-len(older) // budget)  # ceil
                older = older[::stride]
        return "[" + ",".join(older + recent) + "]"

    def dump_cached(self, window_seconds: float | None, max_points: int) -> str:
        """dump() mit Cache pro Tick: Bei einem Connect-Burst (viele Clients
        verbinden sich im selben Tick) wird das teure Join-Ergebnis nur einmal
        pro Tick und Parameter-Set gebaut und von allen geteilt. Der Cache
        invalidiert ueber (Laenge, letzter Zeitstempel) bei jedem append."""
        key = (window_seconds, max_points)
        last_t = self.buf[-1][0] if self.buf else 0.0
        hit = self._cache.get(key)
        if hit and hit[0] == len(self.buf) and hit[1] == last_t:
            return hit[2]
        res = self.dump(window_seconds, max_points)
        if key not in self._cache and len(self._cache) >= CACHE_MAX_KEYS:
            self._cache.pop(next(iter(self._cache)))  # aeltesten Key evicten
        # Byte-Cap: aelteste Keys evicten, bis das neue Ergebnis dazu passt
        total = sum(len(v[2]) for v in self._cache.values())
        while self._cache and total + len(res) > CACHE_MAX_BYTES:
            oldest_key = next(iter(self._cache))
            total -= len(self._cache[oldest_key][2])
            self._cache.pop(oldest_key)
        self._cache[key] = (len(self.buf), last_t, res)
        return res

    def __len__(self) -> int:
        return len(self.buf)
