"""Realtime-Pipeline (Producer/Multi-Consumer).

Ein dedizierter Producer-PROZESS (multiprocessing, eigener Core, kein
GIL-Wettbewerb mit dem Event-Loop) sampled collect_state() mit SAMPLE_HZ
(max 30/s = "30fps") und schickt schlanke Samples (sample.slim_sample) ueber
eine Pipe an den Server. Der Server fuellt den RAM-Ringbuffer
(config.RETENTION_MIN, max 240 min + Cap config.MAX_SAMPLES_CAP, serviert per
/history in main.py),
rendert den kompletten SSE-Frame genau einmal pro Sample (forwarder_loop)
und legt dieselbe String-Referenz in jede Client-Queue. Pro Client bleibt
damit nur queue-get + yield — weder die K8s-Abfrage (~30 ms pro Tick!) noch
das JSON-Rendering skalieren mit der Client-Anzahl (Lasttest-Skript siehe
README "Skalierung"). Alle Queues sind bounded (drop-oldest):
bei vollem Puffer (langsamer Client / Server im Rueckstand) wird das aelteste
Frame verworfen, der RAM bleibt gedeckelt.
"""

import asyncio
import json
import multiprocessing as mp
import os
import threading
import time
from contextlib import asynccontextmanager

from buffer import SampleBuffer
from config import RETENTION_MIN, SAMPLE_HZ, log
from fastapi import FastAPI
from k8s import collect_state
from sample import slim_sample

BUFFER = SampleBuffer(SAMPLE_HZ, RETENTION_MIN)
SUBSCRIBERS: set[asyncio.Queue] = set()
# Serialisiert Check+Add in api_stream: ohne Lock ueberschiessen N parallele
# Connects MAX_SUBSCRIBERS um N (check-then-act-Race zwischen Endpoint und gen).
SUBSCRIBERS_LOCK = asyncio.Lock()
# Pro-Client-Puffer: ~2 s Samples. Bei 30 Hz = 60 Frames a ~300 B = ~18 kB
# pro Client, also ~18 MB bei 1000 Clients worst case (statt unbounded).
QUEUE_MAXLEN = max(8, int(SAMPLE_HZ * 2))
# Obergrenze gleichzeitiger SSE-Subscriber: /stream meldet 503 statt
# unbegrenzt RAM/CPU pro weiterem Client zu verbrennen.
MAX_SUBSCRIBERS = 100
# Pipe-Puffer zwischen Producer-Prozess und Server (drop-oldest, siehe offer).
# asyncio.Queue bindet seit 3.10 keinen Loop mehr bei der Erzeugung.
INBOUND: asyncio.Queue = asyncio.Queue(QUEUE_MAXLEN)
DROPPED = 0  # verworfene Frames wegen voller Queues (langsame Clients/Consumer)


def offer(q: asyncio.Queue, frame: str) -> None:
    """Frame in eine Client-Queue legen. Bei voller Queue das aelteste Frame
    verwerfen (drop-oldest): die Live-Ansicht bleibt frisch und der Speicher
    pro Client bleibt durch QUEUE_MAXLEN gedeckelt."""
    global DROPPED
    try:
        q.put_nowait(frame)
    except asyncio.QueueFull:
        try:
            q.get_nowait()
            DROPPED += 1
        except asyncio.QueueEmpty:
            pass
        try:
            q.put_nowait(frame)
        except asyncio.QueueFull:
            pass


def producer_loop(send_conn) -> None:
    """Laeuft im eigenen Prozess (siehe lifespan): sammelt collect_state() mit
    SAMPLE_HZ (blockierende K8s-Calls ~30 ms/Tick duerfen den Server-Loop nicht
    ausbremsen) und schickt jedes slim_sample ueber die Pipe an den Server.
    Schlaeft nie laenger als noetig und ueberholt sich nicht. Stirbt mit dem
    Parent (daemon) oder wenn die Pipe geschlossen ist."""
    interval = 1.0 / SAMPLE_HZ
    log(f"producer started (pid {os.getpid()}): {SAMPLE_HZ} Hz, "
        f"retention {RETENTION_MIN} min ({BUFFER.maxlen} samples max)")
    n = 0
    while True:
        started = time.monotonic()
        try:
            state = collect_state(verbose=False)
            if "error" not in state:
                send_conn.send(slim_sample(state))
                n += 1
                if n % 300 == 0:  # Lebenszeichen alle 300 Samples (bei 30 Hz: 10 s)
                    log(f"producer alive: {n} samples")
        except (BrokenPipeError, OSError):
            return  # Server ist weg
        except Exception as e:  # noqa: BLE001 - Producer darf nie sterben
            log(f"producer error: {e}")
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, interval - elapsed))


def _pipe_reader(conn, loop: asyncio.AbstractEventLoop,
                 q: asyncio.Queue) -> None:
    """Blockierender Reader-Thread: holt Samples aus der Pipe und legt sie
    thread-safe (drop-oldest) in die INBOUND-Queue des Event-Loops."""
    while True:
        try:
            sample = conn.recv()
        except (EOFError, OSError):
            return  # Producer beendet / Pipe zu
        loop.call_soon_threadsafe(offer, q, sample)


async def forwarder_loop() -> None:
    """Consumer im Server-Prozess: nimmt Samples aus INBOUND, fuellt den
    RAM-Ringbuffer und rendert den kompletten SSE-Frame GENAU EINMAL pro
    Sample. Alle SSE-Clients bekommen dieselbe String-Referenz — die Kosten
    pro zusaetzlichem Client sind nur queue-get + yield im Stream."""
    n = 0
    while True:
        sample = await INBOUND.get()
        BUFFER.append(sample)
        sample["b"] = len(BUFFER)
        frame = (f"event: sample\n"
                 f"data: {json.dumps(sample, separators=(',', ':'))}\n\n")
        for q in list(SUBSCRIBERS):
            offer(q, frame)
        n += 1
        if n % 300 == 0:  # Lebenszeichen alle 300 Samples (bei 30 Hz: 10 s)
            log(f"forwarder alive: {n} samples, "
                f"buffer {len(BUFFER)}/{BUFFER.maxlen}, "
                f"subscribers {len(SUBSCRIBERS)}, dropped {DROPPED}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Producer als eigener Prozess (fork): eigener Core, kein GIL-Wettbewerb
    # mit dem Event-Loop. Pipe statt mp.Queue: kein /dev/shm noetig.
    recv_conn, send_conn = mp.Pipe(duplex=False)
    producer = mp.Process(target=producer_loop, args=(send_conn,), daemon=True)
    producer.start()
    send_conn.close()  # Parent haelt nur die Empfangsseite
    loop = asyncio.get_running_loop()
    reader = threading.Thread(target=_pipe_reader,
                              args=(recv_conn, loop, INBOUND), daemon=True)
    reader.start()
    fwd = asyncio.create_task(forwarder_loop())
    try:
        yield
    finally:
        fwd.cancel()
        producer.terminate()
