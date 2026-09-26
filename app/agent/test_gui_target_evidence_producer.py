from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import ast

import pytest

from app.agent.gui_target_evidence_carrier import (
    StructuredUIVisualTargetEvidenceStore,
)
from app.agent.gui_target_evidence_producer import (
    PRODUCTION_STATUS_ISSUED,
    PRODUCTION_STATUS_UNKNOWN,
    StructuredUIVisualTargetEvidenceProductionResult,
    produce_structured_ui_visual_target_evidence,
)
from app.agent.test_gui_target_dual_evidence import GOAL, visual
from app.agent.test_gui_target_evidence import (
    NEW_UI,
    fresh_binding,
    item,
    make_intent,
    observation,
    old_binding,
)
from app.agent.test_gui_target_point_binding import make_active_screen
from app.vision.observation import SCREEN_OBSERVATIONS


@pytest.fixture(autouse=True)
def clear_screen_store():
    SCREEN_OBSERVATIONS.clear()
    yield
    SCREEN_OBSERVATIONS.clear()


def sequence_clock(*values):
    iterator = iter(values)
    return lambda: next(iterator)


def inputs(monkeypatch, *, verification=None, x=250, y=175):
    make_active_screen(monkeypatch)
    intent = make_intent()
    original = observation(item())
    original_source = old_binding()
    fresh = observation(
        item(
            position_x=420.0,
            position_y=330.0,
            width=160.0,
            height=55.0,
        ),
        observation_id=NEW_UI,
        captured=106.0,
    )
    fresh_source = fresh_binding()
    verification = verification or visual(x=x, y=y)
    return dict(
        intent=intent,
        original_observation=original,
        original_binding=original_source,
        fresh_observation=fresh,
        fresh_binding=fresh_source,
        vision_x=x,
        vision_y=y,
        visual_verification=verification,
        human_goal=GOAL,
    )


def produce(monkeypatch, *, store=None, verification=None, x=250, y=175):
    store = store or StructuredUIVisualTargetEvidenceStore()
    result = produce_structured_ui_visual_target_evidence(
        **inputs(monkeypatch, verification=verification, x=x, y=y),
        store=store,
        clock=sequence_clock(
            104.0,
            109.0,
            109.25,
            109.5,
            109.75,
            110.0,
        ),
    )
    return store, result


def test_happy_path_issues_exact_b8c_through_b8f_graph(monkeypatch):
    verification = visual()
    store, result = produce(monkeypatch, verification=verification)

    assert result.status == PRODUCTION_STATUS_ISSUED
    assert result.issued
    production = result.production
    assert production.visual_verification is verification
    assert (
        production.point_binding_result.binding.orchestration_result
        is production.orchestration_result
    )
    assert (
        production.dual_evidence_result.evidence.point_binding_result
        is production.point_binding_result
    )
    assert (
        production.dual_evidence_result.evidence.visual_verification
        is verification
    )
    assert production.carrier.evidence_result is production.dual_evidence_result
    assert production.carrier.visual_verification is verification
    assert production.vision_point == (250, 175)
    assert production.native_point == (500, 350)

    claimed = store.claim(
        human_goal=GOAL,
        observation_id=production.screen_observation_id,
        x=250,
        y=175,
        clock=lambda: 110.5,
    )
    assert claimed is production.carrier


def test_new_attempt_clears_previous_carrier_before_failure(monkeypatch):
    store, first = produce(monkeypatch)
    assert first.issued

    bad = inputs(monkeypatch)
    bad["intent"] = object()
    failed = produce_structured_ui_visual_target_evidence(
        **bad,
        store=store,
        clock=lambda: 110.1,
    )
    assert failed.status == PRODUCTION_STATUS_UNKNOWN
    assert failed.diagnostics == ("orchestration_unavailable",)

    with pytest.raises(ValueError, match="No dual target-evidence carrier"):
        store.claim(
            human_goal=GOAL,
            observation_id=first.production.screen_observation_id,
            x=250,
            y=175,
            clock=lambda: 110.2,
        )


def test_point_mismatch_is_not_promoted_to_dual_evidence(monkeypatch):
    store = StructuredUIVisualTargetEvidenceStore()
    result = produce_structured_ui_visual_target_evidence(
        **inputs(monkeypatch, x=100, y=100),
        store=store,
        clock=sequence_clock(104.0, 109.0, 109.25, 109.5),
    )
    assert result.status == PRODUCTION_STATUS_UNKNOWN
    assert result.diagnostics == ("point_binding_unavailable",)


def test_visual_mismatch_is_not_promoted_to_carrier(monkeypatch):
    verification = visual(x=251)
    store = StructuredUIVisualTargetEvidenceStore()
    values = inputs(monkeypatch, verification=verification)
    values["vision_x"] = 250
    result = produce_structured_ui_visual_target_evidence(
        **values,
        store=store,
        clock=sequence_clock(104.0, 109.0, 109.25, 109.5, 109.75),
    )
    assert result.status == PRODUCTION_STATUS_UNKNOWN
    assert result.diagnostics == ("dual_evidence_unavailable",)


def test_invalid_store_fails_before_evidence_production(monkeypatch):
    result = produce_structured_ui_visual_target_evidence(
        **inputs(monkeypatch),
        store=object(),
        clock=lambda: 104.0,
    )
    assert result.status == PRODUCTION_STATUS_UNKNOWN
    assert result.diagnostics == ("invalid_store",)


def test_noncallable_clock_is_rejected(monkeypatch):
    with pytest.raises(TypeError, match="clock must be callable"):
        produce_structured_ui_visual_target_evidence(
            **inputs(monkeypatch),
            store=StructuredUIVisualTargetEvidenceStore(),
            clock=None,
        )


def test_carrier_issue_failure_is_sanitized_and_leaves_no_pending_carrier(
    monkeypatch,
):
    store = StructuredUIVisualTargetEvidenceStore()

    def fail_issue(self, result, *, clock):
        raise RuntimeError("SECRET INTERNAL ERROR")

    monkeypatch.setattr(
        StructuredUIVisualTargetEvidenceStore,
        "issue",
        fail_issue,
    )
    result = produce_structured_ui_visual_target_evidence(
        **inputs(monkeypatch),
        store=store,
        clock=sequence_clock(104.0, 109.0, 109.25, 109.5, 109.75),
    )
    assert result.status == PRODUCTION_STATUS_UNKNOWN
    assert result.diagnostics == ("carrier_issue_failed",)
    assert "SECRET" not in repr(result)


def test_production_result_is_immutable(monkeypatch):
    _store, result = produce(monkeypatch)
    with pytest.raises(FrozenInstanceError):
        result.status = PRODUCTION_STATUS_UNKNOWN
    with pytest.raises(FrozenInstanceError):
        result.production.carrier = None


@pytest.mark.parametrize(
    "name",
    [
        "allowed",
        "authorized",
        "permission",
        "attestation",
        "semantic_target_verified",
        "execute",
        "click",
    ],
)
def test_production_has_no_authority_surface(monkeypatch, name):
    _store, result = produce(monkeypatch)
    assert not hasattr(result.production, name)
    assert not hasattr(result, name)


def test_no_dict_reconstruction_or_serialization_surface():
    assert not hasattr(StructuredUIVisualTargetEvidenceProductionResult, "from_dict")
    assert not hasattr(StructuredUIVisualTargetEvidenceProductionResult, "to_dict")


def test_module_imports_exclude_authority_execution_collection_and_mission_service():
    path = Path(__file__).with_name("gui_target_evidence_producer.py")
    tree = ast.parse(path.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden_fragments = (
        "mission_service",
        "permissions",
        "gui_argument_authority",
        "gui_intent_authority",
        "gui_target_evidence_consumption",
        "computer_tools",
        "ui_observation.runtime",
        "desktop.runtime",
        "pyautogui",
    )
    for module in imported:
        assert not any(fragment in module for fragment in forbidden_fragments)
