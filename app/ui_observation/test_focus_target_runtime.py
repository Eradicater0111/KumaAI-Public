import base64
import json
from unittest.mock import (
    Mock,
)

import pytest

from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation.focus_target_correlation import (
    CORRELATION_STATUS_MATCHED,
    FocusTargetCorrelationResult,
    FocusTargetSemanticCandidate,
    focus_target_correlation_to_dict,
)
from app.ui_observation import (
    focus_target_runtime as runtime,
)
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)


APP = ApplicationIdentity(
    123,
    "test.app",
    "Example",
)

SELECTOR = (
    StructuredUITargetSelector(
        role="AXTextField",
        text="Search",
    )
)


class Clock:
    def __init__(
        self,
        *values,
    ):
        self.values = list(
            values
        )

    def __call__(
        self,
    ):
        if len(
            self.values
        ) > 1:
            return self.values.pop(
                0
            )

        return self.values[
            0
        ]


def matched_result(
    *,
    captured=100.5,
    application=None,
    selector=None,
    path=(
        0,
    ),
):
    application = (
        application
        or ApplicationIdentity(
            123,
            "test.app",
        )
    )

    selector = (
        selector
        or SELECTOR
    )

    return FocusTargetCorrelationResult(
        captured_at_monotonic=(
            captured
        ),
        status=(
            CORRELATION_STATUS_MATCHED
        ),
        expected_application=(
            application
        ),
        selector=selector,
        candidate_count=1,
        candidate=(
            FocusTargetSemanticCandidate(
                path=path,
                owner_pid=(
                    application.pid
                ),
                role=(
                    selector.role
                    if selector.role is not None
                    else "AXTextField"
                ),
                subrole=(
                    selector.subrole
                ),
                title=(
                    selector.text
                ),
                description=None,
                enabled=(
                    True
                    if selector.require_enabled
                    else None
                ),
                position_x=(
                    10.0
                    if selector.require_positive_area
                    else None
                ),
                position_y=(
                    20.0
                    if selector.require_positive_area
                    else None
                ),
                width=(
                    200.0
                    if selector.require_positive_area
                    else None
                ),
                height=(
                    30.0
                    if selector.require_positive_area
                    else None
                ),
            )
        ),
        diagnostics=(),
    )


def wire(
    result,
):
    return json.dumps(
        focus_target_correlation_to_dict(
            result
        ),
        allow_nan=False,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )


def install_clock(
    monkeypatch,
    *values,
):
    monkeypatch.setattr(
        runtime.time,
        "monotonic",
        Clock(
            *values
        ),
    )


def test_runtime_accepts_valid_worker_result(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    install_clock(
        monkeypatch,
        100.0,
        101.0,
    )

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        Mock(
            return_value=wire(
                matched_result()
            )
        ),
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
        )
    )

    assert result.matched

    assert (
        result.candidate.path
        == (
            0,
        )
    )


def test_runtime_uses_isolated_python_and_encoded_selector(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    install_clock(
        monkeypatch,
        100.0,
        101.0,
    )

    captured = {}

    def run(
        command,
        timeout,
    ):
        captured[
            "command"
        ] = command

        captured[
            "timeout"
        ] = timeout

        return wire(
            matched_result()
        )

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        run,
    )

    runtime.collect_focus_target_correlation_isolated(
        APP,
        SELECTOR,
    )

    command = captured[
        "command"
    ]

    assert command[
        1:3
    ] == [
        "-I",
        "-B",
    ]

    assert (
        command[
            3
        ]
        == str(
            runtime._WORKER
        )
    )

    encoded = command[
        6
    ]

    decoded = json.loads(
        base64.b64decode(
            encoded
        ).decode(
            "utf-8"
        )
    )

    assert decoded[
        "role"
    ] == "AXTextField"

    assert decoded[
        "text"
    ] == "Search"

    assert (
        captured[
            "timeout"
        ]
        == 3.0
    )


def test_non_darwin_fails_before_worker(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "linux",
    )

    worker = Mock()

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        worker,
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
        )
    )

    assert result.diagnostics == (
        "unsupported_platform",
    )

    worker.assert_not_called()


def test_incomplete_application_fails_before_worker(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    worker = Mock()

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        worker,
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            ApplicationIdentity(
                123
            ),
            SELECTOR,
        )
    )

    assert result.diagnostics == (
        "expected_application_incomplete",
    )

    worker.assert_not_called()


def test_collection_lock_is_fail_closed(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    assert runtime._COLLECTION_LOCK.acquire(
        blocking=False
    )

    try:
        result = (
            runtime
            .collect_focus_target_correlation_isolated(
                APP,
                SELECTOR,
            )
        )

        assert result.diagnostics == (
            "collection_busy",
        )

    finally:
        runtime._COLLECTION_LOCK.release()


@pytest.mark.parametrize(
    "value",
    [
        True,
        0,
        0.01,
        11,
        float(
            "nan"
        ),
        float(
            "inf"
        ),
        "3",
    ],
)
def test_invalid_timeout_is_rejected(
    value,
):
    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        runtime.collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
            timeout_seconds=value,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "max_nodes": 0,
        },
        {
            "max_nodes": 1025,
        },
        {
            "max_depth": -1,
        },
        {
            "max_depth": 17,
        },
        {
            "max_children": 0,
        },
        {
            "max_children": 129,
        },
    ],
)
def test_runtime_enforces_dedicated_bounds(
    kwargs,
):
    with pytest.raises(
        ValueError
    ):
        runtime.collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
            **kwargs,
        )


def test_timeout_becomes_structured_unknown(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        Mock(
            side_effect=TimeoutError
        ),
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
        )
    )

    assert result.diagnostics == (
        "collection_timeout",
    )


def test_worker_failure_becomes_structured_unknown(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        Mock(
            side_effect=OSError(
                "private"
            )
        ),
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
        )
    )

    assert result.diagnostics == (
        "worker_failed",
    )


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"not-json",
        b"[]",
        b"{}",
    ],
)
def test_invalid_worker_payload_is_rejected(
    monkeypatch,
    payload,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    install_clock(
        monkeypatch,
        100.0,
        101.0,
    )

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        Mock(
            return_value=payload
        ),
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
        )
    )

    assert result.diagnostics == (
        "worker_output_invalid",
    )


def test_worker_timestamp_must_belong_to_collection(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    install_clock(
        monkeypatch,
        100.0,
        101.0,
    )

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        Mock(
            return_value=wire(
                matched_result(
                    captured=99.0
                )
            )
        ),
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
        )
    )

    assert result.diagnostics == (
        "worker_output_invalid",
    )


def test_worker_cannot_change_application(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    install_clock(
        monkeypatch,
        100.0,
        101.0,
    )

    foreign = (
        ApplicationIdentity(
            999,
            "foreign.app",
        )
    )

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        Mock(
            return_value=wire(
                matched_result(
                    application=foreign,
                )
            )
        ),
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
        )
    )

    assert result.diagnostics == (
        "worker_output_invalid",
    )


def test_worker_cannot_change_selector(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    install_clock(
        monkeypatch,
        100.0,
        101.0,
    )

    changed = (
        StructuredUITargetSelector(
            role="AXTextField",
            text="Other",
        )
    )

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        Mock(
            return_value=wire(
                matched_result(
                    selector=changed,
                )
            )
        ),
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
        )
    )

    assert result.diagnostics == (
        "worker_output_invalid",
    )


def test_worker_candidate_must_fit_requested_depth(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime.sys,
        "platform",
        "darwin",
    )

    install_clock(
        monkeypatch,
        100.0,
        101.0,
    )

    monkeypatch.setattr(
        runtime,
        "_run_worker",
        Mock(
            return_value=wire(
                matched_result(
                    path=(
                        0,
                        0,
                    )
                )
            )
        ),
    )

    result = (
        runtime
        .collect_focus_target_correlation_isolated(
            APP,
            SELECTOR,
            max_depth=1,
        )
    )

    assert result.diagnostics == (
        "worker_output_invalid",
    )


def test_runtime_source_has_no_native_ax_imports():
    text = runtime.Path(
        runtime.__file__
    ).read_text(
        encoding="utf-8"
    )

    forbidden = (
        "import ApplicationServices",
        "import AppKit",
        "import CoreFoundation",
        "AXUIElementSetAttributeValue",
        "AXUIElementPerformAction",
        "pyautogui",
    )

    for marker in forbidden:
        assert marker not in text
