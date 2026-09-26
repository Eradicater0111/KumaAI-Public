from __future__ import annotations

import ast
from dataclasses import (
    FrozenInstanceError,
    fields,
)
import inspect
import math
from pathlib import Path

import pytest

from app.runtime_trace import (
    KumaRuntimeTrace,
    RuntimeTraceEvent,
    TRACE_AUTHORITY_NONE,
    TRACE_DEFAULT_MAX_EVENTS,
    TRACE_ID_MAX_CHARS,
    TRACE_LABEL_MAX_CHARS,
    TRACE_MAX_DURATION_MS,
    TRACE_MAX_EVENTS,
    TRACE_METADATA_KEY_MAX_CHARS,
    TRACE_METADATA_MAX_ITEMS,
    TRACE_METADATA_STRING_MAX_CHARS,
    TRACE_REASON_MAX_CHARS,
    new_runtime_trace_id,
    sanitize_trace_metadata,
)


MODULE = Path(
    "app/runtime_trace.py"
)


def event(
    **overrides,
):
    values = {
        "trace_id": "trace-demo",
        "sequence": 1,
        "stage": "cognition",
        "event_kind": "stage.started",
        "monotonic_ns": 100,
        "outcome": "observed",
    }

    values.update(
        overrides
    )

    return RuntimeTraceEvent(
        **values
    )


def imports():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    modules = set()

    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            modules.add(
                node.module
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias in node.names
            )

    return modules


def test_authority_constant_is_none():
    assert (
        TRACE_AUTHORITY_NONE
        == "NONE"
    )


def test_event_fields_are_exact():
    assert tuple(
        item.name
        for item in fields(
            RuntimeTraceEvent
        )
    ) == (
        "trace_id",
        "sequence",
        "stage",
        "event_kind",
        "monotonic_ns",
        "duration_ms",
        "outcome",
        "reason",
        "metadata",
        "authority",
    )


def test_authority_is_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            RuntimeTraceEvent
        ).parameters
    )


def test_event_is_frozen():
    value = event()

    with pytest.raises(
        FrozenInstanceError
    ):
        value.stage = "execution"


def test_event_is_slotted():
    assert not hasattr(
        event(),
        "__dict__",
    )


def test_default_authority_is_none():
    assert (
        event().authority
        == "NONE"
    )


def test_default_duration_is_none():
    assert (
        event().duration_ms
        is None
    )


def test_default_reason_is_empty():
    assert (
        event().reason
        == ""
    )


def test_default_metadata_is_empty_tuple():
    assert (
        event().metadata
        == ()
    )


def test_stage_normalizes_case_and_whitespace():
    value = event(
        stage="  COGNITION  "
    )

    assert (
        value.stage
        == "cognition"
    )


def test_event_kind_normalizes_case_and_whitespace():
    value = event(
        event_kind=(
            "  STAGE.STARTED "
        )
    )

    assert (
        value.event_kind
        == "stage.started"
    )


def test_outcome_normalizes_case_and_whitespace():
    value = event(
        outcome=" SUCCEEDED "
    )

    assert (
        value.outcome
        == "succeeded"
    )


def test_reason_normalizes_to_identifier_label():
    value = event(
        reason=" TIMEOUT "
    )

    assert (
        value.reason
        == "timeout"
    )


def test_trace_id_preserves_case_but_trims():
    value = event(
        trace_id=" Trace-ABC "
    )

    assert (
        value.trace_id
        == "Trace-ABC"
    )


@pytest.mark.parametrize(
    "value",
    (
        None,
        1,
        True,
        object(),
    ),
)
def test_trace_id_requires_string(
    value,
):
    with pytest.raises(
        TypeError,
        match="trace_id",
    ):
        event(
            trace_id=value
        )


@pytest.mark.parametrize(
    "value",
    (
        "",
        "   ",
    ),
)
def test_trace_id_rejects_blank(
    value,
):
    with pytest.raises(
        ValueError,
        match="trace_id",
    ):
        event(
            trace_id=value
        )


@pytest.mark.parametrize(
    "value",
    (
        "trace with spaces",
        "trace/path",
        "trace?query",
        "trace\nnewline",
    ),
)
def test_trace_id_rejects_non_identifier_content(
    value,
):
    with pytest.raises(
        ValueError,
        match="identifier-like",
    ):
        event(
            trace_id=value
        )


def test_trace_id_rejects_over_limit():
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        event(
            trace_id=(
                "x"
                * (
                    TRACE_ID_MAX_CHARS
                    + 1
                )
            )
        )


def test_trace_id_accepts_limit():
    value = event(
        trace_id=(
            "x"
            * TRACE_ID_MAX_CHARS
        )
    )

    assert (
        len(
            value.trace_id
        )
        == TRACE_ID_MAX_CHARS
    )


@pytest.mark.parametrize(
    "value",
    (
        True,
        False,
        1.0,
        "1",
        None,
    ),
)
def test_sequence_requires_exact_int(
    value,
):
    with pytest.raises(
        TypeError,
        match="sequence",
    ):
        event(
            sequence=value
        )


@pytest.mark.parametrize(
    "value",
    (
        0,
        -1,
    ),
)
def test_sequence_rejects_nonpositive(
    value,
):
    with pytest.raises(
        TypeError,
        match="sequence",
    ):
        event(
            sequence=value
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "stage",
        "event_kind",
        "outcome",
    ),
)
def test_required_labels_reject_blank(
    field_name,
):
    with pytest.raises(
        ValueError,
        match="nonempty",
    ):
        event(
            **{
                field_name: "   "
            }
        )


@pytest.mark.parametrize(
    (
        "field_name",
        "value",
    ),
    (
        (
            "stage",
            "raw user prompt",
        ),
        (
            "event_kind",
            "stage/started",
        ),
        (
            "outcome",
            "goal complete!",
        ),
    ),
)
def test_labels_reject_free_text(
    field_name,
    value,
):
    with pytest.raises(
        ValueError,
        match="identifier-like",
    ):
        event(
            **{
                field_name: value
            }
        )


def test_stage_rejects_over_limit():
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        event(
            stage=(
                "x"
                * (
                    TRACE_LABEL_MAX_CHARS
                    + 1
                )
            )
        )


def test_reason_rejects_over_limit():
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        event(
            reason=(
                "x"
                * (
                    TRACE_REASON_MAX_CHARS
                    + 1
                )
            )
        )


def test_reason_rejects_arbitrary_sentence():
    with pytest.raises(
        ValueError,
        match="identifier-like",
    ):
        event(
            reason=(
                "user said please delete this file"
            )
        )


@pytest.mark.parametrize(
    "value",
    (
        True,
        False,
        1.0,
        "100",
        None,
    ),
)
def test_monotonic_ns_requires_exact_int(
    value,
):
    with pytest.raises(
        TypeError,
        match="monotonic_ns",
    ):
        event(
            monotonic_ns=value
        )


def test_monotonic_ns_accepts_zero():
    assert (
        event(
            monotonic_ns=0
        ).monotonic_ns
        == 0
    )


def test_monotonic_ns_rejects_negative():
    with pytest.raises(
        TypeError,
        match="monotonic_ns",
    ):
        event(
            monotonic_ns=-1
        )


@pytest.mark.parametrize(
    "value",
    (
        0,
        0.0,
        0.5,
        100,
        100.25,
        TRACE_MAX_DURATION_MS,
    ),
)
def test_duration_accepts_bounded_numeric(
    value,
):
    result = event(
        duration_ms=value
    )

    assert (
        result.duration_ms
        == float(
            value
        )
    )


@pytest.mark.parametrize(
    "value",
    (
        True,
        False,
        "1",
        object(),
    ),
)
def test_duration_rejects_non_numeric(
    value,
):
    with pytest.raises(
        TypeError,
        match="duration_ms",
    ):
        event(
            duration_ms=value
        )


@pytest.mark.parametrize(
    "value",
    (
        -0.1,
        float("inf"),
        float("-inf"),
        float("nan"),
        TRACE_MAX_DURATION_MS
        + 0.1,
    ),
)
def test_duration_rejects_invalid_numeric(
    value,
):
    with pytest.raises(
        ValueError,
        match="duration_ms",
    ):
        event(
            duration_ms=value
        )


def test_sanitize_none_metadata_is_empty():
    assert (
        sanitize_trace_metadata(
            None
        )
        == ()
    )


def test_sanitize_metadata_is_deterministically_sorted():
    result = (
        sanitize_trace_metadata(
            {
                "zeta": 1,
                "alpha": 2,
            }
        )
    )

    assert result == (
        (
            "alpha",
            2,
        ),
        (
            "zeta",
            1,
        ),
    )


def test_sanitize_metadata_normalizes_keys():
    result = (
        sanitize_trace_metadata(
            {
                " Stage.Name ": (
                    "alpha"
                )
            }
        )
    )

    assert result == (
        (
            "stage.name",
            "alpha",
        ),
    )


@pytest.mark.parametrize(
    "value",
    (
        None,
        True,
        False,
        0,
        1,
        -1,
        0.5,
        -0.5,
        "safe_label",
        "Model:local",
        "phase-2a",
    ),
)
def test_metadata_accepts_safe_scalar_values(
    value,
):
    result = (
        sanitize_trace_metadata(
            {
                "value": value
            }
        )
    )

    assert (
        result[0][1]
        == value
    )


@pytest.mark.parametrize(
    "value",
    (
        float("nan"),
        float("inf"),
        float("-inf"),
    ),
)
def test_metadata_rejects_nonfinite_float(
    value,
):
    with pytest.raises(
        ValueError,
        match="finite",
    ):
        sanitize_trace_metadata(
            {
                "value": value
            }
        )


@pytest.mark.parametrize(
    "value",
    (
        [],
        {},
        (),
        object(),
        b"bytes",
    ),
)
def test_metadata_rejects_complex_values(
    value,
):
    with pytest.raises(
        TypeError,
        match="scalar",
    ):
        sanitize_trace_metadata(
            {
                "value": value
            }
        )


@pytest.mark.parametrize(
    "value",
    (
        "contains spaces",
        "raw\ntext",
        "path/to/file",
        "hello world!",
    ),
)
def test_metadata_rejects_free_text_strings(
    value,
):
    with pytest.raises(
        ValueError,
        match="identifier-like",
    ):
        sanitize_trace_metadata(
            {
                "value": value
            }
        )


def test_metadata_string_rejects_over_limit():
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        sanitize_trace_metadata(
            {
                "value": (
                    "x"
                    * (
                        TRACE_METADATA_STRING_MAX_CHARS
                        + 1
                    )
                )
            }
        )


def test_metadata_key_rejects_over_limit():
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        sanitize_trace_metadata(
            {
                (
                    "x"
                    * (
                        TRACE_METADATA_KEY_MAX_CHARS
                        + 1
                    )
                ): 1
            }
        )


@pytest.mark.parametrize(
    "key",
    (
        "prompt",
        "user.prompt",
        "message",
        "transcript",
        "command",
        "args",
        "arguments",
        "password",
        "secret",
        "token",
        "api_key",
        "authorization",
        "clipboard",
        "screen",
        "screenshot",
        "response",
        "content",
        "text",
        "memory_context",
        "raw.payload",
        "credentials",
        "file_contents",
    ),
)
def test_metadata_rejects_sensitive_or_raw_keys(
    key,
):
    with pytest.raises(
        ValueError,
        match="sensitive/raw",
    ):
        sanitize_trace_metadata(
            {
                key: "safe"
            }
        )


@pytest.mark.parametrize(
    "value",
    (
        "sk-abcdef",
        "ghp_abcdef",
        "github_pat_abcdef",
        "tvly-abcdef",
        "xoxb-abcdef",
        "AKIA123456",
        "AIza123456",
    ),
)
def test_metadata_rejects_known_secret_like_prefixes(
    value,
):
    with pytest.raises(
        ValueError,
        match="secret-like",
    ):
        sanitize_trace_metadata(
            {
                "provider_state": value
            }
        )


def test_metadata_rejects_too_many_items():
    metadata = {
        f"key{i}": i
        for i in range(
            TRACE_METADATA_MAX_ITEMS
            + 1
        )
    }

    with pytest.raises(
        ValueError,
        match="item count",
    ):
        sanitize_trace_metadata(
            metadata
        )


def test_event_metadata_is_immutable_tuple():
    value = event(
        metadata=(
            (
                "stage_index",
                2,
            ),
        )
    )

    assert isinstance(
        value.metadata,
        tuple,
    )

    assert (
        value.metadata
        == (
            (
                "stage_index",
                2,
            ),
        )
    )


def test_event_rejects_duplicate_metadata_keys():
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        event(
            metadata=(
                (
                    "key",
                    1,
                ),
                (
                    "key",
                    2,
                ),
            )
        )


def test_new_trace_id_is_bounded_and_valid():
    value = (
        new_runtime_trace_id()
    )

    assert value.startswith(
        "trace-"
    )

    assert (
        len(value)
        <= TRACE_ID_MAX_CHARS
    )

    assert (
        event(
            trace_id=value
        ).trace_id
        == value
    )


def test_new_trace_ids_are_distinct():
    assert (
        new_runtime_trace_id()
        != new_runtime_trace_id()
    )


def test_recorder_default_capacity_is_bounded():
    recorder = (
        KumaRuntimeTrace()
    )

    assert (
        recorder.max_events
        == TRACE_DEFAULT_MAX_EVENTS
    )

    assert (
        recorder.max_events
        <= TRACE_MAX_EVENTS
    )


@pytest.mark.parametrize(
    "value",
    (
        0,
        -1,
        TRACE_MAX_EVENTS
        + 1,
        True,
        1.0,
        "10",
    ),
)
def test_recorder_rejects_invalid_capacity(
    value,
):
    with pytest.raises(
        ValueError,
        match="max_events",
    ):
        KumaRuntimeTrace(
            max_events=value
        )


def test_recorder_authority_is_none():
    assert (
        KumaRuntimeTrace().authority
        == "NONE"
    )


def test_recorder_authority_is_read_only():
    recorder = (
        KumaRuntimeTrace()
    )

    with pytest.raises(
        AttributeError
    ):
        recorder.authority = "FULL"


def test_start_trace_uses_injected_factory():
    recorder = (
        KumaRuntimeTrace(
            trace_id_factory=(
                lambda: "trace-fixed"
            )
        )
    )

    assert (
        recorder.start_trace()
        == "trace-fixed"
    )


def test_start_trace_validates_factory_output():
    recorder = (
        KumaRuntimeTrace(
            trace_id_factory=(
                lambda: "raw user text!"
            )
        )
    )

    with pytest.raises(
        ValueError,
        match="identifier-like",
    ):
        recorder.start_trace()


def test_record_uses_injected_monotonic_clock():
    recorder = (
        KumaRuntimeTrace(
            clock_ns=(
                lambda: 12345
            )
        )
    )

    value = recorder.record(
        trace_id="trace-a",
        stage="perception",
        event_kind="stage.started",
    )

    assert (
        value.monotonic_ns
        == 12345
    )


@pytest.mark.parametrize(
    "clock_value",
    (
        True,
        1.0,
        "1",
        -1,
    ),
)
def test_record_rejects_invalid_clock(
    clock_value,
):
    recorder = (
        KumaRuntimeTrace(
            clock_ns=(
                lambda: clock_value
            )
        )
    )

    with pytest.raises(
        TypeError,
        match="monotonic clock",
    ):
        recorder.record(
            trace_id="trace-a",
            stage="perception",
            event_kind="stage.started",
        )


def test_record_assigns_sequence_starting_at_one():
    recorder = (
        KumaRuntimeTrace(
            clock_ns=(
                lambda: 1
            )
        )
    )

    value = recorder.record(
        trace_id="trace-a",
        stage="perception",
        event_kind="stage.started",
    )

    assert (
        value.sequence
        == 1
    )


def test_record_increments_sequence_per_trace():
    ticks = iter(
        (
            10,
            11,
            12,
        )
    )

    recorder = (
        KumaRuntimeTrace(
            clock_ns=(
                lambda: next(
                    ticks
                )
            )
        )
    )

    first = recorder.record(
        trace_id="trace-a",
        stage="perception",
        event_kind="stage.started",
    )

    second = recorder.record(
        trace_id="trace-a",
        stage="perception",
        event_kind="stage.finished",
    )

    third = recorder.record(
        trace_id="trace-b",
        stage="cognition",
        event_kind="stage.started",
    )

    assert (
        first.sequence,
        second.sequence,
        third.sequence,
    ) == (
        1,
        2,
        1,
    )


def test_record_preserves_zero_authority():
    recorder = (
        KumaRuntimeTrace(
            clock_ns=(
                lambda: 1
            )
        )
    )

    value = recorder.record(
        trace_id="trace-a",
        stage="authority",
        event_kind="gate.observed",
        outcome="blocked",
    )

    assert (
        value.authority
        == "NONE"
    )


def test_record_sanitizes_metadata():
    recorder = (
        KumaRuntimeTrace(
            clock_ns=(
                lambda: 1
            )
        )
    )

    value = recorder.record(
        trace_id="trace-a",
        stage="execution",
        event_kind="tool.finished",
        metadata={
            "Tool.Name": (
                "open_app"
            ),
            "attempt": 2,
        },
    )

    assert value.metadata == (
        (
            "attempt",
            2,
        ),
        (
            "tool.name",
            "open_app",
        ),
    )


def test_record_rejects_raw_prompt_metadata():
    recorder = (
        KumaRuntimeTrace(
            clock_ns=(
                lambda: 1
            )
        )
    )

    with pytest.raises(
        ValueError,
        match="sensitive/raw",
    ):
        recorder.record(
            trace_id="trace-a",
            stage="cognition",
            event_kind="model.observed",
            metadata={
                "prompt": (
                    "do_not_store_me"
                )
            },
        )


def test_append_accepts_exact_next_event():
    recorder = (
        KumaRuntimeTrace()
    )

    value = event()

    assert (
        recorder.append(
            value
        )
        is value
    )


def test_append_rejects_non_event():
    recorder = (
        KumaRuntimeTrace()
    )

    with pytest.raises(
        TypeError,
        match="RuntimeTraceEvent",
    ):
        recorder.append(
            object()
        )


def test_append_rejects_sequence_gap():
    recorder = (
        KumaRuntimeTrace()
    )

    with pytest.raises(
        ValueError,
        match="sequence",
    ):
        recorder.append(
            event(
                sequence=2
            )
        )


def test_append_rejects_sequence_replay():
    recorder = (
        KumaRuntimeTrace()
    )

    recorder.append(
        event()
    )

    with pytest.raises(
        ValueError,
        match="sequence",
    ):
        recorder.append(
            event(
                monotonic_ns=101
            )
        )


def test_append_rejects_monotonic_time_reversal():
    recorder = (
        KumaRuntimeTrace()
    )

    recorder.append(
        event(
            monotonic_ns=100
        )
    )

    with pytest.raises(
        ValueError,
        match="backwards",
    ):
        recorder.append(
            event(
                sequence=2,
                monotonic_ns=99,
            )
        )


def test_append_accepts_equal_monotonic_timestamp():
    recorder = (
        KumaRuntimeTrace()
    )

    recorder.append(
        event(
            monotonic_ns=100
        )
    )

    second = recorder.append(
        event(
            sequence=2,
            monotonic_ns=100,
        )
    )

    assert (
        second.sequence
        == 2
    )


def test_snapshot_returns_immutable_tuple():
    recorder = (
        KumaRuntimeTrace()
    )

    recorder.append(
        event()
    )

    result = recorder.snapshot()

    assert isinstance(
        result,
        tuple,
    )

    assert (
        result
        == (
            event(),
        )
    )


def test_snapshot_is_fresh():
    recorder = (
        KumaRuntimeTrace()
    )

    recorder.append(
        event()
    )

    first = recorder.snapshot()
    second = recorder.snapshot()

    assert first == second
    assert first is not second


def test_events_for_trace_filters_exact_trace():
    recorder = (
        KumaRuntimeTrace()
    )

    recorder.append(
        event(
            trace_id="trace-a",
        )
    )

    recorder.append(
        event(
            trace_id="trace-b",
            monotonic_ns=101,
        )
    )

    result = (
        recorder.events_for_trace(
            "trace-a"
        )
    )

    assert (
        len(result)
        == 1
    )

    assert (
        result[0].trace_id
        == "trace-a"
    )


def test_events_for_trace_validates_id():
    recorder = (
        KumaRuntimeTrace()
    )

    with pytest.raises(
        ValueError
    ):
        recorder.events_for_trace(
            "raw trace text!"
        )


def test_recorder_evicts_oldest_event_at_capacity():
    recorder = (
        KumaRuntimeTrace(
            max_events=2
        )
    )

    recorder.append(
        event(
            trace_id="trace-a",
            monotonic_ns=1,
        )
    )

    recorder.append(
        event(
            trace_id="trace-b",
            monotonic_ns=2,
        )
    )

    recorder.append(
        event(
            trace_id="trace-c",
            monotonic_ns=3,
        )
    )

    result = (
        recorder.snapshot()
    )

    assert [
        item.trace_id
        for item in result
    ] == [
        "trace-b",
        "trace-c",
    ]


def test_eviction_does_not_reset_trace_sequence():
    recorder = (
        KumaRuntimeTrace(
            max_events=1
        )
    )

    recorder.append(
        event(
            trace_id="trace-a",
            monotonic_ns=1,
        )
    )

    recorder.append(
        event(
            trace_id="trace-b",
            monotonic_ns=2,
        )
    )

    third = recorder.append(
        event(
            trace_id="trace-a",
            sequence=2,
            monotonic_ns=3,
        )
    )

    assert (
        third.sequence
        == 2
    )


def test_clear_removes_events():
    recorder = (
        KumaRuntimeTrace()
    )

    recorder.append(
        event()
    )

    recorder.clear()

    assert (
        recorder.snapshot()
        == ()
    )

    assert (
        len(
            recorder
        )
        == 0
    )


def test_clear_resets_sequence_state():
    recorder = (
        KumaRuntimeTrace()
    )

    recorder.append(
        event()
    )

    recorder.clear()

    value = recorder.append(
        event(
            monotonic_ns=1
        )
    )

    assert (
        value.sequence
        == 1
    )


def test_len_tracks_bounded_buffer():
    recorder = (
        KumaRuntimeTrace(
            max_events=2
        )
    )

    assert (
        len(
            recorder
        )
        == 0
    )

    recorder.append(
        event(
            trace_id="trace-a",
        )
    )

    recorder.append(
        event(
            trace_id="trace-b",
            monotonic_ns=101,
        )
    )

    recorder.append(
        event(
            trace_id="trace-c",
            monotonic_ns=102,
        )
    )

    assert (
        len(
            recorder
        )
        == 2
    )


def test_module_imports_only_stdlib():
    loaded = imports()

    assert not any(
        name.startswith(
            "app."
        )
        for name in loaded
    )


def test_module_has_no_network_imports():
    loaded = imports()

    forbidden = {
        "requests",
        "httpx",
        "urllib",
        "socket",
        "aiohttp",
        "websockets",
    }

    roots = {
        name.split(
            ".",
            1,
        )[0]
        for name in loaded
    }

    assert roots.isdisjoint(
        forbidden
    )


def test_module_has_no_persistence_imports():
    loaded = imports()

    forbidden = {
        "sqlite3",
        "pathlib",
        "tempfile",
        "shelve",
    }

    roots = {
        name.split(
            ".",
            1,
        )[0]
        for name in loaded
    }

    assert roots.isdisjoint(
        forbidden
    )


def test_module_has_no_model_provider_imports():
    text = (
        MODULE.read_text()
        .lower()
    )

    for forbidden in (
        "google.genai",
        "openai",
        "ollama",
        "anthropic",
    ):
        assert forbidden not in text


def test_module_has_no_permission_execution_surface():
    text = (
        MODULE.read_text()
    )

    for forbidden in (
        "request_confirmation(",
        "require_explicit_permission(",
        "register_tool(",
        ".execute(",
        "ActionExecutor",
        "PermissionLevel",
        "TaskState",
    ):
        assert forbidden not in text


def test_module_has_no_background_loop():
    text = (
        MODULE.read_text()
    )

    assert (
        "while True"
        not in text
    )

    assert (
        "Thread("
        not in text
    )

    assert (
        "QThread"
        not in text
    )

    assert (
        "QTimer"
        not in text
    )


def test_module_uses_lock_not_background_worker():
    text = (
        MODULE.read_text()
    )

    assert (
        "RLock"
        in text
    )

    assert (
        "threading.Thread"
        not in text
    )


def test_event_contract_has_no_raw_payload_fields():
    names = {
        item.name
        for item in fields(
            RuntimeTraceEvent
        )
    }

    for forbidden in (
        "prompt",
        "message",
        "transcript",
        "command",
        "arguments",
        "args",
        "clipboard",
        "screen",
        "screenshot",
        "response",
        "content",
        "text",
        "memory_context",
        "payload",
    ):
        assert forbidden not in names


def test_recorder_has_no_authority_input():
    signature = (
        inspect.signature(
            KumaRuntimeTrace
        )
    )

    assert (
        "authority"
        not in signature.parameters
    )


def test_record_has_no_authority_input():
    signature = (
        inspect.signature(
            KumaRuntimeTrace.record
        )
    )

    assert (
        "authority"
        not in signature.parameters
    )

    assert (
        "permission"
        not in signature.parameters
    )


def test_start_trace_has_no_user_content_input():
    signature = (
        inspect.signature(
            KumaRuntimeTrace.start_trace
        )
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
    )


def test_contract_documents_core_boundaries():
    text = (
        MODULE.read_text()
    )

    for required in (
        "TRACE != AUTHORITY",
        "TRACE != COMMAND",
        "TRACE != VERIFIED FACT",
        "OBSERVED != AUTHORIZED",
        "LOGGED RESULT != GOAL COMPLETION",
        "DIAGNOSTIC DATA != MODEL CONTEXT",
        "TRACE STORAGE != LONG-TERM MEMORY",
        "TRACE METADATA != RAW USER CONTENT",
        "TRACE AUTHORITY = NONE",
    ):
        assert required in text


def test_contract_documents_no_disk_network_or_model():
    text = (
        MODULE.read_text()
    )

    for required in (
        "no disk persistence",
        "no network",
        "no model/provider imports",
        "no background loop",
    ):
        assert required in text


def test_contract_documents_fail_closed_metadata():
    text = (
        MODULE.read_text()
    )

    assert (
        "fail-closed"
        in text
    )

    assert (
        "rejected"
        in text
    )


def test_outcome_documentation_denies_goal_completion_claim():
    text = (
        inspect.getdoc(
            RuntimeTraceEvent
        )
        or ""
    )

    assert (
        "never means"
        in text
    )

    assert (
        "verified complete"
        in text
    )


def test_module_compiles():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
