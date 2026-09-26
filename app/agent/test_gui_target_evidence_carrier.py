from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import ast

import pytest

from app.agent.gui_target_dual_evidence import (
    DUAL_EVIDENCE_STATUS_UNKNOWN,
    StructuredUIVisualTargetEvidenceResult,
)
from app.agent.gui_target_evidence_carrier import (
    STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE,
    StructuredUIVisualTargetEvidenceCarrier,
    StructuredUIVisualTargetEvidenceStore,
)
from app.agent.test_gui_target_dual_evidence import GOAL, conjoin


@pytest.fixture(autouse=True)
def clear_global_carrier_store():
    STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE.clear()
    yield
    STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE.clear()


def matched_dual(monkeypatch, *, now=109.75):
    _point, _verification, result = conjoin(monkeypatch, now=now)
    assert result.matched
    return result


def test_issue_preserves_exact_b8e_result_and_evidence(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore(max_age_seconds=5.0)

    carrier = store.issue(result, clock=lambda: 110.0)

    assert carrier.evidence_result is result
    assert carrier.evidence is result.evidence
    assert carrier.screen_observation_id == result.evidence.screen_observation_id
    assert carrier.ui_observation_id == result.evidence.ui_observation_id
    assert carrier.vision_point == result.evidence.vision_point
    assert carrier.native_point == result.evidence.native_point
    assert carrier.visual_verification is result.evidence.visual_verification
    assert carrier.issued_at_monotonic == 110.0
    assert carrier.expires_at_monotonic == 115.0


def test_store_max_age_can_bound_carrier_more_tightly_than_b8e(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore(max_age_seconds=1.25)
    carrier = store.issue(result, clock=lambda: 110.0)
    assert carrier.expires_at_monotonic == 111.25
    assert carrier.is_current(111.249)
    assert not carrier.is_current(111.25)


def test_exact_claim_returns_same_carrier_once(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    issued = store.issue(result, clock=lambda: 110.0)

    claimed = store.claim(
        human_goal=GOAL,
        observation_id=result.evidence.screen_observation_id,
        x=result.evidence.vision_point[0],
        y=result.evidence.vision_point[1],
        clock=lambda: 110.5,
    )

    assert claimed is issued
    with pytest.raises(ValueError, match="No dual target-evidence carrier"):
        store.claim(
            human_goal=GOAL,
            observation_id=result.evidence.screen_observation_id,
            x=result.evidence.vision_point[0],
            y=result.evidence.vision_point[1],
            clock=lambda: 110.6,
        )


def test_goal_normalization_matches_b8e(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    issued = store.issue(result, clock=lambda: 110.0)
    claimed = store.claim(
        human_goal=f"  {GOAL}  ",
        observation_id=issued.screen_observation_id,
        x=issued.vision_point[0],
        y=issued.vision_point[1],
        clock=lambda: 110.5,
    )
    assert claimed is issued


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"human_goal": "Click Delete"}, "different human goal"),
        ({"observation_id": "9" * 32}, "different screen observation"),
        ({"x": 251}, "different candidate point"),
        ({"y": 176}, "different candidate point"),
    ],
)
def test_mismatched_claim_fails_closed_and_consumes(monkeypatch, kwargs, match):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    issued = store.issue(result, clock=lambda: 110.0)
    claim = dict(
        human_goal=GOAL,
        observation_id=issued.screen_observation_id,
        x=issued.vision_point[0],
        y=issued.vision_point[1],
        clock=lambda: 110.5,
    )
    claim.update(kwargs)

    with pytest.raises(ValueError, match=match):
        store.claim(**claim)

    with pytest.raises(ValueError, match="No dual target-evidence carrier"):
        store.claim(
            human_goal=GOAL,
            observation_id=issued.screen_observation_id,
            x=issued.vision_point[0],
            y=issued.vision_point[1],
            clock=lambda: 110.6,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"human_goal": ""},
        {"human_goal": None},
        {"observation_id": ""},
        {"observation_id": None},
        {"x": True},
        {"y": False},
        {"x": -1},
        {"y": -1},
    ],
)
def test_malformed_claim_fails_closed_and_consumes(monkeypatch, kwargs):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    issued = store.issue(result, clock=lambda: 110.0)
    claim = dict(
        human_goal=GOAL,
        observation_id=issued.screen_observation_id,
        x=issued.vision_point[0],
        y=issued.vision_point[1],
        clock=lambda: 110.5,
    )
    claim.update(kwargs)

    with pytest.raises(ValueError):
        store.claim(**claim)

    with pytest.raises(ValueError, match="No dual target-evidence carrier"):
        store.claim(
            human_goal=GOAL,
            observation_id=issued.screen_observation_id,
            x=issued.vision_point[0],
            y=issued.vision_point[1],
            clock=lambda: 110.6,
        )


def test_expired_carrier_fails_closed_and_consumes(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore(max_age_seconds=1.0)
    issued = store.issue(result, clock=lambda: 110.0)

    with pytest.raises(ValueError, match="expired"):
        store.claim(
            human_goal=GOAL,
            observation_id=issued.screen_observation_id,
            x=issued.vision_point[0],
            y=issued.vision_point[1],
            clock=lambda: 111.0,
        )

    with pytest.raises(ValueError, match="No dual target-evidence carrier"):
        store.claim(
            human_goal=GOAL,
            observation_id=issued.screen_observation_id,
            x=issued.vision_point[0],
            y=issued.vision_point[1],
            clock=lambda: 110.5,
        )


def test_backwards_claim_time_fails_closed(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    issued = store.issue(result, clock=lambda: 110.0)
    with pytest.raises(ValueError, match="expired"):
        store.claim(
            human_goal=GOAL,
            observation_id=issued.screen_observation_id,
            x=issued.vision_point[0],
            y=issued.vision_point[1],
            clock=lambda: 109.9,
        )


def test_new_issue_replaces_old_pending_carrier(monkeypatch):
    first_result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    first = store.issue(first_result, clock=lambda: 110.0)

    second_result = matched_dual(monkeypatch)
    second = store.issue(second_result, clock=lambda: 110.1)

    assert second is not first
    claimed = store.claim(
        human_goal=GOAL,
        observation_id=second.screen_observation_id,
        x=second.vision_point[0],
        y=second.vision_point[1],
        clock=lambda: 110.2,
    )
    assert claimed is second


def test_clear_removes_pending_carrier(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    carrier = store.issue(result, clock=lambda: 110.0)
    store.clear()
    with pytest.raises(ValueError, match="No dual target-evidence carrier"):
        store.claim(
            human_goal=GOAL,
            observation_id=carrier.screen_observation_id,
            x=carrier.vision_point[0],
            y=carrier.vision_point[1],
            clock=lambda: 110.1,
        )


def test_issue_rejects_unknown_or_invalid_b8e_results(monkeypatch):
    matched = matched_dual(monkeypatch)
    unknown = StructuredUIVisualTargetEvidenceResult(
        status=DUAL_EVIDENCE_STATUS_UNKNOWN,
        diagnostics=("clock_unavailable",),
    )
    store = StructuredUIVisualTargetEvidenceStore()

    with pytest.raises(ValueError, match="exact B8E result"):
        store.issue(object(), clock=lambda: 110.0)
    with pytest.raises(ValueError, match="matched B8E evidence"):
        store.issue(unknown, clock=lambda: 110.0)
    assert matched.matched


def test_issue_rejects_b8e_evidence_at_expiry(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    with pytest.raises(ValueError, match="not current"):
        store.issue(result, clock=lambda: result.evidence.expires_at_monotonic)


@pytest.mark.parametrize("value", [0, -1, True, False, float("inf"), float("nan"), "5"])
def test_store_rejects_invalid_max_age(value):
    with pytest.raises(ValueError):
        StructuredUIVisualTargetEvidenceStore(max_age_seconds=value)


def test_noncallable_clocks_are_rejected_before_store_mutation(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    with pytest.raises(TypeError):
        store.issue(result, clock=None)

    carrier = store.issue(result, clock=lambda: 110.0)
    with pytest.raises(TypeError):
        store.claim(
            human_goal=GOAL,
            observation_id=carrier.screen_observation_id,
            x=carrier.vision_point[0],
            y=carrier.vision_point[1],
            clock=None,
        )

    claimed = store.claim(
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        clock=lambda: 110.1,
    )
    assert claimed is carrier


def test_clock_failure_on_issue_does_not_leak_exception_text(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    with pytest.raises(ValueError, match="clock is unavailable") as caught:
        store.issue(
            result,
            clock=lambda: (_ for _ in ()).throw(RuntimeError("private details")),
        )
    assert "private" not in repr(caught.value)


def test_clock_failure_on_claim_consumes_without_leaking_exception_text(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    carrier = store.issue(result, clock=lambda: 110.0)

    with pytest.raises(ValueError, match="clock is unavailable") as caught:
        store.claim(
            human_goal=GOAL,
            observation_id=carrier.screen_observation_id,
            x=carrier.vision_point[0],
            y=carrier.vision_point[1],
            clock=lambda: (_ for _ in ()).throw(RuntimeError("private details")),
        )
    assert "private" not in repr(caught.value)

    with pytest.raises(ValueError, match="No dual target-evidence carrier"):
        store.claim(
            human_goal=GOAL,
            observation_id=carrier.screen_observation_id,
            x=carrier.vision_point[0],
            y=carrier.vision_point[1],
            clock=lambda: 110.1,
        )


def test_constructor_rejects_equal_value_evidence_substitution(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    carrier = store.issue(result, clock=lambda: 110.0)
    clone = replace(carrier.evidence)
    assert clone == carrier.evidence
    assert clone is not carrier.evidence

    with pytest.raises(ValueError, match="exact matched B8E evidence graph"):
        replace(carrier, evidence=clone)


def test_carrier_is_immutable(monkeypatch):
    result = matched_dual(monkeypatch)
    carrier = StructuredUIVisualTargetEvidenceStore().issue(
        result,
        clock=lambda: 110.0,
    )
    with pytest.raises(FrozenInstanceError):
        carrier.expires_at_monotonic = 1.0


@pytest.mark.parametrize(
    "name",
    [
        "semantic_target_verified",
        "authorized",
        "permission",
        "approved",
        "attestation",
        "execute",
        "click",
    ],
)
def test_carrier_and_store_have_no_authority_surface(monkeypatch, name):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    carrier = store.issue(result, clock=lambda: 110.0)
    assert not hasattr(carrier, name)
    assert not hasattr(store, name)


def test_no_dict_reconstruction_or_serialization_surface():
    assert not hasattr(StructuredUIVisualTargetEvidenceCarrier, "from_dict")
    assert not hasattr(StructuredUIVisualTargetEvidenceCarrier, "to_dict")
    assert not hasattr(StructuredUIVisualTargetEvidenceStore, "from_dict")
    assert not hasattr(StructuredUIVisualTargetEvidenceStore, "to_dict")


def test_module_direct_imports_exclude_authority_execution_and_mission_service():
    module = Path(__file__).with_name("gui_target_evidence_carrier.py")
    tree = ast.parse(module.read_text())
    direct_imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            direct_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            direct_imports.add(node.module or "")

    forbidden = (
        "app.agent.mission_service",
        "app.agent.gui_argument_authority",
        "app.tools",
        "app.vision.gui_target_verifier",
        "pyautogui",
        "ApplicationServices",
        "AppKit",
        "Quartz",
    )
    for imported in direct_imports:
        assert not any(
            imported == prefix or imported.startswith(prefix + ".")
            for prefix in forbidden
        ), imported
