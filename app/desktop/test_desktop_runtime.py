import json
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

from app.desktop import diagnostic, runtime
from app.desktop.contracts import ApplicationIdentity, DesktopContextObservation


def payload(**changes):
    result = DesktopContextObservation(
        captured_at_monotonic=time.monotonic(), status="available",
        active_application=ApplicationIdentity(123, "test.app", "Example"),
        enumeration_succeeded=True,
    ).to_dict(include_titles=True)
    result.update(changes)
    return json.dumps(result).encode()


def test_success_uses_only_fixed_isolated_worker(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    worker = Mock(side_effect=lambda *args: payload())
    monkeypatch.setattr(runtime, "_run_worker", worker)
    result = runtime.collect_desktop_context()
    assert result.status == "available"
    assert worker.call_args.args[0] == [sys.executable, "-I", "-B", str(runtime._WORKER), "32"]


@pytest.mark.parametrize("failure, code", [
    (TimeoutError(), "collection_timeout"),
    (subprocess.TimeoutExpired("worker", 1), "collection_timeout"),
    (OSError("private metadata"), "worker_failed"),
    (ValueError(), "worker_output_invalid"),
])
def test_worker_failures_return_sanitized_unknown_and_release_lock(monkeypatch, failure, code):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    monkeypatch.setattr(runtime, "_run_worker", Mock(side_effect=failure))
    result = runtime.collect_desktop_context()
    assert result.status == "unavailable"
    assert result.diagnostics == (code,)
    assert not runtime._COLLECTION_LOCK.locked()
    assert "private" not in repr(result)


@pytest.mark.parametrize("raw", [b"not json", b"null", b"[]", b"{}",
    payload(captured_at_monotonic=0), payload(captured_at_monotonic=1e100),
    payload(status="invented"), payload(diagnostics={}),
    payload(windows={}), payload(extra_authority=True),
])
def test_invalid_or_replayed_worker_payload_is_rejected(monkeypatch, raw):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    monkeypatch.setattr(runtime, "_run_worker", Mock(return_value=raw))
    result = runtime.collect_desktop_context()
    assert result.diagnostics == ("worker_output_invalid",)


def test_unsupported_platform_does_not_launch_worker(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    worker = Mock()
    monkeypatch.setattr(runtime, "_run_worker", worker)
    assert runtime.collect_desktop_context().diagnostics == ("unsupported_platform",)
    worker.assert_not_called()


def test_concurrent_request_does_not_queue_a_second_worker(monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    worker = Mock()
    monkeypatch.setattr(runtime, "_run_worker", worker)
    with runtime._COLLECTION_LOCK:
        assert runtime.collect_desktop_context().diagnostics == ("collection_busy",)
    worker.assert_not_called()


@pytest.mark.parametrize("kwargs", [dict(timeout_seconds=float("nan")),
    dict(timeout_seconds=float("inf")), dict(timeout_seconds=True),
    dict(timeout_seconds=0), dict(timeout_seconds=11), dict(max_windows=True),
    dict(max_windows=0), dict(max_windows=65), dict(max_windows=1.5)])
def test_invalid_collection_limits_are_rejected(kwargs):
    with pytest.raises(ValueError):
        runtime.collect_desktop_context(**kwargs)


def test_private_worker_output_is_bounded_and_process_reaped(monkeypatch):
    processes = []
    original_popen = subprocess.Popen
    def recording_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(runtime.subprocess, "Popen", recording_popen)
    with pytest.raises(ValueError):
        runtime._run_worker([sys.executable, "-I", "-c", "print('x' * 2000000)"], 3)
    assert processes[0].poll() is not None
    assert processes[0].stdout.closed


def test_timed_out_worker_is_killed_reaped_and_cannot_return_late(monkeypatch):
    processes = []
    original_popen = subprocess.Popen
    def recording_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(runtime.subprocess, "Popen", recording_popen)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        runtime._run_worker([sys.executable, "-I", "-c",
                             "import time; time.sleep(30); print('late')"], 0.15)
    assert time.monotonic() - started < 3
    assert processes[0].poll() is not None
    assert processes[0].stdout.closed
    assert runtime._run_worker([sys.executable, "-I", "-c", "print('fresh')"], 3) == b"fresh\n"


def test_diagnostic_prints_structured_output_and_does_not_start_agent(monkeypatch, capsys):
    observation = DesktopContextObservation.from_dict(json.loads(payload()))
    monkeypatch.setattr(diagnostic, "collect_desktop_context", Mock(return_value=observation))
    assert diagnostic.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["titles_included"] is False
    assert result["enumeration_succeeded"] is True


def test_diagnostic_titles_require_explicit_flag(monkeypatch, capsys):
    from app.desktop.test_desktop_context import collect, provider, row
    observation = collect(provider([row(title="Private window title")]))
    monkeypatch.setattr(diagnostic, "collect_desktop_context", Mock(return_value=observation))
    assert diagnostic.main([]) == 2
    assert "Private window title" not in capsys.readouterr().out
    assert diagnostic.main(["--include-titles"]) == 2
    assert "Private window title" in capsys.readouterr().out
