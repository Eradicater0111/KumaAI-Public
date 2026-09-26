import inspect

import pytest

from app.agent.gui_dual_sensor_verification import (
    RuntimeDualSensorVisionVerificationResult,
    VERIFICATION_STATUS_MATCHED,
    verify_runtime_dual_sensor_vision_target,
)


def test_nonconsuming_switch_defaults_to_existing_pointer_behavior():
    signature = inspect.signature(
        verify_runtime_dual_sensor_vision_target
    )

    parameter = (
        signature.parameters[
            "consume_evidence"
        ]
    )

    assert parameter.default is True


def test_result_carries_exact_boolean_consumption_marker():
    visual = object()

    reserved = (
        RuntimeDualSensorVisionVerificationResult(
            status=VERIFICATION_STATUS_MATCHED,
            fresh_observation_id="fresh-1",
            vision_x=10,
            vision_y=20,
            visual_verification=visual,
            evidence_consumed=False,
        )
    )

    consumed = (
        RuntimeDualSensorVisionVerificationResult(
            status=VERIFICATION_STATUS_MATCHED,
            fresh_observation_id="fresh-1",
            vision_x=10,
            vision_y=20,
            visual_verification=visual,
            evidence_consumed=True,
        )
    )

    assert reserved.matched
    assert consumed.matched

    assert reserved.evidence_consumed is False
    assert consumed.evidence_consumed is True


@pytest.mark.parametrize(
    "value",
    (
        0,
        1,
        None,
        "yes",
        object(),
    ),
)
def test_result_rejects_nonboolean_consumption_marker(
    value,
):
    with pytest.raises(
        ValueError,
        match="consumption marker",
    ):
        RuntimeDualSensorVisionVerificationResult(
            status=VERIFICATION_STATUS_MATCHED,
            fresh_observation_id="fresh-1",
            vision_x=10,
            vision_y=20,
            visual_verification=object(),
            evidence_consumed=value,
        )


def test_nonconsuming_exit_occurs_before_b8g_claim():
    source = inspect.getsource(
        verify_runtime_dual_sensor_vision_target
    )

    reservation = source.index(
        "if not consume_evidence:"
    )

    consumption = source.index(
        "consumption_result ="
    )

    assert reservation < consumption


def test_nonconsuming_path_does_not_claim_physical_authority():
    source = inspect.getsource(
        verify_runtime_dual_sensor_vision_target
    )

    reservation_block = source[
        source.index(
            "if not consume_evidence:"
        ):
        source.index(
            "# B8G — CLAIM CARRIER"
        )
    ]

    assert (
        "evidence_consumed=False"
        in reservation_block
    )

    assert "consume_fn(" not in reservation_block


def test_dual_result_can_preserve_exact_semantic_identity():
    semantic = object()
    visual = object()

    result = (
        RuntimeDualSensorVisionVerificationResult(
            status=VERIFICATION_STATUS_MATCHED,
            fresh_observation_id="fresh-1",
            vision_x=10,
            vision_y=20,
            visual_verification=visual,
            semantic_result=semantic,
            evidence_consumed=False,
        )
    )

    assert (
        result.semantic_result
        is semantic
    )


def test_dual_verifier_recovers_semantic_from_exact_b8j_production():
    source = inspect.getsource(
        verify_runtime_dual_sensor_vision_target
    )

    compact = "".join(
        source.split()
    )

    assert (
        "production.orchestration_result.revalidation_result"
        in compact
    )

    reservation = source.index(
        "if not consume_evidence:"
    )

    extraction = source.index(
        ".revalidation_result",
        reservation,
    )

    b8g = source.index(
        "consumption_result ="
    )

    assert (
        reservation
        < extraction
        < b8g
    )
