from dataclasses import FrozenInstanceError, replace
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

from app.agent.gui_target_dual_evidence import (
    DUAL_EVIDENCE_STATUS_MATCHED,
    DUAL_EVIDENCE_STATUS_UNKNOWN,
    StructuredUIVisualTargetEvidence,
    StructuredUIVisualTargetEvidenceResult,
    conjoin_structured_ui_and_visual_target_evidence,
)
from app.agent.gui_target_point_binding import (
    POINT_BINDING_STATUS_MISMATCH,
    StructuredUITargetPointBindingResult,
    bind_structured_ui_target_point,
)
from app.agent.test_gui_target_orchestration import orchestrate
from app.agent.test_gui_target_point_binding import make_active_screen
from app.vision.gui_target_verifier import (
    GuiTargetVerificationResult,
    TARGET_STATUS_NOT_SATISFIED,
    TARGET_STATUS_SATISFIED,
    TARGET_STATUS_UNKNOWN,
)
from app.vision.observation import SCREEN_OBSERVATIONS


GOAL = "Click Save"
IMAGE_SHA = hashlib.sha256(b"image").hexdigest()
REGION_SHA = hashlib.sha256(b"region").hexdigest()


@pytest.fixture(autouse=True)
def clear_screen_store():
    SCREEN_OBSERVATIONS.clear()
    yield
    SCREEN_OBSERVATIONS.clear()


def goal_digest(goal=GOAL):
    return hashlib.sha256(goal.strip().encode("utf-8")).hexdigest()


def point_binding(monkeypatch, *, x=250, y=175, now=109.5):
    make_active_screen(monkeypatch)
    result = bind_structured_ui_target_point(
        orchestrate(),
        x,
        y,
        clock=lambda: now,
    )
    assert result.matched
    return result


def visual(
    *,
    status=TARGET_STATUS_SATISFIED,
    observation_id="8" * 32,
    x=250,
    y=175,
    goal_sha256=None,
    summary="matched",
    evidence="Save button visible at the candidate point",
    image_sha256=IMAGE_SHA,
    target_region_sha256=REGION_SHA,
):
    return GuiTargetVerificationResult(
        status=status,
        summary=summary,
        evidence=evidence,
        observation_id=observation_id,
        x=x,
        y=y,
        goal_sha256=goal_digest() if goal_sha256 is None else goal_sha256,
        image_sha256=image_sha256,
        target_region_sha256=target_region_sha256,
    )


def conjoin(monkeypatch, *, point=None, verification=None, goal=GOAL, now=109.75):
    point = point or point_binding(monkeypatch)
    verification = verification or visual()
    return point, verification, conjoin_structured_ui_and_visual_target_evidence(
        point,
        verification,
        goal,
        clock=lambda: now,
    )


def test_happy_path_preserves_exact_b8d_and_visual_objects(monkeypatch):
    point, verification, result = conjoin(monkeypatch)
    assert result.status == DUAL_EVIDENCE_STATUS_MATCHED
    assert result.matched
    evidence = result.evidence
    assert evidence.point_binding_result is point
    assert evidence.point_binding is point.binding
    assert evidence.visual_verification is verification
    assert evidence.screen_observation_id == point.binding.screen_observation_id
    assert evidence.ui_observation_id == point.binding.ui_observation_id
    assert evidence.vision_point == (250, 175)
    assert evidence.native_point == point.binding.native_point
    assert evidence.structured_evidence is point.binding.evidence
    assert evidence.target_region_sha256 == REGION_SHA
    assert evidence.human_goal_sha256 == goal_digest()
    assert evidence.assembled_at_monotonic == 109.75
    assert evidence.expires_at_monotonic == point.binding.expires_at_monotonic


def test_human_goal_is_stripped_exactly_like_safe_verifier(monkeypatch):
    point = point_binding(monkeypatch)
    verification = visual(goal_sha256=goal_digest("  Click Save  "))
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        verification,
        "  Click Save  ",
        clock=lambda: 109.75,
    )
    assert result.matched
    assert result.evidence.human_goal_sha256 == goal_digest()


@pytest.mark.parametrize("goal", [None, "", "   ", 7])
def test_invalid_human_goal_fails_closed(monkeypatch, goal):
    point = point_binding(monkeypatch)
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        visual(),
        goal,
        clock=lambda: 109.75,
    )
    assert result.status == DUAL_EVIDENCE_STATUS_UNKNOWN
    assert result.diagnostics == ("invalid_human_goal",)


def test_wrong_screen_observation_is_rejected(monkeypatch):
    point = point_binding(monkeypatch)
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        visual(observation_id="9" * 32),
        GOAL,
        clock=lambda: 109.75,
    )
    assert result.diagnostics == ("screen_observation_mismatch",)


@pytest.mark.parametrize("x,y", [(249, 175), (250, 174)])
def test_wrong_candidate_point_is_rejected(monkeypatch, x, y):
    point = point_binding(monkeypatch)
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        visual(x=x, y=y),
        GOAL,
        clock=lambda: 109.75,
    )
    assert result.diagnostics == ("candidate_point_mismatch",)


def test_wrong_human_goal_digest_is_rejected(monkeypatch):
    point = point_binding(monkeypatch)
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        visual(goal_sha256=hashlib.sha256(b"different").hexdigest()),
        GOAL,
        clock=lambda: 109.75,
    )
    assert result.diagnostics == ("human_goal_mismatch",)


@pytest.mark.parametrize("status", [TARGET_STATUS_NOT_SATISFIED, TARGET_STATUS_UNKNOWN])
def test_visual_result_must_be_satisfied(monkeypatch, status):
    point = point_binding(monkeypatch)
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        visual(status=status),
        GOAL,
        clock=lambda: 109.75,
    )
    assert result.diagnostics == ("visual_verification_unavailable",)


@pytest.mark.parametrize(
    "changes",
    [
        {"summary": ""},
        {"evidence": ""},
        {"image_sha256": "bad"},
        {"target_region_sha256": "bad"},
    ],
)
def test_malformed_satisfied_visual_evidence_fails_closed(monkeypatch, changes):
    point = point_binding(monkeypatch)
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        visual(**changes),
        GOAL,
        clock=lambda: 109.75,
    )
    assert result.diagnostics == ("invalid_visual_verification",)


def test_invalid_visual_result_type_fails_closed(monkeypatch):
    point = point_binding(monkeypatch)
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        object(),
        GOAL,
        clock=lambda: 109.75,
    )
    assert result.diagnostics == ("invalid_visual_verification",)


def test_nonmatched_b8d_result_cannot_become_dual_evidence(monkeypatch):
    make_active_screen(monkeypatch)
    point = bind_structured_ui_target_point(
        orchestrate(),
        100,
        100,
        clock=lambda: 109.5,
    )
    assert point.status == POINT_BINDING_STATUS_MISMATCH
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        visual(x=100, y=100),
        GOAL,
        clock=lambda: 109.75,
    )
    assert result.diagnostics == ("point_binding_unavailable",)


def test_invalid_b8d_result_type_fails_closed():
    result = conjoin_structured_ui_and_visual_target_evidence(
        object(),
        visual(),
        GOAL,
        clock=lambda: 109.75,
    )
    assert result.diagnostics == ("invalid_point_binding",)


def test_expired_b8d_evidence_cannot_be_conjoined(monkeypatch):
    point = point_binding(monkeypatch)
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        visual(),
        GOAL,
        clock=lambda: point.binding.expires_at_monotonic,
    )
    assert result.diagnostics == ("point_binding_not_current",)


def test_constructor_requires_exact_binding_from_b8d_result(monkeypatch):
    _point, _verification, result = conjoin(monkeypatch)
    good = result.evidence
    clone = replace(good.point_binding)
    assert clone == good.point_binding
    assert clone is not good.point_binding
    with pytest.raises(ValueError, match="exact matched B8D binding graph"):
        replace(good, point_binding=clone)


def test_constructor_rejects_visual_point_substitution(monkeypatch):
    _point, _verification, result = conjoin(monkeypatch)
    good = result.evidence
    changed = replace(good.visual_verification, x=good.visual_verification.x + 1)
    with pytest.raises(ValueError, match="different candidate point"):
        replace(good, visual_verification=changed)


def test_constructor_rejects_goal_digest_substitution(monkeypatch):
    _point, _verification, result = conjoin(monkeypatch)
    good = result.evidence
    with pytest.raises(ValueError, match="different human goal"):
        replace(good, human_goal_sha256=hashlib.sha256(b"other").hexdigest())


def test_evidence_lifetime_is_b8d_only_and_explicitly_bounded(monkeypatch):
    _point, _verification, result = conjoin(monkeypatch)
    evidence = result.evidence
    assert evidence.is_current(109.75)
    assert evidence.is_current(evidence.expires_at_monotonic - 0.001)
    assert not evidence.is_current(evidence.expires_at_monotonic)
    assert not hasattr(evidence.visual_verification, "verified_at_monotonic")


def test_evidence_and_result_are_immutable(monkeypatch):
    _point, _verification, result = conjoin(monkeypatch)
    with pytest.raises(FrozenInstanceError):
        result.evidence.human_goal_sha256 = "x"
    with pytest.raises(FrozenInstanceError):
        result.status = DUAL_EVIDENCE_STATUS_UNKNOWN


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
def test_dual_evidence_has_no_authority_surface(monkeypatch, name):
    _point, _verification, result = conjoin(monkeypatch)
    assert not hasattr(result.evidence, name)
    assert not hasattr(result, name)


def test_no_dict_reconstruction_or_serialization_surface():
    assert not hasattr(StructuredUIVisualTargetEvidence, "from_dict")
    assert not hasattr(StructuredUIVisualTargetEvidence, "to_dict")
    assert not hasattr(StructuredUIVisualTargetEvidenceResult, "from_dict")
    assert not hasattr(StructuredUIVisualTargetEvidenceResult, "to_dict")


def test_result_contract_rejects_forged_combinations(monkeypatch):
    _point, _verification, matched = conjoin(monkeypatch)
    with pytest.raises(ValueError):
        StructuredUIVisualTargetEvidenceResult(
            status=DUAL_EVIDENCE_STATUS_MATCHED,
            evidence=None,
        )
    with pytest.raises(ValueError):
        StructuredUIVisualTargetEvidenceResult(
            status=DUAL_EVIDENCE_STATUS_UNKNOWN,
            evidence=matched.evidence,
            diagnostics=("clock_unavailable",),
        )
    with pytest.raises(ValueError):
        StructuredUIVisualTargetEvidenceResult(
            status=DUAL_EVIDENCE_STATUS_UNKNOWN,
            diagnostics=("made_up",),
        )


def test_noncallable_clock_is_rejected(monkeypatch):
    point = point_binding(monkeypatch)
    with pytest.raises(TypeError):
        conjoin_structured_ui_and_visual_target_evidence(
            point,
            visual(),
            GOAL,
            clock=None,
        )


def test_clock_failure_fails_closed_without_exception_text(monkeypatch):
    point = point_binding(monkeypatch)
    result = conjoin_structured_ui_and_visual_target_evidence(
        point,
        visual(),
        GOAL,
        clock=lambda: (_ for _ in ()).throw(RuntimeError("private details")),
    )
    assert result.diagnostics == ("clock_unavailable",)
    assert "private" not in repr(result)


def test_module_has_no_permission_attestation_execution_or_mission_service_surface():
    import ast
    import app.agent.gui_target_dual_evidence as imported_module

    module = Path(__file__).with_name("gui_target_dual_evidence.py")
    tree = ast.parse(module.read_text())

    direct_imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            direct_imports.update(
                alias.name
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            direct_imports.add(
                node.module or ""
            )

    forbidden_import_prefixes = (
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
            imported == prefix
            or imported.startswith(prefix + ".")
            for prefix in forbidden_import_prefixes
        ), imported

    for name in (
        "click",
        "execute",
        "authorize",
        "authorize_runtime_gui_arguments",
        "semantic_target_verified",
        "attestation",
        "permission",
        "GUI_TARGET_ATTESTATIONS",
        "GuiTargetAttestation",
    ):
        assert not hasattr(imported_module, name)
