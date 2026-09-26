import json
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

from app.desktop.contracts import ApplicationIdentity
from app.ui_observation import runtime
from app.ui_observation.contracts import StructuredUIObservation, UIElementObservation


APP = ApplicationIdentity(123, "test.app", "Example")


def payload(**changes):
    result = StructuredUIObservation(
        captured_at_monotonic=time.monotonic(),
        status="available",
        active_application=APP,
        elements=(UIElementObservation(path=(), owner_pid=123, role="AXApplication"),),
        traversal_succeeded=True,
    ).to_dict(include_text=True)
    result.update(changes)
    return json.dumps(result).encode()


def test_success_uses_fixed_isolated_worker_and_expected_identity(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    worker = Mock(side_effect=lambda *args: payload())
    monkeypatch.setattr(runtime, "_run_worker", worker)
    result = runtime.collect_structured_ui(APP)
    assert result.status == "available"
    assert worker.call_args.args[0] == [
        sys.executable, "-I", "-B", str(runtime._WORKER),
        "123", "test.app", "128", "6", "32",
    ]


@pytest.mark.parametrize("failure, code", [
    (TimeoutError(), "collection_timeout"),
    (subprocess.TimeoutExpired("worker", 1), "collection_timeout"),
    (OSError("private"), "worker_failed"),
    (ValueError(), "worker_output_invalid"),
])
def test_worker_failures_are_sanitized_and_lock_released(monkeypatch, failure, code):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    monkeypatch.setattr(runtime, "_run_worker", Mock(side_effect=failure))
    result = runtime.collect_structured_ui(APP)
    assert result.diagnostics == (code,)
    assert not runtime._COLLECTION_LOCK.locked()
    assert "private" not in repr(result)


@pytest.mark.parametrize("raw", [
    b"not json", b"null", b"[]", b"{}",
    payload(status="invented"), payload(diagnostics={}), payload(elements={}),
    payload(extra_authority=True),
])
def test_invalid_worker_payload_is_rejected(monkeypatch, raw):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    monkeypatch.setattr(runtime, "_run_worker", Mock(return_value=raw))
    assert runtime.collect_structured_ui(APP).diagnostics == ("worker_output_invalid",)



def test_worker_paths_outside_requested_bounds_are_rejected(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    raw = json.loads(payload())
    raw["status"] = "available"
    raw["elements"].append(dict(
        path=[1], owner_pid=123, role="AXButton", subrole=None,
        title=None, description=None, enabled=None, focused=None, selected=None,
    ))
    monkeypatch.setattr(runtime, "_run_worker", Mock(return_value=json.dumps(raw).encode()))
    assert runtime.collect_structured_ui(APP, max_children=1).diagnostics == (
        "worker_output_invalid",
    )

def test_wrong_worker_application_identity_is_rejected(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    raw = json.loads(payload())
    raw["active_application"] = dict(pid=456, bundle_id="other.app", name="Other")
    raw["elements"][0]["owner_pid"] = 456
    monkeypatch.setattr(runtime, "_run_worker", Mock(return_value=json.dumps(raw).encode()))
    assert runtime.collect_structured_ui(APP).diagnostics == ("worker_output_invalid",)


def test_unsupported_platform_does_not_launch_worker(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    worker = Mock()
    monkeypatch.setattr(runtime, "_run_worker", worker)
    assert runtime.collect_structured_ui(APP).diagnostics == ("unsupported_platform",)
    worker.assert_not_called()


def test_incomplete_expected_identity_does_not_launch_worker(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    worker = Mock()
    monkeypatch.setattr(runtime, "_run_worker", worker)
    result = runtime.collect_structured_ui(ApplicationIdentity(123))
    assert result.diagnostics == ("expected_application_incomplete",)
    worker.assert_not_called()


def test_concurrent_request_does_not_queue_worker(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    worker = Mock()
    monkeypatch.setattr(runtime, "_run_worker", worker)
    with runtime._COLLECTION_LOCK:
        assert runtime.collect_structured_ui(APP).diagnostics == ("collection_busy",)
    worker.assert_not_called()


@pytest.mark.parametrize("kwargs", [
    dict(timeout_seconds=float("nan")), dict(timeout_seconds=True),
    dict(timeout_seconds=0), dict(timeout_seconds=11),
    dict(max_nodes=0), dict(max_depth=9), dict(max_children=65),
])
def test_invalid_runtime_limits_are_rejected(kwargs):
    with pytest.raises(ValueError):
        runtime.collect_structured_ui(APP, **kwargs)
