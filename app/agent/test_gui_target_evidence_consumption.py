from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import ast

import pytest

from app.agent.gui_target_evidence_carrier import (
    STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE,
    StructuredUIVisualTargetEvidenceStore,
)
from app.agent.gui_target_evidence_consumption import (
    CONSUMPTION_STATUS_MATCHED,
    CONSUMPTION_STATUS_UNKNOWN,
    StructuredUIVisualTargetEvidenceConsumption,
    StructuredUIVisualTargetEvidenceConsumptionResult,
    consume_structured_ui_visual_target_evidence,
)
from app.agent.test_gui_target_dual_evidence import GOAL
from app.agent.test_gui_target_evidence_carrier import matched_dual


@pytest.fixture(autouse=True)
def clear_global_carrier_store():
    STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE.clear()
    yield
    STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE.clear()


def issued(monkeypatch, *, store=None, issue_now=110.0):
    result = matched_dual(monkeypatch)
    store = store or StructuredUIVisualTargetEvidenceStore()
    carrier = store.issue(result, clock=lambda: issue_now)
    return result, store, carrier, result.evidence.visual_verification


def consume(
    monkeypatch,
    *,
    store=None,
    verification=None,
    human_goal=GOAL,
    observation_id=None,
    x=None,
    y=None,
    issue_now=110.0,
    claim_now=110.5,
):
    result, store, carrier, original = issued(
        monkeypatch,
        store=store,
        issue_now=issue_now,
    )
    verification = original if verification is None else verification
    observation_id = carrier.screen_observation_id if observation_id is None else observation_id
    x = carrier.vision_point[0] if x is None else x
    y = carrier.vision_point[1] if y is None else y
    consumed = consume_structured_ui_visual_target_evidence(
        verification,
        human_goal=human_goal,
        observation_id=observation_id,
        x=x,
        y=y,
        store=store,
        clock=lambda: claim_now,
    )
    return result, store, carrier, original, consumed


def assert_store_consumed(store, carrier, *, now=110.6):
    with pytest.raises(ValueError, match="No dual target-evidence carrier"):
        store.claim(
            human_goal=GOAL,
            observation_id=carrier.screen_observation_id,
            x=carrier.vision_point[0],
            y=carrier.vision_point[1],
            clock=lambda: now,
        )


def test_happy_path_claims_exact_carrier_and_preserves_runtime_visual_identity(monkeypatch):
    result, store, carrier, visual, consumed = consume(monkeypatch)

    assert consumed.status == CONSUMPTION_STATUS_MATCHED
    assert consumed.matched
    evidence = consumed.consumption
    assert evidence.carrier is carrier
    assert evidence.visual_verification is visual
    assert evidence.evidence is result.evidence
    assert evidence.screen_observation_id == carrier.screen_observation_id
    assert evidence.ui_observation_id == carrier.ui_observation_id
    assert evidence.vision_point == carrier.vision_point
    assert evidence.native_point == carrier.native_point
    assert evidence.target_region_sha256 == visual.target_region_sha256
    assert evidence.is_current(110.6)
    assert_store_consumed(store, carrier)


def test_default_global_store_can_be_consumed(monkeypatch):
    result = matched_dual(monkeypatch)
    carrier = STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE.issue(
        result,
        clock=lambda: 110.0,
    )
    visual = result.evidence.visual_verification
    consumed = consume_structured_ui_visual_target_evidence(
        visual,
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        clock=lambda: 110.5,
    )
    assert consumed.matched
    assert consumed.consumption.carrier is carrier


def test_equal_value_reconstructed_visual_is_rejected_by_identity_and_consumes(monkeypatch):
    result, store, carrier, visual = issued(monkeypatch)
    clone = replace(visual)
    assert clone == visual
    assert clone is not visual

    consumed = consume_structured_ui_visual_target_evidence(
        clone,
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        store=store,
        clock=lambda: 110.5,
    )
    assert consumed.status == CONSUMPTION_STATUS_UNKNOWN
    assert consumed.diagnostics == ("visual_identity_mismatch",)
    assert_store_consumed(store, carrier)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "unknown"),
        ("summary", ""),
        ("evidence", ""),
        ("image_sha256", "bad"),
        ("target_region_sha256", "bad"),
    ],
)
def test_invalid_or_unavailable_visual_consumes_pending_carrier(monkeypatch, field, value):
    _result, store, carrier, visual = issued(monkeypatch)
    changed = replace(visual, **{field: value})
    consumed = consume_structured_ui_visual_target_evidence(
        changed,
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        store=store,
        clock=lambda: 110.5,
    )
    assert consumed.status == CONSUMPTION_STATUS_UNKNOWN
    if field == "status":
        assert consumed.diagnostics == ("visual_verification_unavailable",)
    else:
        assert consumed.diagnostics == ("invalid_visual_verification",)
    assert_store_consumed(store, carrier)


def test_non_visual_object_consumes_pending_carrier(monkeypatch):
    _result, store, carrier, _visual = issued(monkeypatch)
    consumed = consume_structured_ui_visual_target_evidence(
        object(),
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        store=store,
        clock=lambda: 110.5,
    )
    assert consumed.diagnostics == ("invalid_visual_verification",)
    assert_store_consumed(store, carrier)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"human_goal": "Click Delete"},
        {"observation_id": "9" * 32},
        {"x": 251},
        {"y": 176},
    ],
)
def test_claim_mismatch_is_generic_unavailable_and_consumes(monkeypatch, kwargs):
    _result, store, carrier, visual = issued(monkeypatch)
    claim = dict(
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
    )
    claim.update(kwargs)
    consumed = consume_structured_ui_visual_target_evidence(
        visual,
        store=store,
        clock=lambda: 110.5,
        **claim,
    )
    assert consumed.diagnostics == ("carrier_unavailable",)
    assert_store_consumed(store, carrier)


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
def test_malformed_claim_is_generic_unavailable_and_consumes(monkeypatch, kwargs):
    _result, store, carrier, visual = issued(monkeypatch)
    claim = dict(
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
    )
    claim.update(kwargs)
    consumed = consume_structured_ui_visual_target_evidence(
        visual,
        store=store,
        clock=lambda: 110.5,
        **claim,
    )
    assert consumed.diagnostics == ("carrier_unavailable",)
    assert_store_consumed(store, carrier)


def test_missing_carrier_fails_closed(monkeypatch):
    result = matched_dual(monkeypatch)
    store = StructuredUIVisualTargetEvidenceStore()
    visual = result.evidence.visual_verification
    consumed = consume_structured_ui_visual_target_evidence(
        visual,
        human_goal=GOAL,
        observation_id=result.evidence.screen_observation_id,
        x=result.evidence.vision_point[0],
        y=result.evidence.vision_point[1],
        store=store,
        clock=lambda: 110.5,
    )
    assert consumed.diagnostics == ("carrier_unavailable",)


def test_expired_carrier_fails_closed_and_consumes(monkeypatch):
    store = StructuredUIVisualTargetEvidenceStore(max_age_seconds=0.5)
    _result, store, carrier, visual = issued(monkeypatch, store=store)
    consumed = consume_structured_ui_visual_target_evidence(
        visual,
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        store=store,
        clock=lambda: 110.5,
    )
    assert consumed.diagnostics == ("carrier_unavailable",)
    assert_store_consumed(store, carrier, now=110.4)


def test_clock_failure_is_sanitized_and_consumes(monkeypatch):
    _result, store, carrier, visual = issued(monkeypatch)
    consumed = consume_structured_ui_visual_target_evidence(
        visual,
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        store=store,
        clock=lambda: (_ for _ in ()).throw(RuntimeError("private details")),
    )
    assert consumed.diagnostics == ("carrier_unavailable",)
    assert "private" not in repr(consumed)
    assert_store_consumed(store, carrier)


def test_noncallable_clock_is_rejected_before_claim(monkeypatch):
    _result, store, carrier, visual = issued(monkeypatch)
    with pytest.raises(TypeError):
        consume_structured_ui_visual_target_evidence(
            visual,
            human_goal=GOAL,
            observation_id=carrier.screen_observation_id,
            x=carrier.vision_point[0],
            y=carrier.vision_point[1],
            store=store,
            clock=False,
        )
    # This is API misuse before B8F claim; the carrier remains available.
    claimed = store.claim(
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        clock=lambda: 110.5,
    )
    assert claimed is carrier


def test_invalid_store_fails_without_touching_real_store(monkeypatch):
    result = matched_dual(monkeypatch)
    carrier = STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE.issue(
        result,
        clock=lambda: 110.0,
    )
    visual = result.evidence.visual_verification
    consumed = consume_structured_ui_visual_target_evidence(
        visual,
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        store=object(),
        clock=lambda: 110.5,
    )
    assert consumed.diagnostics == ("invalid_store",)
    claimed = STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE.claim(
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        clock=lambda: 110.5,
    )
    assert claimed is carrier


def test_constructor_rejects_equal_value_visual_substitution(monkeypatch):
    _result, store, carrier, visual = issued(monkeypatch)
    claimed = store.claim(
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        clock=lambda: 110.5,
    )
    clone = replace(visual)
    with pytest.raises(ValueError, match="exact B8F visual object"):
        StructuredUIVisualTargetEvidenceConsumption(
            carrier=claimed,
            visual_verification=clone,
            human_goal_sha256=claimed.human_goal_sha256,
        )


def test_constructor_rejects_goal_digest_substitution(monkeypatch):
    _result, store, carrier, visual = issued(monkeypatch)
    claimed = store.claim(
        human_goal=GOAL,
        observation_id=carrier.screen_observation_id,
        x=carrier.vision_point[0],
        y=carrier.vision_point[1],
        clock=lambda: 110.5,
    )
    with pytest.raises(ValueError, match="different human goal"):
        StructuredUIVisualTargetEvidenceConsumption(
            carrier=claimed,
            visual_verification=visual,
            human_goal_sha256="0" * 64,
        )


def test_consumption_and_result_are_immutable(monkeypatch):
    _result, _store, _carrier, _visual, consumed = consume(monkeypatch)
    with pytest.raises(FrozenInstanceError):
        consumed.consumption.human_goal_sha256 = "x"
    with pytest.raises(FrozenInstanceError):
        consumed.status = CONSUMPTION_STATUS_UNKNOWN


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
def test_consumption_has_no_authority_surface(monkeypatch, name):
    _result, _store, _carrier, _visual, consumed = consume(monkeypatch)
    assert not hasattr(consumed.consumption, name)
    assert not hasattr(consumed, name)


def test_no_dict_reconstruction_or_serialization_surface():
    assert not hasattr(StructuredUIVisualTargetEvidenceConsumption, "from_dict")
    assert not hasattr(StructuredUIVisualTargetEvidenceConsumption, "to_dict")
    assert not hasattr(StructuredUIVisualTargetEvidenceConsumptionResult, "from_dict")
    assert not hasattr(StructuredUIVisualTargetEvidenceConsumptionResult, "to_dict")


def test_result_contract_rejects_forged_combinations(monkeypatch):
    _result, _store, _carrier, _visual, matched = consume(monkeypatch)
    with pytest.raises(ValueError):
        StructuredUIVisualTargetEvidenceConsumptionResult(
            status=CONSUMPTION_STATUS_MATCHED,
            consumption=None,
        )
    with pytest.raises(ValueError):
        StructuredUIVisualTargetEvidenceConsumptionResult(
            status=CONSUMPTION_STATUS_UNKNOWN,
            consumption=matched.consumption,
            diagnostics=("carrier_unavailable",),
        )
    with pytest.raises(ValueError):
        StructuredUIVisualTargetEvidenceConsumptionResult(
            status=CONSUMPTION_STATUS_UNKNOWN,
            diagnostics=("made_up",),
        )


def test_module_direct_imports_exclude_authority_execution_and_mission_service():
    module = Path(__file__).with_name("gui_target_evidence_consumption.py")
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
