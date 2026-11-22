"""slim_sample(): collect_state()-Snapshot -> kompaktes Sample fuer
Stream + RAM-Cache (weniger Bytes pro Frame/Buffer-Eintrag)."""

import time


def slim_sample(state: dict) -> dict:
    """Kompaktes Sample fuer Stream/Cache: pro Station Name, CPU-Summe (nano),
    Mem-Summe (bytes), Pod-Anzahl, Zustand. t = ms epoch."""
    stations = []
    for st in state["stations"]:
        cpu = mem = pods = 0
        states: set[str] = set()
        for tr in st["tracks"]:
            p = tr["pod"]
            if p:
                pods += 1
                cpu += p["cpu_nano"] or 0
                mem += p["mem_bytes"] or 0
                states.add(p["state"])
        if not states:
            s = "zero"
        elif states == {"running"}:
            s = "running"
        else:
            s = "+".join(sorted(states))
        stations.append({"n": st["name"], "c": cpu, "m": mem, "p": pods, "st": s})
    return {"t": round(time.time() * 1000), "s": stations}
