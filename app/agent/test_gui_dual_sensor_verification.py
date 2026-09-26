from dataclasses import fields
from types import SimpleNamespace

from app.agent.gui_dual_sensor_verification import (
    RuntimeDualSensorVisionVerificationResult,
    verify_runtime_dual_sensor_vision_target,
)


INTENT = {
    "role": "AXButton",
    "text": "Save",
    "require_enabled": True,
    "require_positive_area": True,
}

MODEL_POINT = (
    100,
    200,
)

DERIVED_POINT = (
    250,
    179,
)


def corroboration():
    return SimpleNamespace(
        original_observation=object(),
        original_binding=object(),
        fresh_observation=object(),
        fresh_binding=object(),
        fresh_screen_observation_id=(
            "screen-fresh"
        ),
    )


def available_refresh():
    return SimpleNamespace(
        available=True,
        corroboration=corroboration(),
    )


def matched_derivation():
    return SimpleNamespace(
        matched=True,
        screen_observation_id=(
            "screen-fresh"
        ),
        vision_point=DERIVED_POINT,
    )


def satisfied_visual():
    return SimpleNamespace(
        satisfied=True,
        summary="matched",
    )


def issued_production(visual):
    return SimpleNamespace(
        issued=True,
        production=SimpleNamespace(
            visual_verification=visual,
        ),
    )


def matched_consumption(visual):
    return SimpleNamespace(
        matched=True,
        consumption=SimpleNamespace(
            visual_verification=visual,
        ),
    )


def base_kwargs():
    return {
        "raw_target_intent": dict(INTENT),
        "original_observation_id": (
            "screen-old"
        ),
        "x": MODEL_POINT[0],
        "y": MODEL_POINT[1],
        "human_goal": "Click Save.",
        "gui_target_verifier": object(),
    }


def default_dependencies(
    visual,
):
    return {
        "refresh_fn": (
            lambda observation_id:
            available_refresh()
        ),
        "derive_fn": (
            lambda *args:
            matched_derivation()
        ),
        "visual_verify_fn": (
            lambda *args, **kwargs:
            visual
        ),
        "produce_fn": (
            lambda *args:
            issued_production(
                visual
            )
        ),
        "consume_fn": (
            lambda supplied, **kwargs:
            matched_consumption(
                supplied
            )
        ),
    }


def test_invalid_semantic_intent_fails_before_refresh_or_derivation():
    calls = []

    result = (
        verify_runtime_dual_sensor_vision_target(
            **{
                **base_kwargs(),
                "raw_target_intent": {
                    "text": "Save",
                    "x": 100,
                },
            },
            refresh_fn=(
                lambda observation_id:
                calls.append(
                    "refresh"
                )
            ),
            derive_fn=(
                lambda *args:
                calls.append(
                    "derive"
                )
            ),
        )
    )

    assert not result.matched

    assert result.diagnostics == (
        "invalid_target_intent",
    )

    assert calls == []


def test_missing_original_context_fails_before_derivation():
    calls = []

    result = (
        verify_runtime_dual_sensor_vision_target(
            **base_kwargs(),
            refresh_fn=(
                lambda observation_id:
                SimpleNamespace(
                    available=False,
                    corroboration=None,
                )
            ),
            derive_fn=(
                lambda *args:
                calls.append(
                    "derive"
                )
            ),
        )
    )

    assert not result.matched

    assert result.diagnostics == (
        "fresh_corroboration_unavailable",
    )

    assert calls == []


def test_failed_trusted_point_derivation_blocks_visual_verifier():
    calls = []

    result = (
        verify_runtime_dual_sensor_vision_target(
            **base_kwargs(),
            refresh_fn=(
                lambda observation_id:
                available_refresh()
            ),
            derive_fn=(
                lambda *args:
                SimpleNamespace(
                    matched=False,
                    screen_observation_id="",
                    vision_point=None,
                )
            ),
            visual_verify_fn=(
                lambda *args, **kwargs:
                calls.append(
                    "visual"
                )
            ),
        )
    )

    assert not result.matched

    assert result.diagnostics == (
        "trusted_point_derivation_unavailable",
    )

    assert calls == []


def test_derived_point_must_belong_to_fresh_observation():
    visual = satisfied_visual()

    result = (
        verify_runtime_dual_sensor_vision_target(
            **base_kwargs(),
            refresh_fn=(
                lambda observation_id:
                available_refresh()
            ),
            derive_fn=(
                lambda *args:
                SimpleNamespace(
                    matched=True,
                    screen_observation_id=(
                        "other-screen"
                    ),
                    vision_point=(
                        DERIVED_POINT
                    ),
                )
            ),
            visual_verify_fn=(
                lambda *args, **kwargs:
                visual
            ),
        )
    )

    assert not result.matched

    assert result.diagnostics == (
        "trusted_point_derivation_unavailable",
    )


def test_visual_verifier_runs_once_on_fresh_observation_and_derived_point():
    calls = []
    visual = satisfied_visual()

    def verify(
        verifier,
        *,
        goal,
        observation_id,
        x,
        y,
    ):
        calls.append(
            (
                verifier,
                goal,
                observation_id,
                x,
                y,
            )
        )

        return visual

    result = (
        verify_runtime_dual_sensor_vision_target(
            **base_kwargs(),
            refresh_fn=(
                lambda observation_id:
                available_refresh()
            ),
            derive_fn=(
                lambda *args:
                matched_derivation()
            ),
            visual_verify_fn=verify,
            produce_fn=(
                lambda *args:
                issued_production(
                    visual
                )
            ),
            consume_fn=(
                lambda supplied, **kwargs:
                matched_consumption(
                    supplied
                )
            ),
        )
    )

    assert result.matched
    assert len(calls) == 1

    assert calls[0][2] == (
        "screen-fresh"
    )

    assert calls[0][3:] == (
        DERIVED_POINT
    )

    # Proves model proposal is not forwarded.
    assert calls[0][3:] != (
        MODEL_POINT
    )

    assert result.fresh_observation_id == (
        "screen-fresh"
    )

    assert result.vision_point == (
        DERIVED_POINT
    )

    assert result.visual_verification is visual


def test_unsatisfied_visual_never_reaches_b8j():
    calls = []

    result = (
        verify_runtime_dual_sensor_vision_target(
            **base_kwargs(),
            refresh_fn=(
                lambda observation_id:
                available_refresh()
            ),
            derive_fn=(
                lambda *args:
                matched_derivation()
            ),
            visual_verify_fn=(
                lambda *args, **kwargs:
                SimpleNamespace(
                    satisfied=False,
                    summary="mismatch",
                )
            ),
            produce_fn=(
                lambda *args, **kwargs:
                calls.append(
                    "produce"
                )
            ),
        )
    )

    assert not result.matched

    assert result.diagnostics == (
        "visual_verification_unavailable",
    )

    assert calls == []


def test_b8j_receives_exact_visual_object_and_derived_point():
    visual = satisfied_visual()
    seen = []

    def produce(*args):
        seen.append(
            (
                args[5],
                args[6],
                args[-2],
            )
        )

        return issued_production(
            args[-2]
        )

    result = (
        verify_runtime_dual_sensor_vision_target(
            **base_kwargs(),
            refresh_fn=(
                lambda observation_id:
                available_refresh()
            ),
            derive_fn=(
                lambda *args:
                matched_derivation()
            ),
            visual_verify_fn=(
                lambda *args, **kwargs:
                visual
            ),
            produce_fn=produce,
            consume_fn=(
                lambda supplied, **kwargs:
                matched_consumption(
                    supplied
                )
            ),
        )
    )

    assert result.matched

    assert seen == [
        (
            DERIVED_POINT[0],
            DERIVED_POINT[1],
            visual,
        )
    ]


def test_b8g_receives_same_visual_object_and_derived_point():
    visual = satisfied_visual()
    seen = []

    def consume(
        supplied,
        **kwargs,
    ):
        seen.append(
            (
                supplied,
                kwargs,
            )
        )

        return matched_consumption(
            supplied
        )

    dependencies = (
        default_dependencies(
            visual
        )
    )

    dependencies[
        "consume_fn"
    ] = consume

    result = (
        verify_runtime_dual_sensor_vision_target(
            **base_kwargs(),
            **dependencies,
        )
    )

    assert result.matched

    supplied, kwargs = seen[0]

    assert supplied is visual

    assert kwargs[
        "observation_id"
    ] == "screen-fresh"

    assert (
        kwargs["x"],
        kwargs["y"],
    ) == DERIVED_POINT

    assert result.visual_verification is visual


def test_reconstructed_visual_object_is_rejected():
    visual = satisfied_visual()
    reconstructed = (
        satisfied_visual()
    )

    result = (
        verify_runtime_dual_sensor_vision_target(
            **base_kwargs(),
            refresh_fn=(
                lambda observation_id:
                available_refresh()
            ),
            derive_fn=(
                lambda *args:
                matched_derivation()
            ),
            visual_verify_fn=(
                lambda *args, **kwargs:
                visual
            ),
            produce_fn=(
                lambda *args:
                issued_production(
                    visual
                )
            ),
            consume_fn=(
                lambda supplied, **kwargs:
                matched_consumption(
                    reconstructed
                )
            ),
        )
    )

    assert not result.matched

    assert result.diagnostics == (
        "dual_evidence_consumption_unavailable",
    )


def test_result_contract_carries_only_fresh_point_evidence_not_authority():
    visual = satisfied_visual()

    result = (
        RuntimeDualSensorVisionVerificationResult(
            status="matched",
            fresh_observation_id=(
                "screen-fresh"
            ),
            vision_x=(
                DERIVED_POINT[0]
            ),
            vision_y=(
                DERIVED_POINT[1]
            ),
            visual_verification=visual,
        )
    )

    assert result.matched

    assert result.vision_point == (
        DERIVED_POINT
    )

    forbidden = {
        "allowed",
        "approved",
        "permission",
        "semantic_target_verified",
        "attestation",
        "button",
        "clicks",
        "execute",
    }

    names = {
        item.name
        for item in fields(
            RuntimeDualSensorVisionVerificationResult
        )
    }

    assert not (
        names
        & forbidden
    )
