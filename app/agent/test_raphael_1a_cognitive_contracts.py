from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect

import pytest

from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
    TacticalDecision,
    TacticalDisposition,
    TacticalOption,
    TacticalRisk,
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.permissions import PermissionLevel

STAMP = "2026-09-12T14:00:00+05:30"


def _option(option_id="option-1", permission=PermissionLevel.SAFE):
    return TacticalOption(
        option_id=option_id,
        objective="Inspect the current state.",
        rationale="More evidence reduces uncertainty.",
        expected_outcome="State becomes clearer.",
        confidence=0.82,
        risk=TacticalRisk.LOW,
        required_permission=permission,
        reversible=True,
        capability="inspect_system",
        cost=0.15,
    )


def test_world_state_is_zero_authority_and_frozen():
    snapshot = WorldStateSnapshot(
        timestamp=STAMP,
        task_goal="Diagnose the current issue.",
        system_state=("CPU normal",),
    )
    assert snapshot.authority == COGNITIVE_AUTHORITY_NONE
    with pytest.raises(FrozenInstanceError):
        snapshot.task_goal = "mutated"


@pytest.mark.parametrize("bad_timestamp", ("", "not-a-time", "2026-09-12T14:00:00"))
def test_world_state_rejects_invalid_or_naive_timestamp(bad_timestamp):
    with pytest.raises((ValueError, TypeError)):
        WorldStateSnapshot(timestamp=bad_timestamp)


def test_tactical_situation_normalizes_iterables_and_stays_zero_authority():
    situation = TacticalSituation(
        goal="Choose the safest next diagnostic step.",
        observed_state=["Application is open."],
        known_facts=["No destructive action requested."],
        uncertainties=["Failure cause is unknown."],
        constraints=["Do not alter files."],
        available_capabilities=["inspect_system"],
        world_state=WorldStateSnapshot(timestamp=STAMP),
    )
    assert situation.authority == "NONE"
    assert situation.observed_state == ("Application is open.",)


def test_tactical_situation_rejects_blank_goal():
    with pytest.raises(ValueError, match="goal"):
        TacticalSituation(goal="   ")


@pytest.mark.parametrize("confidence", (-0.01, 1.01, True, "0.9"))
def test_tactical_option_rejects_invalid_confidence(confidence):
    with pytest.raises((TypeError, ValueError)):
        TacticalOption(
            option_id="bad-confidence",
            objective="Inspect.",
            rationale="Need evidence.",
            expected_outcome="More evidence.",
            confidence=confidence,
            risk=TacticalRisk.LOW,
            required_permission=PermissionLevel.SAFE,
            reversible=True,
        )


def test_tactical_option_records_required_permission_without_granting_it():
    option = _option(permission=PermissionLevel.DANGEROUS)
    assert option.required_permission == PermissionLevel.DANGEROUS
    assert option.authority == "NONE"


def test_tactical_option_requires_permission_enum():
    with pytest.raises(TypeError, match="required_permission"):
        TacticalOption(
            option_id="bad-permission",
            objective="Inspect.",
            rationale="Need evidence.",
            expected_outcome="More evidence.",
            confidence=0.8,
            risk=TacticalRisk.LOW,
            required_permission="safe",
            reversible=True,
        )


@pytest.mark.parametrize("risk", tuple(TacticalRisk))
def test_all_tactical_risk_levels_are_valid(risk):
    option = TacticalOption(
        option_id=f"risk-{risk.value}",
        objective="Evaluate.",
        rationale="Compare risk.",
        expected_outcome="Risk classified.",
        confidence=0.5,
        risk=risk,
        required_permission=PermissionLevel.SAFE,
        reversible=True,
    )
    assert option.risk is risk
    assert option.authority == "NONE"


def test_decision_is_recommendation_only_and_inherits_required_permission():
    option = _option(permission=PermissionLevel.USER_AUTHORIZED)
    decision = TacticalDecision(
        disposition=TacticalDisposition.ACTION_CANDIDATE,
        reason="This is the best available option.",
        confidence=0.91,
        chosen_option=option,
    )
    assert decision.authority == "NONE"
    assert decision.required_permission == PermissionLevel.USER_AUTHORIZED


def test_blocked_decision_can_exist_without_action_option():
    decision = TacticalDecision(
        disposition=TacticalDisposition.BLOCKED,
        reason="Required evidence is unavailable.",
        confidence=0.99,
        remaining_uncertainties=("Target state cannot be verified.",),
    )
    assert decision.chosen_option is None
    assert decision.required_permission is None


def test_decision_rejects_chosen_option_also_rejected():
    option = _option()
    with pytest.raises(ValueError, match="chosen_option"):
        TacticalDecision(
            disposition=TacticalDisposition.ADVISE,
            reason="Contradictory decision.",
            confidence=0.5,
            chosen_option=option,
            rejected_options=(option,),
        )


def test_contract_module_has_no_execution_surface():
    import app.agent.cognitive_contracts as module
    source = inspect.getsource(module)
    for marker in (
        "ActionExecutor",
        "register_tool(",
        ".execute(",
        "request_confirmation(",
        "open_app(",
        "type_text(",
        "execute_command(",
        "kuma_runtime",
    ):
        assert marker not in source


def test_contracts_do_not_expose_approval_fields():
    for contract in (WorldStateSnapshot, TacticalSituation, TacticalOption, TacticalDecision):
        fields = set(contract.__dataclass_fields__)
        assert "approved" not in fields
        assert "confirmed" not in fields
        assert "permission_granted" not in fields
        assert "authorized" not in fields


def test_authority_is_not_constructor_input():
    assert "authority" not in inspect.signature(TacticalOption).parameters
    assert "authority" not in inspect.signature(TacticalDecision).parameters
