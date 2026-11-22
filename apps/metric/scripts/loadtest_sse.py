#!/usr/bin/env python3
"""Loadtest fuer /stream: N parallele SSE-Clients, zaehlt empfangene sample-Events
und Bytes und misst CPU/RSS des Server-Prozesses (--pid, via /proc). Nur stdlib.

Beispiel:
  python scripts/loadtest_sse.py --port 8080 --clients 1000 --duration 15 \
      --procs 4 --pid "$(pgrep -f 'uvicorn main:app')"

--procs N splittet die Clients auf N Child-Prozesse (sonst ist bei 1000+
Clients der Loadtest selbst der Flaschenhals, nicht der Server).
--json gibt genau eine JSON-Zeile aus (fuer die Aggregation durch den Parent).

Liest chunkweise (64k), damit 1000 Clients mit grossem history-Event nicht
selbst das RAM sprengen. Zaehlt Vorkommen von "event: sample".
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time

MARK_SAMPLE = b"event: sample"
MARK_HELLO = b"event: hello"
MARK_HISTORY = b"event: history"

CLK_TCK = os.sysconf("SC_CLK_TCK")


def _cpu_seconds_from_stat(text: str) -> float:
    # comm kann Klammern enthalten: nach dem letzten ")" splitten,
    # utime/stime sind dann Feld 11/12 (0-basiert)
    parts = text.rsplit(")", 1)[1].split()
    return (int(parts[11]) + int(parts[12])) / CLK_TCK


def proc_cpu_seconds(pid: int) -> float:
    with open(f"/proc/{pid}/stat") as f:
        return _cpu_seconds_from_stat(f.read())


def self_cpu_seconds() -> float:
    with open("/proc/self/stat") as f:
        return _cpu_seconds_from_stat(f.read())


def proc_rss_bytes(pid: int) -> int:
    with open(f"/proc/{pid}/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    return 0


async def one_client(host: str, port: int, path: str, duration: float,
                     c: dict) -> None:
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except OSError:
        c["conn_fail"] += 1
        return
    c["connected"] += 1
    try:
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
               "Accept: text/event-stream\r\n"
               "Cache-Control: no-cache\r\nConnection: close\r\n\r\n")
        writer.write(req.encode())
        await writer.drain()
        end = time.monotonic() + duration
        tail = b""
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            try:
                chunk = await asyncio.wait_for(reader.read(65536),
                                               timeout=remaining)
            except TimeoutError:
                break
            if not chunk:
                break
            data = tail + chunk
            c["samples"] += data.count(MARK_SAMPLE)
            c["hello"] += data.count(MARK_HELLO)
            c["history"] += data.count(MARK_HISTORY)
            c["bytes"] += len(chunk)
            keep = len(MARK_SAMPLE) - 1
            tail = data[-keep:] if len(data) >= keep else data
    finally:
        writer.close()


async def run(args: argparse.Namespace) -> dict:
    c = {"connected": 0, "conn_fail": 0, "samples": 0, "hello": 0,
         "history": 0, "bytes": 0}
    cpu0 = proc_cpu_seconds(args.pid) if args.pid else None
    self0 = self_cpu_seconds()
    rss0 = proc_rss_bytes(args.pid) if args.pid else None
    tasks = [asyncio.create_task(
        one_client(args.host, args.port, args.path, args.duration, c))
        for _ in range(args.clients)]
    t0 = time.monotonic()
    try:
        await asyncio.wait_for(asyncio.gather(*tasks),
                               timeout=args.duration + 30)
    except TimeoutError:
        for t in tasks:
            t.cancel()
    dt = time.monotonic() - t0
    self1 = self_cpu_seconds()
    res = dict(c)
    res["duration"] = dt
    res["self_cpu_pct"] = (self1 - self0) / dt * 100
    if args.pid:
        res["server_cpu_pct"] = (proc_cpu_seconds(args.pid) - cpu0) / dt * 100
        res["server_rss_mib"] = proc_rss_bytes(args.pid) / 2**20
        res["server_rss_start_mib"] = rss0 / 2**20
    return res


def human(args: argparse.Namespace, res: dict) -> None:
    dt = res["duration"]
    per_client = res["samples"] / res["connected"] if res["connected"] else 0
    print(f"clients:      {res['connected']} ok, {res['conn_fail']} failed "
          f"(asked {args.clients})")
    print(f"duration:     {dt:.1f} s")
    print(f"hello/hist:   {res['hello']} hello, {res['history']} history events")
    print(f"samples:      {res['samples']} total, {res['samples'] / dt:.0f}/s "
          f"aggregate, {per_client:.0f} per client ({per_client / dt:.1f}/s)")
    print(f"traffic:      {res['bytes'] / dt / 1e6:.1f} MB/s "
          f"({res['bytes'] / dt * 8 / 1e6:.0f} Mbit/s) outbound")
    print(f"loadtest cpu: {res['self_cpu_pct']:.0f}% of one core (client side)")
    if args.pid:
        print(f"server pid:   {args.pid}")
        print(f"server cpu:   {res['server_cpu_pct']:.0f}% of one core "
              f"({res['server_cpu_pct'] / (os.cpu_count() or 1):.1f}% of "
              f"{os.cpu_count()} cores)")
        print(f"server rss:   {res['server_rss_start_mib']:.0f} MiB -> "
              f"{res['server_rss_mib']:.0f} MiB")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--path", default="/stream?window_seconds=60&max_points=2000")
    p.add_argument("--clients", type=int, default=1000)
    p.add_argument("--duration", type=float, default=15.0)
    p.add_argument("--procs", type=int, default=1,
                   help="Clients auf N Child-Prozesse splitten")
    p.add_argument("--pid", type=int, default=None,
                   help="Server-PID fuer CPU/RSS-Messung via /proc")
    p.add_argument("--json", action="store_true",
                   help="nur eine JSON-Zeile ausgeben (intern fuer --procs)")
    args = p.parse_args()

    if args.procs > 1 and not args.json:
        per = max(1, args.clients // args.procs)
        children = []
        for _ in range(args.procs):
            cmd = [sys.executable, os.path.abspath(__file__),
                   "--host", args.host, "--port", str(args.port),
                   "--path", args.path, "--clients", str(per),
                   "--duration", str(args.duration), "--json"]
            if args.pid:
                cmd += ["--pid", str(args.pid)]
            children.append(subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                             text=True))
        agg = {"connected": 0, "conn_fail": 0, "samples": 0, "hello": 0,
               "history": 0, "bytes": 0, "duration": args.duration,
               "self_cpu_pct": 0.0}
        t0 = time.monotonic()
        cpu0 = proc_cpu_seconds(args.pid) if args.pid else None
        rss0 = proc_rss_bytes(args.pid) / 2**20 if args.pid else None
        for ch in children:
            line = ch.stdout.readline().strip()
            ch.wait()
            r = json.loads(line)
            for k in ("connected", "conn_fail", "samples", "hello",
                      "history", "bytes"):
                agg[k] += r[k]
            agg["self_cpu_pct"] = max(agg["self_cpu_pct"],
                                      r.get("self_cpu_pct", 0.0))
        agg["duration"] = time.monotonic() - t0
        if args.pid:
            agg["server_cpu_pct"] = (proc_cpu_seconds(args.pid) - cpu0) \
                / agg["duration"] * 100
            agg["server_rss_mib"] = proc_rss_bytes(args.pid) / 2**20
            agg["server_rss_start_mib"] = rss0
        human(args, agg)
        return 0

    res = asyncio.run(run(args))
    if args.json:
        print(json.dumps(res))
    else:
        human(args, res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
