from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.integration_v2_production_policy import (
    PRODUCTION_REALTIME_TRIGGER_POLICY,
)
from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.realtime.contracts import (
    RealtimeFact,
)
from app.realtime.runtime_trigger import (
    propose_runtime_trigger,
)
from app.realtime.trigger_policy import (
    RealtimeTriggerEligibilityStatus,
    evaluate_trigger_eligibility,
)


MODULE = Path(
    "app/integration_v2_production_policy.py"
)


def make_signal(
    *,
    level,
    score,
):
    return RealtimeSignal(
        kind="policy.test",
        level=level,
        score=score,
        reason="policy test",
        fact=RealtimeFact(
            kind="policy.test",
            value={
                "score": score,
            },
            source="integration-v2f-policy-test",
            observed_at=datetime(
                2026,
                9,
                23,
                7,
                0,
                tzinfo=timezone.utc,
            ),
            expires_at=None,
        ),
        previous_fact=None,
    )


def decision(
    *,
    level,
    score,
):
    policy = (
        PRODUCTION_REALTIME_TRIGGER_POLICY
    )

    proposal = propose_runtime_trigger(
        make_signal(
            level=level,
            score=score,
        )
    )

    return evaluate_trigger_eligibility(
        proposal,
        minimum_level=policy.minimum_level,
        minimum_score=policy.minimum_score,
    )


def test_production_policy_is_high_080():
    policy = (
        PRODUCTION_REALTIME_TRIGGER_POLICY
    )

    assert (
        policy.minimum_level
        is RealtimeRelevanceLevel.HIGH
    )

    assert policy.minimum_score == 0.80
    assert policy.authority == "NONE"


def test_all_current_high_detector_floor_and_above_are_eligible():
    for score in (
        0.80,
        0.85,
        0.90,
    ):
        result = decision(
            level=RealtimeRelevanceLevel.HIGH,
            score=score,
        )

        assert (
            result.status
            is RealtimeTriggerEligibilityStatus.ELIGIBLE
        )


def test_current_medium_detector_ceiling_is_ineligible():
    result = decision(
        level=RealtimeRelevanceLevel.MEDIUM,
        score=0.65,
    )

    assert (
        result.status
        is RealtimeTriggerEligibilityStatus.INELIGIBLE
    )


def test_future_medium_score_080_remains_ineligible_by_level():
    result = decision(
        level=RealtimeRelevanceLevel.MEDIUM,
        score=0.80,
    )

    assert (
        result.status
        is RealtimeTriggerEligibilityStatus.INELIGIBLE
    )


def test_low_signal_is_ineligible():
    result = decision(
        level=RealtimeRelevanceLevel.LOW,
        score=1.00,
    )

    assert (
        result.status
        is RealtimeTriggerEligibilityStatus.INELIGIBLE
    )


def test_policy_module_declares_separate_zero_authority_boundary():
    source = MODULE.read_text()

    for marker in (
        "TRACE ELIGIBILITY != WAKE",
        "TRACE ELIGIBILITY != ATTENTION SURFACING",
        "TRACE ELIGIBILITY != PERMISSION",
        "TRACE ELIGIBILITY != EXECUTION",
        "PRODUCTION POLICY != RAPHAEL POLICY",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_policy_module_does_not_import_raphael_attention_thresholds():
    source = MODULE.read_text()

    assert "SURFACE_THRESHOLD" not in source
    assert "ESCALATE_THRESHOLD" not in source
    assert "proactive_attention" not in source
