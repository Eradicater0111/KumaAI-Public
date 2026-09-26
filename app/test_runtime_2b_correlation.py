from __future__ import annotations

import ast
from dataclasses import (
    FrozenInstanceError,
    fields,
)
import inspect
from pathlib import Path

import pytest

from app.runtime_correlation import (
    CORRELATION_AUTHORITY_NONE,
    CORRELATION_ID_MAX_CHARS,
    KumaRuntimeCorrelation,
    RuntimeTurnClosure,
    RuntimeTurnCorrelation,
    RuntimeTurnEndKind,
    correlation_metadata,
    new_runtime_session_id,
    new_runtime_turn_id,
)
from app.runtime_trace import (
    KumaRuntimeTrace,
    RuntimeTraceEvent,
)


MODULE = Path(
    "app/runtime_correlation.py"
)

TRACE_MODULE = Path(
    "app/runtime_trace.py"
)


def make_trace(
    ticks=(
        100,
        200,
        300,
        400,
        500,
        600,
        700,
        800,
    ),
    trace_ids=(
        "trace-a",
        "trace-b",
        "trace-c",
        "trace-d",
    ),
):
    tick_iterator = iter(
        ticks
    )

    trace_iterator = iter(
        trace_ids
    )

    return KumaRuntimeTrace(
        clock_ns=(
            lambda: next(
                tick_iterator
            )
        ),
        trace_id_factory=(
            lambda: next(
                trace_iterator
            )
        ),
    )


def make_manager(
    *,
    trace=None,
    session_ids=(
        "session-a",
    ),
    turn_ids=(
        "turn-a",
        "turn-b",
        "turn-c",
        "turn-d",
    ),
):
    session_iterator = iter(
        session_ids
    )

    turn_iterator = iter(
        turn_ids
    )

    return KumaRuntimeCorrelation(
        trace=(
            trace
            if trace is not None
            else make_trace()
        ),
        session_id_factory=(
            lambda: next(
                session_iterator
            )
        ),
        turn_id_factory=(
            lambda: next(
                turn_iterator
            )
        ),
    )


def context(
    **overrides,
):
    values = {
        "session_id": "session-a",
        "turn_id": "turn-a",
        "trace_id": "trace-a",
        "turn_index": 1,
        "started_monotonic_ns": 100,
    }

    values.update(
        overrides
    )

    return RuntimeTurnCorrelation(
        **values
    )


def closure(
    **overrides,
):
    values = {
        "context": context(),
        "end_kind": (
            RuntimeTurnEndKind.RESPONSE
        ),
        "ended_monotonic_ns": 200,
        "duration_ms": 0.0001,
    }

    values.update(
        overrides
    )

    return RuntimeTurnClosure(
        **values
    )


def imports():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    result = set()

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
            result.add(
                node.module
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            result.update(
                alias.name
                for alias in node.names
            )

    return result


def test_authority_constant_is_none():
    assert (
        CORRELATION_AUTHORITY_NONE
        == "NONE"
    )


def test_turn_end_kinds_are_exact():
    assert {
        value.value
        for value in RuntimeTurnEndKind
    } == {
        "response",
        "error",
        "blocked",
        "cancelled",
    }


@pytest.mark.parametrize(
    (
        "member",
        "expected",
    ),
    (
        (
            RuntimeTurnEndKind.RESPONSE,
            "response",
        ),
        (
            RuntimeTurnEndKind.ERROR,
            "error",
        ),
        (
            RuntimeTurnEndKind.BLOCKED,
            "blocked",
        ),
        (
            RuntimeTurnEndKind.CANCELLED,
            "cancelled",
        ),
    ),
)
def test_turn_end_kind_values(
    member,
    expected,
):
    assert (
        member.value
        == expected
    )


def test_correlation_fields_are_exact():
    assert tuple(
        value.name
        for value in fields(
            RuntimeTurnCorrelation
        )
    ) == (
        "session_id",
        "turn_id",
        "trace_id",
        "turn_index",
        "started_monotonic_ns",
        "authority",
    )


def test_closure_fields_are_exact():
    assert tuple(
        value.name
        for value in fields(
            RuntimeTurnClosure
        )
    ) == (
        "context",
        "end_kind",
        "ended_monotonic_ns",
        "duration_ms",
        "authority",
    )


def test_correlation_authority_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            RuntimeTurnCorrelation
        ).parameters
    )


def test_closure_authority_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            RuntimeTurnClosure
        ).parameters
    )


def test_correlation_is_frozen():
    value = context()

    with pytest.raises(
        FrozenInstanceError
    ):
        value.turn_id = "turn-b"


def test_closure_is_frozen():
    value = closure()

    with pytest.raises(
        FrozenInstanceError
    ):
        value.duration_ms = 1.0


def test_correlation_is_slotted():
    assert not hasattr(
        context(),
        "__dict__",
    )


def test_closure_is_slotted():
    assert not hasattr(
        closure(),
        "__dict__",
    )


def test_correlation_authority_is_none():
    assert (
        context().authority
        == "NONE"
    )


def test_closure_authority_is_none():
    assert (
        closure().authority
        == "NONE"
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "session_id",
        "turn_id",
        "trace_id",
    ),
)
def test_identifiers_trim_outer_whitespace(
    field_name,
):
    value = context(
        **{
            field_name: "  token-a  "
        }
    )

    assert (
        getattr(
            value,
            field_name,
        )
        == "token-a"
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "session_id",
        "turn_id",
        "trace_id",
    ),
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
def test_identifiers_require_string(
    field_name,
    value,
):
    with pytest.raises(
        TypeError
    ):
        context(
            **{
                field_name: value
            }
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "session_id",
        "turn_id",
        "trace_id",
    ),
)
@pytest.mark.parametrize(
    "value",
    (
        "",
        "   ",
    ),
)
def test_identifiers_reject_blank(
    field_name,
    value,
):
    with pytest.raises(
        ValueError,
        match="nonempty",
    ):
        context(
            **{
                field_name: value
            }
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "session_id",
        "turn_id",
        "trace_id",
    ),
)
@pytest.mark.parametrize(
    "value",
    (
        "contains spaces",
        "prompt/goes/here",
        "text?query",
        "line\nbreak",
    ),
)
def test_identifiers_reject_non_opaque_content(
    field_name,
    value,
):
    with pytest.raises(
        ValueError,
        match="opaque",
    ):
        context(
            **{
                field_name: value
            }
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "session_id",
        "turn_id",
        "trace_id",
    ),
)
def test_identifiers_reject_over_limit(
    field_name,
):
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        context(
            **{
                field_name: (
                    "x"
                    * (
                        CORRELATION_ID_MAX_CHARS
                        + 1
                    )
                )
            }
        )


def test_identifier_accepts_exact_limit():
    value = context(
        session_id=(
            "s"
            * CORRELATION_ID_MAX_CHARS
        )
    )

    assert (
        len(
            value.session_id
        )
        == CORRELATION_ID_MAX_CHARS
    )


@pytest.mark.parametrize(
    "value",
    (
        0,
        -1,
        True,
        1.0,
        "1",
        None,
    ),
)
def test_turn_index_requires_positive_exact_int(
    value,
):
    with pytest.raises(
        TypeError,
        match="turn_index",
    ):
        context(
            turn_index=value
        )


@pytest.mark.parametrize(
    "value",
    (
        -1,
        True,
        1.0,
        "1",
        None,
    ),
)
def test_started_timestamp_requires_nonnegative_exact_int(
    value,
):
    with pytest.raises(
        TypeError,
        match="started_monotonic_ns",
    ):
        context(
            started_monotonic_ns=value
        )


def test_started_timestamp_accepts_zero():
    assert (
        context(
            started_monotonic_ns=0
        ).started_monotonic_ns
        == 0
    )


def test_closure_requires_context():
    with pytest.raises(
        TypeError,
        match="RuntimeTurnCorrelation",
    ):
        closure(
            context=object()
        )


@pytest.mark.parametrize(
    "value",
    (
        "response",
        None,
        1,
    ),
)
def test_closure_requires_enum_end_kind(
    value,
):
    with pytest.raises(
        TypeError,
        match="RuntimeTurnEndKind",
    ):
        closure(
            end_kind=value
        )


@pytest.mark.parametrize(
    "value",
    (
        -1,
        True,
        1.0,
        "1",
        None,
    ),
)
def test_closure_end_timestamp_requires_nonnegative_exact_int(
    value,
):
    with pytest.raises(
        TypeError,
        match="ended_monotonic_ns",
    ):
        closure(
            ended_monotonic_ns=value
        )


@pytest.mark.parametrize(
    "value",
    (
        True,
        False,
        "1",
        None,
        object(),
    ),
)
def test_closure_duration_requires_numeric(
    value,
):
    with pytest.raises(
        TypeError,
        match="duration_ms",
    ):
        closure(
            duration_ms=value
        )


@pytest.mark.parametrize(
    "value",
    (
        -0.1,
        float("inf"),
        float("-inf"),
        float("nan"),
    ),
)
def test_closure_duration_rejects_invalid_number(
    value,
):
    with pytest.raises(
        ValueError,
        match="duration_ms",
    ):
        closure(
            duration_ms=value
        )


def test_closure_rejects_end_before_start():
    with pytest.raises(
        ValueError,
        match="before",
    ):
        closure(
            ended_monotonic_ns=99,
        )


def test_closure_accepts_zero_duration():
    value = closure(
        ended_monotonic_ns=100,
        duration_ms=0,
    )

    assert (
        value.duration_ms
        == 0.0
    )


def test_new_session_id_has_session_prefix():
    assert (
        new_runtime_session_id()
        .startswith(
            "session-"
        )
    )


def test_new_turn_id_has_turn_prefix():
    assert (
        new_runtime_turn_id()
        .startswith(
            "turn-"
        )
    )


def test_new_session_ids_are_distinct():
    assert (
        new_runtime_session_id()
        != new_runtime_session_id()
    )


def test_new_turn_ids_are_distinct():
    assert (
        new_runtime_turn_id()
        != new_runtime_turn_id()
    )


def test_generated_session_id_is_bounded():
    assert (
        len(
            new_runtime_session_id()
        )
        <= CORRELATION_ID_MAX_CHARS
    )


def test_generated_turn_id_is_bounded():
    assert (
        len(
            new_runtime_turn_id()
        )
        <= CORRELATION_ID_MAX_CHARS
    )


def test_correlation_metadata_is_immutable_mapping():
    metadata = (
        correlation_metadata(
            context()
        )
    )

    with pytest.raises(
        TypeError
    ):
        metadata[
            "session.id"
        ] = "session-b"


def test_correlation_metadata_is_exact():
    metadata = dict(
        correlation_metadata(
            context()
        )
    )

    assert metadata == {
        "session.id": "session-a",
        "turn.id": "turn-a",
        "turn.index": 1,
    }


def test_correlation_metadata_requires_context():
    with pytest.raises(
        TypeError,
        match="RuntimeTurnCorrelation",
    ):
        correlation_metadata(
            object()
        )


def test_manager_creates_one_session_identity():
    manager = (
        make_manager()
    )

    assert (
        manager.session_id
        == "session-a"
    )


def test_manager_authority_is_none():
    assert (
        make_manager().authority
        == "NONE"
    )


def test_manager_starts_open():
    manager = (
        make_manager()
    )

    assert (
        manager.closed
        is False
    )


def test_manager_starts_without_active_turn():
    manager = (
        make_manager()
    )

    assert (
        manager.active_turn
        is None
    )


def test_manager_starts_without_closure():
    manager = (
        make_manager()
    )

    assert (
        manager.last_closure
        is None
    )


def test_manager_starts_with_zero_turn_count():
    assert (
        make_manager().turn_count
        == 0
    )


def test_manager_construction_does_not_record_trace_event():
    manager = (
        make_manager()
    )

    assert (
        manager.trace.snapshot()
        == ()
    )


def test_manager_trace_property_returns_exact_recorder():
    trace = make_trace()

    manager = (
        make_manager(
            trace=trace
        )
    )

    assert (
        manager.trace
        is trace
    )


def test_manager_trace_property_is_read_only():
    manager = (
        make_manager()
    )

    with pytest.raises(
        AttributeError
    ):
        manager.trace = make_trace()


def test_manager_session_id_is_read_only():
    manager = (
        make_manager()
    )

    with pytest.raises(
        AttributeError
    ):
        manager.session_id = "session-b"


def test_manager_rejects_invalid_trace():
    with pytest.raises(
        TypeError,
        match="KumaRuntimeTrace",
    ):
        KumaRuntimeCorrelation(
            trace=object()
        )


@pytest.mark.parametrize(
    "name",
    (
        "session_id_factory",
        "turn_id_factory",
    ),
)
def test_manager_requires_callable_factories(
    name,
):
    values = {
        "session_id_factory": (
            lambda: "session-a"
        ),
        "turn_id_factory": (
            lambda: "turn-a"
        ),
    }

    values[name] = object()

    with pytest.raises(
        TypeError,
        match=name,
    ):
        KumaRuntimeCorrelation(
            **values
        )


def test_manager_validates_session_factory_output():
    with pytest.raises(
        ValueError,
        match="opaque",
    ):
        KumaRuntimeCorrelation(
            session_id_factory=(
                lambda: (
                    "user identity in session"
                )
            )
        )


def test_begin_turn_returns_correlation():
    manager = (
        make_manager()
    )

    value = (
        manager.begin_turn()
    )

    assert isinstance(
        value,
        RuntimeTurnCorrelation,
    )


def test_begin_turn_binds_manager_session():
    manager = (
        make_manager()
    )

    value = (
        manager.begin_turn()
    )

    assert (
        value.session_id
        == manager.session_id
    )


def test_begin_turn_uses_turn_factory():
    manager = (
        make_manager()
    )

    assert (
        manager.begin_turn()
        .turn_id
        == "turn-a"
    )


def test_begin_turn_uses_trace_factory():
    manager = (
        make_manager()
    )

    assert (
        manager.begin_turn()
        .trace_id
        == "trace-a"
    )


def test_begin_turn_starts_index_at_one():
    manager = (
        make_manager()
    )

    assert (
        manager.begin_turn()
        .turn_index
        == 1
    )


def test_begin_turn_uses_trace_event_timestamp():
    manager = (
        make_manager()
    )

    assert (
        manager.begin_turn()
        .started_monotonic_ns
        == 100
    )


def test_begin_turn_sets_active_turn():
    manager = (
        make_manager()
    )

    value = (
        manager.begin_turn()
    )

    assert (
        manager.active_turn
        is value
    )


def test_begin_turn_increments_turn_count():
    manager = (
        make_manager()
    )

    manager.begin_turn()

    assert (
        manager.turn_count
        == 1
    )


def test_begin_turn_records_one_started_event():
    manager = (
        make_manager()
    )

    value = (
        manager.begin_turn()
    )

    events = (
        manager.trace
        .events_for_trace(
            value.trace_id
        )
    )

    assert (
        len(events)
        == 1
    )

    assert (
        events[0].event_kind
        == "turn.started"
    )


def test_started_event_has_correlation_stage():
    manager = (
        make_manager()
    )

    value = (
        manager.begin_turn()
    )

    event = (
        manager.trace
        .events_for_trace(
            value.trace_id
        )[0]
    )

    assert (
        event.stage
        == "correlation"
    )


def test_started_event_authority_is_none():
    manager = (
        make_manager()
    )

    value = (
        manager.begin_turn()
    )

    event = (
        manager.trace
        .events_for_trace(
            value.trace_id
        )[0]
    )

    assert (
        event.authority
        == "NONE"
    )


def test_started_event_metadata_is_structural_only():
    manager = (
        make_manager()
    )

    value = (
        manager.begin_turn()
    )

    event = (
        manager.trace
        .events_for_trace(
            value.trace_id
        )[0]
    )

    assert dict(
        event.metadata
    ) == {
        "session.id": "session-a",
        "turn.id": "turn-a",
        "turn.index": 1,
    }


def test_begin_turn_rejects_second_active_turn():
    manager = (
        make_manager()
    )

    manager.begin_turn()

    with pytest.raises(
        RuntimeError,
        match="already active",
    ):
        manager.begin_turn()


def test_rejected_second_turn_does_not_increment_count():
    manager = (
        make_manager()
    )

    manager.begin_turn()

    with pytest.raises(
        RuntimeError
    ):
        manager.begin_turn()

    assert (
        manager.turn_count
        == 1
    )


def test_rejected_second_turn_does_not_create_second_trace():
    manager = (
        make_manager()
    )

    manager.begin_turn()

    with pytest.raises(
        RuntimeError
    ):
        manager.begin_turn()

    assert (
        len(
            manager.trace.snapshot()
        )
        == 1
    )


def test_duplicate_turn_id_fails_closed():
    manager = (
        KumaRuntimeCorrelation(
            trace=make_trace(),
            session_id_factory=(
                lambda: "session-a"
            ),
            turn_id_factory=(
                lambda: "turn-a"
            ),
        )
    )

    first = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=first.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        manager.begin_turn()


def test_duplicate_trace_id_fails_closed():
    ticks = iter(
        (
            100,
            200,
            300,
        )
    )

    trace = KumaRuntimeTrace(
        clock_ns=(
            lambda: next(
                ticks
            )
        ),
        trace_id_factory=(
            lambda: "trace-a"
        ),
    )

    manager = (
        KumaRuntimeCorrelation(
            trace=trace,
            session_id_factory=(
                lambda: "session-a"
            ),
            turn_id_factory=iter(
                (
                    "turn-a",
                    "turn-b",
                )
            ).__next__,
        )
    )

    first = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=first.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        manager.begin_turn()


@pytest.mark.parametrize(
    "end_kind",
    tuple(
        RuntimeTurnEndKind
    ),
)
def test_every_terminal_kind_ends_active_turn(
    end_kind,
):
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    result = (
        manager.end_turn(
            turn_id=active.turn_id,
            end_kind=end_kind,
        )
    )

    assert (
        result.end_kind
        is end_kind
    )

    assert (
        manager.active_turn
        is None
    )


def test_response_terminal_does_not_name_goal_completion():
    assert (
        RuntimeTurnEndKind.RESPONSE
        .value
        == "response"
    )

    assert (
        "complete"
        not in RuntimeTurnEndKind.RESPONSE.value
    )


def test_end_turn_requires_active_turn():
    manager = (
        make_manager()
    )

    with pytest.raises(
        RuntimeError,
        match="no runtime turn",
    ):
        manager.end_turn(
            turn_id="turn-a",
            end_kind=(
                RuntimeTurnEndKind.RESPONSE
            ),
        )


def test_end_turn_rejects_stale_turn_id():
    manager = (
        make_manager()
    )

    manager.begin_turn()

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        manager.end_turn(
            turn_id="turn-stale",
            end_kind=(
                RuntimeTurnEndKind.RESPONSE
            ),
        )


def test_stale_turn_id_does_not_end_active_turn():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    with pytest.raises(
        ValueError
    ):
        manager.end_turn(
            turn_id="turn-stale",
            end_kind=(
                RuntimeTurnEndKind.ERROR
            ),
        )

    assert (
        manager.active_turn
        is active
    )


def test_end_turn_requires_enum():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    with pytest.raises(
        TypeError,
        match="RuntimeTurnEndKind",
    ):
        manager.end_turn(
            turn_id=active.turn_id,
            end_kind="error",
        )


def test_invalid_end_kind_does_not_end_active_turn():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    with pytest.raises(
        TypeError
    ):
        manager.end_turn(
            turn_id=active.turn_id,
            end_kind="error",
        )

    assert (
        manager.active_turn
        is active
    )


def test_end_turn_returns_closure():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    result = (
        manager.end_turn(
            turn_id=active.turn_id,
            end_kind=(
                RuntimeTurnEndKind.RESPONSE
            ),
        )
    )

    assert isinstance(
        result,
        RuntimeTurnClosure,
    )


def test_end_turn_closure_carries_exact_context():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    result = (
        manager.end_turn(
            turn_id=active.turn_id,
            end_kind=(
                RuntimeTurnEndKind.ERROR
            ),
        )
    )

    assert (
        result.context
        is active
    )


def test_end_turn_uses_end_event_timestamp():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    result = (
        manager.end_turn(
            turn_id=active.turn_id,
            end_kind=(
                RuntimeTurnEndKind.RESPONSE
            ),
        )
    )

    assert (
        result.ended_monotonic_ns
        == 200
    )


def test_end_turn_computes_duration_from_trace_clock():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    result = (
        manager.end_turn(
            turn_id=active.turn_id,
            end_kind=(
                RuntimeTurnEndKind.RESPONSE
            ),
        )
    )

    assert (
        result.duration_ms
        == pytest.approx(
            0.0001
        )
    )


def test_end_turn_updates_last_closure():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    result = (
        manager.end_turn(
            turn_id=active.turn_id,
            end_kind=(
                RuntimeTurnEndKind.BLOCKED
            ),
        )
    )

    assert (
        manager.last_closure
        is result
    )


def test_end_turn_records_ended_event():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=active.turn_id,
        end_kind=(
            RuntimeTurnEndKind.ERROR
        ),
    )

    events = (
        manager.trace
        .events_for_trace(
            active.trace_id
        )
    )

    assert [
        value.event_kind
        for value in events
    ] == [
        "turn.started",
        "turn.ended",
    ]


def test_ended_event_sequence_is_two():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=active.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    events = (
        manager.trace
        .events_for_trace(
            active.trace_id
        )
    )

    assert [
        value.sequence
        for value in events
    ] == [
        1,
        2,
    ]


@pytest.mark.parametrize(
    "end_kind",
    tuple(
        RuntimeTurnEndKind
    ),
)
def test_ended_event_outcome_matches_terminal_kind(
    end_kind,
):
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=active.turn_id,
        end_kind=end_kind,
    )

    event = (
        manager.trace
        .events_for_trace(
            active.trace_id
        )[-1]
    )

    assert (
        event.outcome
        == end_kind.value
    )


def test_ended_event_metadata_includes_end_kind():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=active.turn_id,
        end_kind=(
            RuntimeTurnEndKind.BLOCKED
        ),
    )

    event = (
        manager.trace
        .events_for_trace(
            active.trace_id
        )[-1]
    )

    assert (
        dict(
            event.metadata
        )[
            "turn.end_kind"
        ]
        == "blocked"
    )


def test_ended_event_authority_is_none():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=active.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    event = (
        manager.trace
        .events_for_trace(
            active.trace_id
        )[-1]
    )

    assert (
        event.authority
        == "NONE"
    )


def test_new_turn_after_terminal_gets_new_turn_id():
    manager = (
        make_manager()
    )

    first = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=first.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    second = (
        manager.begin_turn()
    )

    assert (
        second.turn_id
        != first.turn_id
    )


def test_new_turn_after_terminal_gets_new_trace_id():
    manager = (
        make_manager()
    )

    first = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=first.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    second = (
        manager.begin_turn()
    )

    assert (
        second.trace_id
        != first.trace_id
    )


def test_session_spans_multiple_turns():
    manager = (
        make_manager()
    )

    first = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=first.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    second = (
        manager.begin_turn()
    )

    assert (
        first.session_id
        == second.session_id
        == manager.session_id
    )


def test_turn_index_increments_across_session():
    manager = (
        make_manager()
    )

    first = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=first.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    second = (
        manager.begin_turn()
    )

    assert (
        first.turn_index,
        second.turn_index,
    ) == (
        1,
        2,
    )


def test_two_turns_have_disjoint_trace_event_sets():
    manager = (
        make_manager()
    )

    first = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=first.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    second = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=second.turn_id,
        end_kind=(
            RuntimeTurnEndKind.ERROR
        ),
    )

    first_events = (
        manager.trace
        .events_for_trace(
            first.trace_id
        )
    )

    second_events = (
        manager.trace
        .events_for_trace(
            second.trace_id
        )
    )

    assert first_events
    assert second_events

    assert not (
        set(
            first_events
        )
        & set(
            second_events
        )
    )


def test_events_for_session_returns_all_session_turn_events():
    manager = (
        make_manager()
    )

    first = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=first.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    second = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=second.turn_id,
        end_kind=(
            RuntimeTurnEndKind.ERROR
        ),
    )

    assert (
        len(
            manager.events_for_session()
        )
        == 4
    )


def test_events_for_turn_filters_exact_turn():
    manager = (
        make_manager()
    )

    first = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=first.turn_id,
        end_kind=(
            RuntimeTurnEndKind.RESPONSE
        ),
    )

    second = (
        manager.begin_turn()
    )

    manager.end_turn(
        turn_id=second.turn_id,
        end_kind=(
            RuntimeTurnEndKind.ERROR
        ),
    )

    first_events = (
        manager.events_for_turn(
            first.turn_id
        )
    )

    assert (
        len(first_events)
        == 2
    )

    assert all(
        dict(
            value.metadata
        )[
            "turn.id"
        ]
        == first.turn_id
        for value in first_events
    )


def test_events_for_turn_rejects_free_text_identifier():
    manager = (
        make_manager()
    )

    with pytest.raises(
        ValueError,
        match="opaque",
    ):
        manager.events_for_turn(
            "the user's prompt"
        )


def test_close_empty_session_returns_none():
    manager = (
        make_manager()
    )

    assert (
        manager.close_session()
        is None
    )


def test_close_empty_session_marks_closed():
    manager = (
        make_manager()
    )

    manager.close_session()

    assert (
        manager.closed
        is True
    )


def test_close_session_is_idempotent():
    manager = (
        make_manager()
    )

    manager.close_session()

    assert (
        manager.close_session()
        is None
    )

    assert (
        manager.closed
        is True
    )


def test_close_active_session_cancels_turn():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    result = (
        manager.close_session()
    )

    assert (
        result.context
        is active
    )

    assert (
        result.end_kind
        is RuntimeTurnEndKind.CANCELLED
    )


def test_close_active_session_clears_active_turn():
    manager = (
        make_manager()
    )

    manager.begin_turn()

    manager.close_session()

    assert (
        manager.active_turn
        is None
    )


def test_close_active_session_records_cancelled_terminal():
    manager = (
        make_manager()
    )

    active = (
        manager.begin_turn()
    )

    manager.close_session()

    events = (
        manager.trace
        .events_for_trace(
            active.trace_id
        )
    )

    assert (
        events[-1].outcome
        == "cancelled"
    )


def test_closed_session_rejects_new_turn():
    manager = (
        make_manager()
    )

    manager.close_session()

    with pytest.raises(
        RuntimeError,
        match="closed",
    ):
        manager.begin_turn()


def test_closed_session_does_not_increment_turn_count():
    manager = (
        make_manager()
    )

    manager.close_session()

    with pytest.raises(
        RuntimeError
    ):
        manager.begin_turn()

    assert (
        manager.turn_count
        == 0
    )


def test_trace_clock_reversal_fails_end_and_keeps_turn_active():
    ticks = iter(
        (
            200,
            100,
        )
    )

    trace = KumaRuntimeTrace(
        clock_ns=(
            lambda: next(
                ticks
            )
        ),
        trace_id_factory=(
            lambda: "trace-a"
        ),
    )

    manager = (
        KumaRuntimeCorrelation(
            trace=trace,
            session_id_factory=(
                lambda: "session-a"
            ),
            turn_id_factory=(
                lambda: "turn-a"
            ),
        )
    )

    active = (
        manager.begin_turn()
    )

    with pytest.raises(
        ValueError,
        match="backwards",
    ):
        manager.end_turn(
            turn_id=active.turn_id,
            end_kind=(
                RuntimeTurnEndKind.ERROR
            ),
        )

    assert (
        manager.active_turn
        is active
    )

    assert (
        manager.closed
        is False
    )


def test_manager_begin_turn_signature_accepts_no_user_content():
    signature = (
        inspect.signature(
            KumaRuntimeCorrelation
            .begin_turn
        )
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
    )


def test_manager_constructor_has_no_user_identity_input():
    parameters = (
        inspect.signature(
            KumaRuntimeCorrelation
        ).parameters
    )

    for forbidden in (
        "user_id",
        "account_id",
        "prompt",
        "message",
        "transcript",
        "command",
        "goal",
        "mission",
        "conversation",
    ):
        assert (
            forbidden
            not in parameters
        )


def test_end_turn_has_no_goal_verification_input():
    parameters = (
        inspect.signature(
            KumaRuntimeCorrelation
            .end_turn
        ).parameters
    )

    for forbidden in (
        "verified",
        "goal_complete",
        "success",
        "permission",
        "authority",
        "command",
    ):
        assert (
            forbidden
            not in parameters
        )


def test_close_session_has_no_authority_input():
    parameters = (
        inspect.signature(
            KumaRuntimeCorrelation
            .close_session
        ).parameters
    )

    assert tuple(
        parameters
    ) == (
        "self",
    )


def test_runtime_2b_imports_only_runtime_2a_from_kuma():
    loaded = imports()

    app_modules = {
        name
        for name in loaded
        if name.startswith(
            "app."
        )
    }

    assert app_modules == {
        "app.runtime_trace"
    }


def test_runtime_2b_has_no_agent_import():
    assert not any(
        name.startswith(
            "app.agent"
        )
        for name in imports()
    )


def test_runtime_2b_has_no_ui_import():
    assert not any(
        name.startswith(
            "app.ui"
        )
        for name in imports()
    )


def test_runtime_2b_has_no_voice_import():
    assert not any(
        name.startswith(
            "app.voice"
        )
        for name in imports()
    )


def test_runtime_2b_has_no_realtime_import():
    assert not any(
        name.startswith(
            "app.realtime"
        )
        for name in imports()
    )


def test_runtime_2b_has_no_memory_import():
    assert not any(
        name.startswith(
            "app.memory"
        )
        for name in imports()
    )


def test_runtime_2b_has_no_tool_import():
    assert not any(
        name.startswith(
            "app.tools"
        )
        for name in imports()
    )


def test_runtime_2b_has_no_network_import():
    roots = {
        name.split(
            ".",
            1,
        )[0]
        for name in imports()
    }

    assert roots.isdisjoint(
        {
            "requests",
            "httpx",
            "urllib",
            "socket",
            "aiohttp",
            "websockets",
        }
    )


def test_runtime_2b_has_no_persistence_import():
    roots = {
        name.split(
            ".",
            1,
        )[0]
        for name in imports()
    }

    assert roots.isdisjoint(
        {
            "sqlite3",
            "pathlib",
            "tempfile",
            "shelve",
        }
    )


def test_runtime_2b_has_no_model_provider_surface():
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


def test_runtime_2b_has_no_permission_execution_surface():
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


def test_runtime_2b_has_no_contextvar_or_thread_local():
    loaded = imports()

    assert (
        "contextvars"
        not in loaded
    )

    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    threading_names = {
        alias.name
        for node in ast.walk(
            tree
        )
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
            == "threading"
        )
        for alias in node.names
    }

    assert threading_names == {
        "RLock"
    }


def test_runtime_2b_has_no_background_loop():
    text = (
        MODULE.read_text()
    )

    for forbidden in (
        "while True",
        "Thread(",
        "QThread",
        "QTimer",
        "asyncio",
    ):
        assert forbidden not in text


def test_runtime_2b_has_no_raw_payload_fields():
    names = {
        value.name
        for value in fields(
            RuntimeTurnCorrelation
        )
    } | {
        value.name
        for value in fields(
            RuntimeTurnClosure
        )
    }

    for forbidden in (
        "prompt",
        "message",
        "transcript",
        "command",
        "arguments",
        "content",
        "text",
        "screen",
        "clipboard",
        "response",
        "memory_context",
        "goal",
    ):
        assert forbidden not in names


def test_runtime_2b_does_not_construct_runtime_2a_events_directly():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    runtime_event_calls = [
        node
        for node in ast.walk(
            tree
        )
        if (
            isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Name,
            )
            and node.func.id
            == "RuntimeTraceEvent"
        )
    ]

    assert (
        runtime_event_calls
        == []
    )


def test_runtime_2b_uses_runtime_2a_public_api():
    text = (
        MODULE.read_text()
    )

    assert (
        ".start_trace()"
        in text
    )

    assert (
        ".record("
        in text
    )

    assert (
        ".snapshot()"
        in text
    )


def test_runtime_2b_never_accesses_runtime_2a_private_state():
    text = (
        MODULE.read_text()
    )

    for forbidden in (
        "._events",
        "._next_sequence",
        "._last_timestamp",
        "._clock_ns",
        "._trace_id_factory",
    ):
        assert forbidden not in text


def test_runtime_2b_documents_core_boundaries():
    text = (
        MODULE.read_text()
    )

    for required in (
        "SESSION ID != USER ID",
        "TURN ID != PROMPT",
        "TRACE ID != COMMAND",
        "CORRELATION != AUTHORITY",
        "NEW TURN -> NEW TRACE",
        "ONE TURN -> ONE TRACE ID",
        "SESSION MAY SPAN TURNS",
        "TRACE MUST NOT SPAN UNRELATED TURNS",
        "RESPONSE TERMINAL != VERIFIED GOAL COMPLETION",
        "ERROR STILL TERMINATES A TURN",
        "BLOCKED STILL TERMINATES A TURN",
        "CORRELATION DATA != MODEL CONTEXT",
        "CORRELATION DATA != MEMORY",
        "CORRELATION AUTHORITY = NONE",
    ):
        assert required in text


def test_runtime_2b_documents_additive_not_live():
    text = (
        MODULE.read_text()
    )

    assert (
        "Runtime-2B remains additive"
        in text
    )

    assert (
        "future integration phase"
        in text.lower()
    )


def test_response_enum_docstring_denies_verified_completion():
    text = (
        inspect.getdoc(
            RuntimeTurnEndKind
        )
        or ""
    )

    assert (
        "does not mean"
        in text
    )

    assert (
        "verified complete"
        in text
    )


def test_closure_docstring_denies_task_success_claim():
    text = (
        inspect.getdoc(
            RuntimeTurnClosure
        )
        or ""
    )

    assert (
        "does not"
        in text
    )

    assert (
        "goal completion"
        in text
    )


def test_manager_docstring_denies_authority():
    text = (
        inspect.getdoc(
            KumaRuntimeCorrelation
        )
        or ""
    )

    assert (
        "cannot authorize"
        in text
    )

    assert (
        "execute"
        in text
    )


def test_frozen_runtime_2a_file_still_compiles():
    compile(
        TRACE_MODULE.read_text(),
        str(TRACE_MODULE),
        "exec",
    )


def test_runtime_2b_module_compiles():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
