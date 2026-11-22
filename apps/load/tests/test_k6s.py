"""Unit-Tests fuer parse_k6_summary (app/k8s.py) — k6-Summary aus Pod-Log."""

import json
from types import SimpleNamespace

import k8s
from k8s import parse_k6_summary

LOG = """
  execution: local
    script: /scripts/loadtest.js

  scenarios: (100.00%) 1 scenario, 150 max VUs, 5m30s max duration

    http_reqs..................: 65992   732.179731/s
    http_req_duration..........: avg=41.2ms min=1.1ms med=30ms p(90)=88ms p(95)=589.3ms
    http_req_failed............: 0.00%   0 out of 65992
    data_received..............: 21 GB   233 MB/s
    vus........................: 150     min=100 max=150
    vus_max....................: 150     min=150 max=150
"""


def test_parse_k6_summary():
    m = parse_k6_summary(LOG)
    assert m["http_reqs"] == 65992
    assert m["rps"] == 732.2
    assert m["p95_ms"] == 589.3
    assert m["failed_pct"] == 0.0
    assert m["data_received_bytes"] == 21_000_000_000
    assert m["vus"] == 150


def test_parse_k6_summary_units():
    log = ("http_reqs...: 10 5/s\n"
           "p(95)=1.5s\n"
           "http_req_failed...: 2.5%\n"
           "data_received...: 512 MiB\n"
           "vus_max...: 7\n")
    m = parse_k6_summary(log)
    assert m["p95_ms"] == 1500.0       # s -> ms
    assert m["failed_pct"] == 2.5
    assert m["data_received_bytes"] == 512 * 1024**2  # MiB -> bytes
    assert m["vus"] == 7


def test_parse_k6_summary_missing_metrics():
    assert parse_k6_summary("run still in progress, no summary yet") is None


def _fake_job(name="load-run-xyz"):
    return SimpleNamespace(metadata=SimpleNamespace(name=name),
                           status=SimpleNamespace(succeeded=1))


def test_create_run_clamps_overrides_and_annotates(monkeypatch):
    monkeypatch.setattr(k8s, "active_run", lambda: None)
    monkeypatch.setattr(k8s, "list_runs", list)
    captured = {}

    def fake_create(ns, body):
        captured["body"] = body
        return _fake_job()

    monkeypatch.setattr(k8s.batch, "create_namespaced_job", fake_create)
    job = k8s.create_run(source="visitor", duration_s=99999, rate=999999,
                         signals={"webdriver": False})
    assert job is not None
    body = captured["body"]
    env = {e["name"]: e["value"]
           for e in body["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["K6_DURATION"] == "600s"   # OVERRIDE_DURATION_MAX_S
    assert env["K6_RATE"] == "2000"        # OVERRIDE_RATE_MAX
    assert body["spec"]["activeDeadlineSeconds"] == 600 + 120
    ann = body["metadata"]["annotations"]
    assert ann["metzler.systems/load-source"] == "visitor"
    assert json.loads(ann["metzler.systems/load-signals"]) == {"webdriver": False}
    assert body["metadata"]["labels"]["metzler.systems/load-source"] == "visitor"


def test_create_run_returns_none_when_active(monkeypatch):
    monkeypatch.setattr(k8s, "active_run", lambda: object())
    assert k8s.create_run() is None        # -> API antwortet 409


def test_create_run_source_whitelist_label(monkeypatch):
    monkeypatch.setattr(k8s, "active_run", lambda: None)
    monkeypatch.setattr(k8s, "list_runs", list)
    captured = {}

    def fake_create(ns, body):
        captured["body"] = body
        return _fake_job()

    monkeypatch.setattr(k8s.batch, "create_namespaced_job", fake_create)
    k8s.create_run(source="evil-label-value")
    assert captured["body"]["metadata"]["labels"]["metzler.systems/load-source"] == "button"


def test_job_pod_hardened(monkeypatch):
    monkeypatch.setattr(k8s, "active_run", lambda: None)
    monkeypatch.setattr(k8s, "list_runs", list)
    captured = {}

    def fake_create(ns, body):
        captured["body"] = body
        return _fake_job()

    monkeypatch.setattr(k8s.batch, "create_namespaced_job", fake_create)
    k8s.create_run()
    pod = captured["body"]["spec"]["template"]["spec"]
    sc = pod["containers"][0]["securityContext"]
    assert sc["readOnlyRootFilesystem"] is True
    assert sc["runAsNonRoot"] is True
    assert sc["capabilities"]["drop"] == ["ALL"]
    vols = {v["name"]: v for v in pod["volumes"]}
    assert vols["tmp"] == {"name": "tmp", "emptyDir": {}}
    mounts = {m["name"]: m for m in pod["containers"][0]["volumeMounts"]}
    assert mounts["tmp"]["mountPath"] == "/tmp"


# --- Review Runde 2: Parser-Härtung, k6_metrics, run_summary, status, Lock ---

def test_parse_k6_summary_rejects_malformed_numbers():
    # "1.2.3" darf nicht als Zahl matchen — frueher float("1.2.3") -> ValueError -> 500
    log = "http_reqs...: 1.2.3 4/s\n"
    assert parse_k6_summary(log) is None
    # p95 kaputt -> Feld None, aber kein Crash
    log2 = "http_reqs...: 10 5/s\np(95)=1.2.3ms\n"
    m = parse_k6_summary(log2)
    assert m["http_reqs"] == 10
    assert m["p95_ms"] is None


def _succeeded_job(name="load-run-abc"):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, annotations={}, labels={}),
        status=SimpleNamespace(succeeded=1, failed=0, active=0,
                               start_time=None))


def test_k6_metrics_reads_pod_log(monkeypatch):
    job = _succeeded_job()
    monkeypatch.setattr(
        k8s.core, "list_namespaced_pod",
        lambda ns, label_selector: SimpleNamespace(
            items=[SimpleNamespace(metadata=SimpleNamespace(name="load-run-abc-1"))]))
    monkeypatch.setattr(
        k8s.core, "read_namespaced_pod_log",
        lambda name, ns, tail_lines: LOG)
    m = k8s.k6_metrics(job)
    assert m["http_reqs"] == 65992
    assert m["p95_ms"] == 589.3


def test_k6_metrics_not_succeeded_or_no_pods(monkeypatch):
    running = SimpleNamespace(metadata=SimpleNamespace(name="j"),
                              status=SimpleNamespace(succeeded=0, failed=0, active=1))
    assert k8s.k6_metrics(running) is None
    monkeypatch.setattr(
        k8s.core, "list_namespaced_pod",
        lambda ns, label_selector: SimpleNamespace(items=[]))
    assert k8s.k6_metrics(_succeeded_job()) is None


def test_run_summary_fields(monkeypatch):
    from datetime import UTC, datetime
    job = SimpleNamespace(
        metadata=SimpleNamespace(
            name="load-run-abc",
            annotations={"metzler.systems/load-duration-s": "90",
                         "metzler.systems/load-rate": "500"},
            labels={"metzler.systems/load-source": "visitor"}),
        status=SimpleNamespace(succeeded=0, failed=0, active=1,
                               start_time=datetime.now(UTC)))
    s = k8s.run_summary(job)
    assert s["state"] == "running"
    assert s["job_state"] == "Running"
    assert s["source"] == "visitor"
    assert s["duration_s"] == 90
    assert s["rate"] == 500
    assert 0 <= s["remaining_s"] <= 90
    # interne Cluster-Details duerfen nicht in die oeffentliche Antwort
    assert "target" not in s


def test_status_idle_and_no_internals(monkeypatch):
    monkeypatch.setattr(k8s, "list_runs", list)
    s = k8s.status()
    assert s["state"] == "idle"
    assert s["job"] is None
    assert "target" not in s
    assert "k6_image" not in s


def test_list_runs_none_and_status_error_on_api_outage(monkeypatch):
    """K8s-API down: list_runs() -> None und /status meldet "error" statt "idle"."""
    def boom(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(k8s.batch, "list_namespaced_job", boom)
    assert k8s.list_runs() is None
    assert k8s.active_run() is None  # create_run schlaegt spaeter beim Anlegen fehl -> 503
    s = k8s.status()
    assert s["state"] == "error"
    assert s["job"] is None


def test_run_summary_bad_annotations_fall_back_to_config(monkeypatch):
    """Kaputte Job-Annotationen duerfen nie den /status mit 500 schiessen."""
    from datetime import UTC, datetime
    job = SimpleNamespace(
        metadata=SimpleNamespace(
            name="load-run-abc",
            annotations={"metzler.systems/load-duration-s": "kaputt",
                         "metzler.systems/load-rate": "1.2.3"},
            labels={"metzler.systems/load-source": "cli"}),
        status=SimpleNamespace(succeeded=0, failed=0, active=1,
                               start_time=datetime.now(UTC)))
    s = k8s.run_summary(job)
    assert s["duration_s"] == k8s.LOAD_DURATION_S
    assert s["rate"] == k8s.LOAD_RATE


def test_status_last_run_after_succeeded(monkeypatch):
    from datetime import UTC, datetime
    job = SimpleNamespace(
        metadata=SimpleNamespace(
            name="load-run-abc", annotations={}, labels={},
            creation_timestamp=datetime.now(UTC)),
        status=SimpleNamespace(succeeded=1, failed=0, active=0,
                               start_time=datetime.now(UTC)))
    monkeypatch.setattr(k8s, "list_runs", lambda: [job])
    monkeypatch.setattr(k8s, "k6_metrics", lambda j: None)
    s = k8s.status()
    assert s["state"] == "idle"
    assert s["job_state"] == "Succeeded"
    assert s["last_run"] is not None


def test_create_run_lock_prevents_parallel_double_create(monkeypatch):
    """8 parallele create_run-Calls duerfen nur EINEN Job anlegen (Lock)."""
    import threading
    jobs = []

    def fake_list():
        return list(jobs)

    def fake_create(ns, body):
        job = SimpleNamespace(
            metadata=SimpleNamespace(name=f"load-run-{len(jobs)}",
                                     annotations=body["metadata"]["annotations"],
                                     labels=body["metadata"]["labels"]),
            status=None)  # None-Status zaehlt als aktiv (siehe _is_active)
        jobs.append(job)
        return job

    monkeypatch.setattr(k8s, "list_runs", fake_list)
    monkeypatch.setattr(k8s, "active_run", lambda: k8s.active_run.__wrapped__() if False else next((j for j in jobs if k8s._is_active(j)), None))
    monkeypatch.setattr(k8s.batch, "create_namespaced_job", fake_create)
    monkeypatch.setattr(k8s.batch, "delete_namespaced_job",
                        lambda *a, **k: None)

    results = []
    threads = [threading.Thread(target=lambda: results.append(k8s.create_run()))
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(jobs) == 1
    assert sum(1 for r in results if r is not None) == 1
