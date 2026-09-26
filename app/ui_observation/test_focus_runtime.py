import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock


import pytest


from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation import (
    focus_runtime,
)
from app.ui_observation.focus_contracts import (
    FOCUS_STATUS_AVAILABLE,
    FOCUS_STATUS_UNAVAILABLE,
    FocusedUIObservation,
)


APP = ApplicationIdentity(
    123,
    "test.app",
    "Example",
)


def payload(
    *,
    app=APP,
    captured_at=None,
    **changes,
):
    if captured_at is None:
        captured_at = (
            time.monotonic()
        )

    result = FocusedUIObservation(
        captured_at_monotonic=(
            captured_at
        ),
        status=FOCUS_STATUS_AVAILABLE,
        active_application=app,
        role="AXTextField",
        subrole=None,
        title="Input",
        description="Example input",
        enabled=True,
        position_x=10.0,
        position_y=20.0,
        width=100.0,
        height=30.0,
    ).to_dict()

    result.update(
        changes
    )

    return json.dumps(
        result
    ).encode()


def test_success_uses_fixed_isolated_worker_and_expected_identity(
    monkeypatch,
):
    monkeypatch.setattr(
        focus_runtime.sys,
        "platform",
        "darwin",
    )

    worker = Mock(
        side_effect=lambda *args: (
            payload()
        )
    )

    monkeypatch.setattr(
        focus_runtime,
        "_run_worker",
        worker,
    )

    result = (
        focus_runtime
        .collect_focused_ui(
            APP
        )
    )

    assert (
        result.status
        == FOCUS_STATUS_AVAILABLE
    )

    assert (
        result.active_application.pid
        == APP.pid
    )

    assert (
        result.active_application.bundle_id
        == APP.bundle_id
    )

    assert (
        worker.call_args.args[0]
        == [
            sys.executable,
            "-I",
            "-B",
            str(
                focus_runtime._WORKER
            ),
            "123",
            "test.app",
        ]
    )


@pytest.mark.parametrize(
    "failure,code",
    [
        (
            TimeoutError(),
            "collection_timeout",
        ),
        (
            subprocess.TimeoutExpired(
                "worker",
                1,
            ),
            "collection_timeout",
        ),
        (
            OSError(
                "private native details"
            ),
            "worker_failed",
        ),
        (
            ValueError(
                "private malformed output"
            ),
            "worker_output_invalid",
        ),
    ],
)
def test_worker_failures_are_sanitized_and_lock_released(
    monkeypatch,
    failure,
    code,
):
    monkeypatch.setattr(
        focus_runtime.sys,
        "platform",
        "darwin",
    )

    monkeypatch.setattr(
        focus_runtime,
        "_run_worker",
        Mock(
            side_effect=failure
        ),
    )

    result = (
        focus_runtime
        .collect_focused_ui(
            APP
        )
    )

    assert (
        result.status
        == FOCUS_STATUS_UNAVAILABLE
    )

    assert result.diagnostics == (
        code,
    )

    assert not (
        focus_runtime
        ._COLLECTION_LOCK
        .locked()
    )

    assert (
        "private"
        not in repr(result)
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"null",
        b"[]",
        b"{}",
        payload(
            status="invented"
        ),
        payload(
            diagnostics={}
        ),
        payload(
            extra_authority=True
        ),
    ],
)
def test_invalid_worker_payload_is_rejected(
    monkeypatch,
    raw,
):
    monkeypatch.setattr(
        focus_runtime.sys,
        "platform",
        "darwin",
    )

    monkeypatch.setattr(
        focus_runtime,
        "_run_worker",
        Mock(
            return_value=raw
        ),
    )

    result = (
        focus_runtime
        .collect_focused_ui(
            APP
        )
    )

    assert result.diagnostics == (
        "worker_output_invalid",
    )


def test_wrong_worker_application_identity_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        focus_runtime.sys,
        "platform",
        "darwin",
    )

    other = ApplicationIdentity(
        456,
        "other.app",
        "Other",
    )

    monkeypatch.setattr(
        focus_runtime,
        "_run_worker",
        Mock(
            side_effect=lambda *args: (
                payload(
                    app=other
                )
            )
        ),
    )

    result = (
        focus_runtime
        .collect_focused_ui(
            APP
        )
    )

    assert result.diagnostics == (
        "worker_output_invalid",
    )


def test_result_timestamp_must_belong_to_current_collection(
    monkeypatch,
):
    monkeypatch.setattr(
        focus_runtime.sys,
        "platform",
        "darwin",
    )

    monkeypatch.setattr(
        focus_runtime,
        "_run_worker",
        Mock(
            return_value=payload(
                captured_at=0.0
            )
        ),
    )

    result = (
        focus_runtime
        .collect_focused_ui(
            APP
        )
    )

    assert result.diagnostics == (
        "worker_output_invalid",
    )


def test_unsupported_platform_does_not_launch_worker(
    monkeypatch,
):
    monkeypatch.setattr(
        focus_runtime.sys,
        "platform",
        "linux",
    )

    worker = Mock()

    monkeypatch.setattr(
        focus_runtime,
        "_run_worker",
        worker,
    )

    result = (
        focus_runtime
        .collect_focused_ui(
            APP
        )
    )

    assert result.diagnostics == (
        "unsupported_platform",
    )

    worker.assert_not_called()


@pytest.mark.parametrize(
    "application",
    [
        ApplicationIdentity(
            123,
            None,
            "Example",
        ),
        ApplicationIdentity(
            123,
            "",
            "Example",
        ),
        ApplicationIdentity(
            123,
            "   ",
            "Example",
        ),
    ],
)
def test_incomplete_expected_application_does_not_launch_worker(
    monkeypatch,
    application,
):
    monkeypatch.setattr(
        focus_runtime.sys,
        "platform",
        "darwin",
    )

    worker = Mock()

    monkeypatch.setattr(
        focus_runtime,
        "_run_worker",
        worker,
    )

    result = (
        focus_runtime
        .collect_focused_ui(
            application
        )
    )

    assert result.diagnostics == (
        "expected_application_incomplete",
    )

    worker.assert_not_called()


def test_concurrent_request_does_not_queue_worker(
    monkeypatch,
):
    monkeypatch.setattr(
        focus_runtime.sys,
        "platform",
        "darwin",
    )

    worker = Mock()

    monkeypatch.setattr(
        focus_runtime,
        "_run_worker",
        worker,
    )

    with (
        focus_runtime
        ._COLLECTION_LOCK
    ):
        result = (
            focus_runtime
            .collect_focused_ui(
                APP
            )
        )

    assert result.diagnostics == (
        "collection_busy",
    )

    worker.assert_not_called()


@pytest.mark.parametrize(
    "timeout",
    [
        True,
        0,
        0.01,
        11,
        float("nan"),
        float("inf"),
        "2",
    ],
)
def test_invalid_timeout_is_rejected(
    timeout,
):
    with pytest.raises(
        ValueError
    ):
        focus_runtime.collect_focused_ui(
            APP,
            timeout_seconds=timeout,
        )


def test_worker_output_has_strict_small_bound(
    monkeypatch,
):
    monkeypatch.setattr(
        focus_runtime.sys,
        "platform",
        "darwin",
    )

    oversized = (
        b"x"
        * (
            focus_runtime
            .MAX_FOCUS_OUTPUT_BYTES
            + 1
        )
    )

    monkeypatch.setattr(
        focus_runtime,
        "_run_worker",
        Mock(
            return_value=oversized
        ),
    )

    result = (
        focus_runtime
        .collect_focused_ui(
            APP
        )
    )

    assert result.diagnostics == (
        "worker_output_invalid",
    )


def test_runtime_source_has_no_native_ax_or_action_imports():
    source = (
        Path(
            focus_runtime.__file__
        )
        .read_text()
    )

    forbidden = (
        "ApplicationServices",
        "CoreFoundation",
        "AppKit",
        "pyautogui",
        "ollama",
        "google.genai",
        "AXUIElementSetAttributeValue",
        "AXUIElementPerformAction",
        "type_text(",
        "press_key(",
        "click(",
        "register_tool",
        "KUMA_TOOLS",
    )

    for marker in forbidden:
        assert marker not in source


def test_focus_runtime_contract_is_evidence_only():
    source = (
        Path(
            focus_runtime.__file__
        )
        .read_text()
    )

    assert (
        "FocusedUIObservation"
        in source
    )

    assert (
        "request_confirmation"
        not in source
    )

    assert (
        "semantic_target_verified"
        not in source
    )

    assert (
        "GUI_TARGET_ATTESTATIONS"
        not in source
    )
