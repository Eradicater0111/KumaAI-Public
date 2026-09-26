from dataclasses import FrozenInstanceError, replace

import pytest

from app.agent.gui_target_evidence import EVIDENCE_STATUS_AVAILABLE
from app.agent.gui_target_intent import StructuredUITargetIntent
from app.agent.gui_target_orchestration import (
    ORCHESTRATION_STATUS_AVAILABLE,
    ORCHESTRATION_STATUS_UNKNOWN,
    StructuredUITargetOrchestrationResult,
    orchestrate_structured_ui_target_evidence,
)
from app.agent.test_gui_target_evidence import (
    NEW_UI,
    OLD_UI,
    fresh_binding,
    item,
    make_intent,
    observation,
    old_binding,
)
from app.ui_observation.target_resolution import (
    TARGET_STATUS_RESOLVED,
    TARGET_STATUS_UNKNOWN,
)
from app.ui_observation.target_revalidation import (
    CONTINUITY_STATUS_MATCHED,
    CONTINUITY_STATUS_MISMATCH,
)


def sequence_clock(*values):
    iterator = iter(values)
    return lambda: next(iterator)


def orchestrate(
    *,
    intent=None,
    original=None,
    original_source=None,
    fresh=None,
    fresh_source=None,
    clock=None,
):
    intent = intent or make_intent()
    original = original or observation(item())
    original_source = original_source or old_binding()
    fresh = fresh or observation(
        item(
            position_x=420.0,
            position_y=330.0,
            width=160.0,
            height=55.0,
        ),
        observation_id=NEW_UI,
        captured=106.0,
    )
    fresh_source = fresh_source or fresh_binding()
    clock = clock or sequence_clock(104.0, 109.0, 109.25)

    return orchestrate_structured_ui_target_evidence(
        intent,
        original,
        original_source,
        fresh,
        fresh_source,
        clock=clock,
    )


def test_happy_path_preserves_one_authoritative_selector_through_all_stages():
    intent = make_intent()
    result = orchestrate(intent=intent)

    assert result.status == ORCHESTRATION_STATUS_AVAILABLE
    assert result.available
    assert result.intent is intent

    selector = result.selector
    resolution = result.resolution_result.resolution
    revalidation = result.revalidation_result.revalidation
    evidence = result.evidence

    assert result.resolution_result.status == TARGET_STATUS_RESOLVED
    assert result.revalidation_result.status == CONTINUITY_STATUS_MATCHED
    assert result.evidence_result.status == EVIDENCE_STATUS_AVAILABLE

    assert resolution.selector is selector
    assert revalidation.original is resolution
    assert revalidation.selector is selector
    assert revalidation.fresh_resolution.selector is selector
    assert evidence.intent is intent
    assert evidence.selector is selector
    assert evidence.revalidation_result is result.revalidation_result
    assert evidence.revalidation is revalidation
    assert evidence.original_ui_observation_id == OLD_UI
    assert evidence.ui_observation_id == NEW_UI


def test_b8c_constructs_authoritative_selector_once(monkeypatch):
    produced = []
    original = StructuredUITargetIntent.to_selector

    def counted(self):
        selector = original(self)
        produced.append(selector)
        return selector

    monkeypatch.setattr(
        StructuredUITargetIntent,
        "to_selector",
        counted,
    )

    intent = make_intent()
    result = orchestrate(intent=intent)

    assert result.available

    # B8C creates the authoritative selector exactly once.
    #
    # B8B performs two independent equal-value integrity checks:
    # one in assemble_structured_ui_target_evidence() and one again
    # in StructuredUITargetEvidence.__post_init__().
    #
    # Those two comparison selectors must never replace the exact
    # authoritative selector already carried by B6/B7/B8B.
    assert len(produced) == 3

    authoritative = produced[0]

    assert authoritative is result.selector

    assert produced[1] == authoritative
    assert produced[1] is not authoritative

    assert produced[2] == authoritative
    assert produced[2] is not authoritative

    assert (
        result.resolution_result.resolution.selector
        is authoritative
    )
    assert (
        result.revalidation_result.revalidation.selector
        is authoritative
    )
    assert result.evidence.selector is authoritative


def test_initial_resolution_failure_stops_before_b7_and_b8b():
    result = orchestrate(
        original=observation(item(title="Other")),
        clock=sequence_clock(104.0),
    )

    assert result.status == ORCHESTRATION_STATUS_UNKNOWN
    assert result.diagnostics == ("initial_resolution_unavailable",)
    assert result.resolution_result.status == TARGET_STATUS_UNKNOWN
    assert result.resolution_result.diagnostics == ("no_semantic_match",)
    assert result.revalidation_result is None
    assert result.evidence_result is None
    assert result.evidence is None


def test_ambiguous_initial_target_stops_before_revalidation():
    result = orchestrate(
        original=observation(item(), item()),
        clock=sequence_clock(104.0),
    )

    assert result.status == ORCHESTRATION_STATUS_UNKNOWN
    assert result.diagnostics == ("initial_resolution_unavailable",)
    assert not result.resolution_result.resolved
    assert result.revalidation_result is None


def test_b7_mismatch_is_not_promoted_to_b8b_evidence():
    fresh = observation(
        item(),
        item(),
        observation_id=NEW_UI,
        captured=106.0,
    )
    result = orchestrate(
        fresh=fresh,
        clock=sequence_clock(104.0, 109.0),
    )

    assert result.status == ORCHESTRATION_STATUS_UNKNOWN
    assert result.diagnostics == ("continuity_unavailable",)
    assert result.revalidation_result.status == CONTINUITY_STATUS_MISMATCH
    assert result.revalidation_result.diagnostics == (
        "fresh_target_ambiguous",
    )
    assert result.evidence_result is None


def test_b8b_expiry_failure_is_not_promoted_to_available():
    result = orchestrate(
        clock=sequence_clock(104.0, 109.0, 115.0),
    )

    assert result.status == ORCHESTRATION_STATUS_UNKNOWN
    assert result.diagnostics == ("evidence_unavailable",)
    assert result.evidence_result is not None
    assert not result.evidence_result.available
    assert result.evidence_result.diagnostics == ("evidence_expired",)
    assert result.evidence is None


def test_invalid_intent_fails_before_selector_or_evidence():
    result = orchestrate_structured_ui_target_evidence(
        object(),
        observation(item()),
        old_binding(),
        observation(
            item(),
            observation_id=NEW_UI,
            captured=106.0,
        ),
        fresh_binding(),
        clock=sequence_clock(104.0, 109.0, 109.25),
    )

    assert result.status == ORCHESTRATION_STATUS_UNKNOWN
    assert result.diagnostics == ("invalid_intent",)
    assert result.intent is None
    assert result.selector is None
    assert result.resolution_result is None


def test_noncallable_clock_is_rejected():
    with pytest.raises(TypeError):
        orchestrate_structured_ui_target_evidence(
            make_intent(),
            observation(item()),
            old_binding(),
            observation(
                item(),
                observation_id=NEW_UI,
                captured=106.0,
            ),
            fresh_binding(),
            clock=None,
        )


def test_clock_failure_is_preserved_as_b6_failure_without_exception_leakage():
    result = orchestrate(
        clock=lambda: (_ for _ in ()).throw(RuntimeError("private details")),
    )

    assert result.status == ORCHESTRATION_STATUS_UNKNOWN
    assert result.diagnostics == ("initial_resolution_unavailable",)
    assert result.resolution_result.diagnostics == ("clock_unavailable",)
    assert "private" not in repr(result)


def test_available_result_is_immutable_and_exposes_fresh_b8b_evidence_only():
    result = orchestrate()

    with pytest.raises(FrozenInstanceError):
        result.selector = None

    assert result.evidence is result.evidence_result.evidence
    assert result.evidence.ax_geometry == (
        420.0,
        330.0,
        160.0,
        55.0,
    )


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
        "x",
        "y",
    ],
)
def test_orchestration_has_no_authority_or_click_surface(name):
    result = orchestrate()
    assert not hasattr(result, name)


def test_orchestration_has_no_dict_reconstruction_or_serialization_surface():
    assert not hasattr(
        StructuredUITargetOrchestrationResult,
        "from_dict",
    )
    assert not hasattr(
        StructuredUITargetOrchestrationResult,
        "to_dict",
    )


def test_available_constructor_rejects_equal_value_selector_substitution():
    good = orchestrate()
    substituted = good.intent.to_selector()

    assert substituted == good.selector
    assert substituted is not good.selector

    with pytest.raises(ValueError, match="exact selector"):
        replace(
            good,
            selector=substituted,
        )


def test_available_constructor_rejects_b6_graph_substitution():
    good = orchestrate()
    changed_resolution = replace(
        good.resolution_result.resolution,
        resolved_at_monotonic=104.1,
    )
    substituted_result = replace(
        good.resolution_result,
        resolution=changed_resolution,
    )

    with pytest.raises(ValueError):
        replace(
            good,
            resolution_result=substituted_result,
        )


def test_unknown_constructor_rejects_available_evidence():
    good = orchestrate()

    with pytest.raises(ValueError, match="cannot carry available"):
        StructuredUITargetOrchestrationResult(
            status=ORCHESTRATION_STATUS_UNKNOWN,
            intent=good.intent,
            selector=good.selector,
            resolution_result=good.resolution_result,
            revalidation_result=good.revalidation_result,
            evidence_result=good.evidence_result,
            diagnostics=("evidence_unavailable",),
        )
