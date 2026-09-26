"""Mission-boundary current desktop-context revalidation for click_vision."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.agent.mission_service import (
    DESKTOP_ACTION_REVALIDATION_MAX_AGE_SECONDS,
    DESKTOP_ACTION_REVALIDATION_MAX_WINDOWS,
    DESKTOP_ACTION_REVALIDATION_TIMEOUT_SECONDS,
    MissionService,
)
from app.agent.test_gui_action_grounding import (
    FakeCapabilityRegistry,
    MissionBoundaryKuma,
    SatisfiedGuiVerifier,
)
from app.agent.test_gui_target_contract import matching_result, run_step
from app.vision.gui_target_verifier import GUI_TARGET_ATTESTATIONS


OBSERVATION_ID = "obs-1"


def make_service():
    kuma = MissionBoundaryKuma(FakeCapabilityRegistry())
    service = MissionService(kuma)
    service.gui_objective_verifier = SatisfiedGuiVerifier()
    return service


def provenance():
    return SimpleNamespace(
        binding=object(),
        desktop_before=object(),
        desktop_after=object(),
    )


def revalidation(*, matched, status, code):
    return SimpleNamespace(
        matched=matched,
        status=status,
        diagnostics=(code,),
    )


def test_missing_exact_provenance_fails_before_collection():
    service = make_service()
    with patch(
        "app.agent.mission_service.SCREEN_DESKTOP_PROVENANCE.get",
        return_value=None,
    ) as get_provenance, patch(
        "app.agent.mission_service.collect_desktop_context",
    ) as collect:
        allowed, reason = service._revalidate_vision_click_desktop_context(
            OBSERVATION_ID
        )

    assert not allowed
    assert "provenance is unavailable" in reason
    get_provenance.assert_called_once_with(OBSERVATION_ID)
    collect.assert_not_called()


def test_provenance_lookup_failure_fails_closed():
    service = make_service()
    with patch(
        "app.agent.mission_service.SCREEN_DESKTOP_PROVENANCE.get",
        side_effect=RuntimeError("clock failed"),
    ), patch(
        "app.agent.mission_service.collect_desktop_context",
    ) as collect:
        allowed, reason = service._revalidate_vision_click_desktop_context(
            OBSERVATION_ID
        )

    assert not allowed
    assert "provenance lookup failed" in reason
    collect.assert_not_called()


def test_current_collection_failure_fails_closed_before_revalidator():
    service = make_service()
    with patch(
        "app.agent.mission_service.SCREEN_DESKTOP_PROVENANCE.get",
        return_value=provenance(),
    ), patch(
        "app.agent.mission_service.collect_desktop_context",
        side_effect=RuntimeError("worker failed"),
    ), patch(
        "app.agent.mission_service.revalidate_desktop_context",
    ) as revalidate:
        allowed, reason = service._revalidate_vision_click_desktop_context(
            OBSERVATION_ID
        )

    assert not allowed
    assert "collection failed" in reason
    revalidate.assert_not_called()


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            revalidation(
                matched=False,
                status="mismatch",
                code="application_changed",
            ),
            "mismatch (application_changed)",
        ),
        (
            revalidation(
                matched=False,
                status="unknown",
                code="current_context_unavailable",
            ),
            "unknown (current_context_unavailable)",
        ),
    ],
)
def test_nonmatching_revalidation_fails_closed(result, expected):
    service = make_service()
    current = object()
    with patch(
        "app.agent.mission_service.SCREEN_DESKTOP_PROVENANCE.get",
        return_value=provenance(),
    ), patch(
        "app.agent.mission_service.collect_desktop_context",
        return_value=current,
    ), patch(
        "app.agent.mission_service.revalidate_desktop_context",
        return_value=result,
    ):
        allowed, reason = service._revalidate_vision_click_desktop_context(
            OBSERVATION_ID
        )

    assert not allowed
    assert expected in reason


def test_matched_revalidation_uses_exact_provenance_and_bounded_collection():
    service = make_service()
    source = provenance()
    current = object()
    matched = revalidation(
        matched=True,
        status="matched",
        code="source_context_partial",
    )

    with patch(
        "app.agent.mission_service.SCREEN_DESKTOP_PROVENANCE.get",
        return_value=source,
    ) as get_provenance, patch(
        "app.agent.mission_service.collect_desktop_context",
        return_value=current,
    ) as collect, patch(
        "app.agent.mission_service.revalidate_desktop_context",
        return_value=matched,
    ) as revalidate:
        allowed, reason = service._revalidate_vision_click_desktop_context(
            OBSERVATION_ID
        )

    assert allowed
    assert reason == ""
    get_provenance.assert_called_once_with(OBSERVATION_ID)
    collect.assert_called_once_with(
        timeout_seconds=DESKTOP_ACTION_REVALIDATION_TIMEOUT_SECONDS,
        max_windows=DESKTOP_ACTION_REVALIDATION_MAX_WINDOWS,
    )
    revalidate.assert_called_once_with(
        source.binding,
        source.desktop_before,
        source.desktop_after,
        current,
        max_current_age_seconds=DESKTOP_ACTION_REVALIDATION_MAX_AGE_SECONDS,
    )


def test_revalidator_exception_fails_closed():
    service = make_service()
    with patch(
        "app.agent.mission_service.SCREEN_DESKTOP_PROVENANCE.get",
        return_value=provenance(),
    ), patch(
        "app.agent.mission_service.collect_desktop_context",
        return_value=object(),
    ), patch(
        "app.agent.mission_service.revalidate_desktop_context",
        side_effect=RuntimeError("unexpected"),
    ):
        allowed, reason = service._revalidate_vision_click_desktop_context(
            OBSERVATION_ID
        )

    assert not allowed
    assert "revalidation failed closed" in reason


def test_mission_desktop_failure_blocks_before_attestation_and_executor():
    GUI_TARGET_ATTESTATIONS.clear()
    service = make_service()
    service.gui_target_verifier = Mock()
    service.gui_target_verifier.verify.return_value = matching_result()

    with patch.object(
        service,
        "_revalidate_vision_click_desktop_context",
        return_value=(False, "Vision click desktop context changed."),
    ) as desktop_gate, patch(
        "app.agent.mission_service.GUI_TARGET_ATTESTATIONS.issue",
    ) as issue:
        result = run_step(service)

    assert not result.success
    assert not result.verified
    assert result.recovery_action == "escalate"
    assert result.recovery_reason == result.error
    assert "desktop context changed" in result.error
    assert service.kuma.executor.calls == []
    # B8K3 rebinds model-visible O0 to fresh trusted O1
    # before current desktop-context revalidation.
    desktop_gate.assert_called_once_with(
        "obs-fresh"
    )
    issue.assert_not_called()
    GUI_TARGET_ATTESTATIONS.clear()


def test_semantic_failure_blocks_before_desktop_revalidation():
    GUI_TARGET_ATTESTATIONS.clear()
    service = make_service()
    service.gui_target_verifier = Mock()
    bad = matching_result()
    service.gui_target_verifier.verify.return_value = SimpleNamespace(
        **{**vars(bad), "status": "unknown", "summary": "Ambiguous target."}
    )

    with patch.object(
        service,
        "_revalidate_vision_click_desktop_context",
    ) as desktop_gate:
        result = run_step(service)

    assert not result.success
    assert result.recovery_action == "escalate"
    assert service.kuma.executor.calls == []
    desktop_gate.assert_not_called()
    GUI_TARGET_ATTESTATIONS.clear()
