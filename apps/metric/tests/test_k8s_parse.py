"""Unit-Tests fuer das Quantity-Parsing (app/k8s.py) — ohne Cluster."""

from k8s import cpu_to_nano, mem_to_bytes, parse_quantity


def test_mem_suffix_order_binary_before_decimal():
    # "Ki" muss vor "K" greifen (Dict-Reihenfolge in mem_to_bytes)
    assert mem_to_bytes("1Ki") == 1024
    assert mem_to_bytes("1K") == 1000


def test_cpu_to_nano():
    assert cpu_to_nano("250m") == 250_000_000
    assert cpu_to_nano("296384584n") == 296_384_584
    assert cpu_to_nano("100u") == 100_000
    assert cpu_to_nano("2") == 2_000_000_000


def test_mem_to_bytes():
    assert mem_to_bytes("512Mi") == 512 * 1024**2
    assert mem_to_bytes("6408628Ki") == 6_408_628 * 1024
    assert mem_to_bytes("1Gi") == 1024**3
    assert mem_to_bytes("1G") == 1_000**3
    assert mem_to_bytes("128974848") == 128_974_848


def test_parse_quantity_plain_mult():
    assert parse_quantity("3", {"m": 1}, plain_mult=10) == 30


# --- Review Runde 2: collect_state + pod_info mit gemockter K8s-API ---

from datetime import UTC, datetime
from types import SimpleNamespace

import k8s


def _pod(name="website-abc", phase="Running", deleting=False, waiting=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name, namespace="website", uid=f"uid-{name}",
            deletion_timestamp=datetime.now(UTC) if deleting else None,
            creation_timestamp=datetime.now(UTC)),
        status=SimpleNamespace(
            phase=phase, reason=None,
            container_statuses=([SimpleNamespace(
                state=SimpleNamespace(waiting=SimpleNamespace(reason=waiting)))]
                if waiting else [])))


def test_pod_info_states_and_waiting_reason():
    info = k8s.pod_info(_pod(waiting="CrashLoopBackOff"), {})
    assert info["state"] == "running"
    assert info["reason"] == "CrashLoopBackOff"
    assert k8s.pod_info(_pod(phase="Pending"), {})["state"] == "entering"
    assert k8s.pod_info(_pod(deleting=True), {})["state"] == "leaving"
    assert k8s.pod_info(_pod(phase="Succeeded"), {})["state"] == "leaving"


def test_collect_state_builds_tracks(monkeypatch):
    dep = SimpleNamespace(
        metadata=SimpleNamespace(name="website", namespace="website", uid="d1"),
        spec=SimpleNamespace(
            selector=SimpleNamespace(match_labels={"app": "website"}),
            replicas=2))
    monkeypatch.setattr(k8s, "pod_metrics", lambda: [
        {"namespace": "website", "name": "website-abc",
         "containers": [{"cpu": "250m", "memory": "64Mi"}]}])
    monkeypatch.setattr(k8s.apps_api, "list_namespaced_deployment",
                        lambda ns: SimpleNamespace(items=[dep]))
    monkeypatch.setattr(k8s.core, "list_namespaced_pod",
                        lambda ns, label_selector: SimpleNamespace(
                            items=[_pod()]))
    st = k8s.collect_state(verbose=False)
    assert "error" not in st
    station = st["stations"][0]
    assert station["name"] == "website"
    assert len(station["tracks"]) == 2  # replicas=2, aber nur 1 Pod
    pod = station["tracks"][0]["pod"]
    assert pod["state"] == "running"
    assert pod["cpu_nano"] == 250_000_000
    assert pod["mem_bytes"] == 64 * 1024**2
    assert station["tracks"][1]["pod"] is None


def test_collect_state_metrics_api_down_still_answers(monkeypatch):
    def boom():
        raise RuntimeError("metrics.k8s.io not ready")
    monkeypatch.setattr(k8s, "pod_metrics", boom)
    dep = SimpleNamespace(
        metadata=SimpleNamespace(name="website", namespace="website", uid="d1"),
        spec=SimpleNamespace(
            selector=SimpleNamespace(match_labels={"app": "website"}),
            replicas=1))
    monkeypatch.setattr(k8s.apps_api, "list_namespaced_deployment",
                        lambda ns: SimpleNamespace(items=[dep]))
    monkeypatch.setattr(k8s.core, "list_namespaced_pod",
                        lambda ns, label_selector: SimpleNamespace(items=[_pod()]))
    st = k8s.collect_state(verbose=False)
    assert "error" not in st  # Teil-Resultat ohne CPU/Mem, kein 500
    assert st["stations"][0]["tracks"][0]["pod"]["cpu_nano"] is None


def test_collect_state_error_is_generic_no_internals(monkeypatch):
    monkeypatch.setattr(k8s, "pod_metrics", list)

    def boom(ns):
        raise RuntimeError("ApiException 403 forbidden: quota")
    monkeypatch.setattr(k8s.apps_api, "list_namespaced_deployment", boom)
    st = k8s.collect_state(verbose=False)
    assert st["error"] == "state collection failed"
    assert "quota" not in str(st) and "403" not in str(st)
