from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.realtime.contracts import (
    RealtimeFact,
)
from app.realtime.runtime_trigger import (
    MAX_TRIGGER_REASON_CHARS,
    REALTIME_TRIGGER_AUTHORITY_NONE,
    RealtimeTriggerProposal,
    propose_runtime_trigger,
)


ROOT = Path(__file__).resolve().parents[2]

MODULE = (
    ROOT
    / "app/realtime/runtime_trigger.py"
)

V1_REGRESSION = (
    ROOT
    / "app/realtime/test_realtime_v1_architecture_regression.py"
)


def _fact(
    *,
    authority: str = "NONE",
) -> RealtimeFact:
    fact = object.__new__(
        RealtimeFact
    )

    object.__setattr__(
        fact,
        "authority",
        authority,
    )

    return fact


def _signal(
    *,
    kind: str = "weather.current",
    level: RealtimeRelevanceLevel = RealtimeRelevanceLevel.HIGH,
    score: float = 0.9,
    reason: str = "precipitation started",
    fact_authority: str = "NONE",
    previous_authority: str | None = None,
    signal_authority: str = "NONE",
) -> RealtimeSignal:
    signal = object.__new__(
        RealtimeSignal
    )

    object.__setattr__(signal, "kind", kind)
    object.__setattr__(signal, "level", level)
    object.__setattr__(signal, "score", score)
    object.__setattr__(signal, "reason", reason)
    object.__setattr__(
        signal,
        "fact",
        _fact(authority=fact_authority),
    )
    object.__setattr__(
        signal,
        "previous_fact",
        (
            None
            if previous_authority is None
            else _fact(authority=previous_authority)
        ),
    )
    object.__setattr__(
        signal,
        "authority",
        signal_authority,
    )

    return signal


def _field_names(cls) -> tuple[str, ...]:
    return tuple(
        item.name
        for item in fields(cls)
    )


def _imports(path: Path) -> set[str]:
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    result = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(
                alias.name
                for alias in node.names
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
        ):
            result.add(node.module)

    return result


def test_2a_module_and_frozen_v1_regression_exist():
    assert MODULE.is_file()
    assert V1_REGRESSION.is_file()


def test_trigger_authority_is_permanently_none():
    assert REALTIME_TRIGGER_AUTHORITY_NONE == "NONE"

    proposal = propose_runtime_trigger(
        _signal()
    )

    assert proposal is not None
    assert proposal.authority == "NONE"


def test_trigger_proposal_surface_is_privacy_minimized():
    assert _field_names(
        RealtimeTriggerProposal
    ) == (
        "proposal_id",
        "kind",
        "level",
        "score",
        "reason",
        "authority",
    )


def test_trigger_proposal_exposes_no_action_authority_fields():
    forbidden = {
        "tool",
        "tool_name",
        "arguments",
        "command",
        "permission",
        "confirmation",
        "execute",
        "executor",
        "callback",
        "mission",
        "retry",
        "resume",
        "verified",
        "verified_complete",
        "fact",
        "previous_fact",
        "value",
        "location",
    }

    assert set(
        _field_names(
            RealtimeTriggerProposal
        )
    ).isdisjoint(
        forbidden
    )


def test_trigger_proposal_is_frozen():
    proposal = propose_runtime_trigger(
        _signal()
    )

    assert proposal is not None

    with pytest.raises(
        FrozenInstanceError
    ):
        proposal.kind = "other"


def test_trigger_proposal_rejects_non_none_authority():
    with pytest.raises(
        ValueError,
        match="permanently NONE",
    ):
        RealtimeTriggerProposal(
            proposal_id="rtp-test",
            kind="weather.current",
            level=RealtimeRelevanceLevel.HIGH,
            score=0.9,
            reason="eligible",
            authority="USER",
        )


def test_projection_rejects_non_signal_input():
    with pytest.raises(
        TypeError,
        match="RealtimeSignal",
    ):
        propose_runtime_trigger(
            object()
        )


def test_projection_rejects_forged_signal_authority():
    with pytest.raises(
        ValueError,
        match="RealtimeSignal authority",
    ):
        propose_runtime_trigger(
            _signal(
                signal_authority="USER",
            )
        )


def test_projection_rejects_forged_fact_authority():
    with pytest.raises(
        ValueError,
        match="fact authority",
    ):
        propose_runtime_trigger(
            _signal(
                fact_authority="USER",
            )
        )


def test_projection_rejects_forged_previous_fact_authority():
    with pytest.raises(
        ValueError,
        match="Previous RealtimeFact authority",
    ):
        propose_runtime_trigger(
            _signal(
                previous_authority="USER",
            )
        )


def test_ignore_signal_produces_no_trigger_proposal():
    assert (
        propose_runtime_trigger(
            _signal(
                level=RealtimeRelevanceLevel.IGNORE,
                score=0.0,
            )
        )
        is None
    )


def test_zero_score_produces_no_trigger_proposal():
    assert (
        propose_runtime_trigger(
            _signal(
                level=RealtimeRelevanceLevel.LOW,
                score=0.0,
            )
        )
        is None
    )


@pytest.mark.parametrize(
    "level,score",
    (
        (RealtimeRelevanceLevel.LOW, 0.2),
        (RealtimeRelevanceLevel.MEDIUM, 0.65),
        (RealtimeRelevanceLevel.HIGH, 0.9),
    ),
)
def test_existing_non_ignore_relevance_is_projected_without_escalation(
    level,
    score,
):
    proposal = propose_runtime_trigger(
        _signal(
            level=level,
            score=score,
        )
    )

    assert proposal is not None
    assert proposal.level == level
    assert proposal.score == score


def test_projection_does_not_strengthen_score():
    signal = _signal(
        level=RealtimeRelevanceLevel.MEDIUM,
        score=0.51,
    )

    proposal = propose_runtime_trigger(signal)

    assert proposal is not None
    assert proposal.score == signal.score


def test_projection_identity_is_deterministic():
    first = propose_runtime_trigger(
        _signal()
    )
    second = propose_runtime_trigger(
        _signal()
    )

    assert first is not None
    assert second is not None
    assert first.proposal_id == second.proposal_id


def test_projection_identity_changes_with_safe_relevance_metadata():
    first = propose_runtime_trigger(
        _signal(
            reason="precipitation started",
        )
    )
    second = propose_runtime_trigger(
        _signal(
            reason="temperature changed materially",
        )
    )

    assert first is not None
    assert second is not None
    assert first.proposal_id != second.proposal_id


def test_reason_is_whitespace_normalized_and_bounded():
    proposal = propose_runtime_trigger(
        _signal(
            reason=(
                "  precipitation   started  "
                + ("x" * 400)
            ),
        )
    )

    assert proposal is not None
    assert "  " not in proposal.reason
    assert len(proposal.reason) <= MAX_TRIGGER_REASON_CHARS


def test_projection_does_not_preserve_raw_fact_object():
    signal = _signal()

    proposal = propose_runtime_trigger(signal)

    assert proposal is not None

    for item in fields(proposal):
        assert getattr(
            proposal,
            item.name,
        ) is not signal.fact


def test_2a_module_does_not_import_agent_or_tools():
    for module in _imports(MODULE):
        assert not module.startswith(
            (
                "app.agent",
                "app.tools",
            )
        ), module


def test_2a_module_has_no_network_or_persistence_dependency():
    roots = {
        module.split(".", 1)[0]
        for module in _imports(MODULE)
    }

    assert roots.isdisjoint(
        {
            "httpx",
            "requests",
            "urllib",
            "socket",
            "aiohttp",
            "websockets",
            "sqlite3",
            "sqlalchemy",
            "shelve",
        }
    )


def test_2a_module_has_no_background_execution_primitive():
    source = MODULE.read_text()

    for forbidden in (
        "threading.Thread",
        "Thread(",
        "asyncio.create_task",
        "create_task(",
        "while True",
        "run_forever(",
        "Timer(",
        "daemon=",
    ):
        assert forbidden not in source


def test_2a_module_has_no_runtime_side_effect_calls():
    source = MODULE.read_text()

    for forbidden in (
        ".tick(",
        "pending_signals(",
        "drain_signals(",
        "refresh_weather(",
        "refresh_weather_daily(",
        ".publish(",
        ".put(",
        ".register(",
        ".subscribe(",
    ):
        assert forbidden not in source


def test_2a_boundary_markers_are_explicit():
    source = MODULE.read_text()

    for marker in (
        "TRIGGER PROPOSAL != COMMAND",
        "TRIGGER PROPOSAL != PERMISSION",
        "TRIGGER PROPOSAL != EXECUTION",
        "TRIGGER PROPOSAL != VERIFIED COMPLETION",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_2a_does_not_modify_frozen_v1_regression_contract():
    source = V1_REGRESSION.read_text()

    assert (
        "def test_realtime_v1_phase_tests_exist():"
        in source
    )
    assert (
        "def test_realtime_subsystem_has_no_background_execution_loop():"
        in source
    )
    assert (
        "def test_realtime_v1_boundary_markers_are_explicit():"
        in source
    )


def test_2a_source_compiles():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
