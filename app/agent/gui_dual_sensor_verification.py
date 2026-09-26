"""Fail-closed B8 dual-sensor verification for runtime vision clicks.

This module joins:
- B8K1 original trusted structured-screen context
- B8K2 independently refreshed structured-screen context
- B8J exact structured + visual evidence production
- B8G exact visual-object evidence consumption

It grants no permission, GUI argument authority, attestation, semantic flag,
or physical execution authority. MissionService alone decides whether a
successful result may set semantic_target_verified for the current attempt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.gui_target_intent import (
    StructuredUITargetIntent,
)


VERIFICATION_STATUS_MATCHED = "matched"
VERIFICATION_STATUS_UNKNOWN = "unknown"

VALID_VERIFICATION_STATUSES = frozenset({
    VERIFICATION_STATUS_MATCHED,
    VERIFICATION_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "invalid_request",
    "invalid_target_intent",
    "fresh_corroboration_unavailable",
    "trusted_point_derivation_unavailable",
    "visual_verification_unavailable",
    "dual_evidence_production_unavailable",
    "dual_evidence_consumption_unavailable",
    "fresh_observation_mismatch",
})


@dataclass(frozen=True)
class RuntimeDualSensorVisionVerificationResult:
    status: str
    fresh_observation_id: str = ""
    vision_x: int | None = None
    vision_y: int | None = None
    visual_verification: object | None = field(
        default=None,
        repr=False,
    )
    semantic_result: object | None = field(
        default=None,
        repr=False,
    )
    evidence_consumed: bool = False
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            type(self.evidence_consumed)
            is not bool
        ):
            raise ValueError(
                "Dual-sensor evidence-consumption marker "
                "must be boolean."
            )

        if (
            type(self.status) is not str
            or self.status not in VALID_VERIFICATION_STATUSES
        ):
            raise ValueError(
                "Invalid dual-sensor verification status."
            )

        if (
            type(self.diagnostics) is not tuple
            or any(
                type(code) is not str
                for code in self.diagnostics
            )
            or len(set(self.diagnostics))
            != len(self.diagnostics)
        ):
            raise ValueError(
                "Dual-sensor diagnostics must be immutable and unique."
            )

        if self.status == VERIFICATION_STATUS_MATCHED:
            if (
                type(self.fresh_observation_id) is not str
                or not self.fresh_observation_id
            ):
                raise ValueError(
                    "Matched dual-sensor verification requires "
                    "a fresh observation ID."
                )

            if (
                type(self.vision_x) is not int
                or type(self.vision_y) is not int
                or self.vision_x < 0
                or self.vision_y < 0
            ):
                raise ValueError(
                    "Matched dual-sensor verification requires "
                    "an exact trusted vision point."
                )

            if self.visual_verification is None:
                raise ValueError(
                    "Matched dual-sensor verification requires "
                    "the exact visual verifier object."
                )

            if self.diagnostics:
                raise ValueError(
                    "Matched dual-sensor verification has "
                    "no local diagnostics."
                )

            return

        if self.fresh_observation_id:
            raise ValueError(
                "Unknown dual-sensor verification cannot carry "
                "a fresh observation binding."
            )

        if (
            self.vision_x is not None
            or self.vision_y is not None
        ):
            raise ValueError(
                "Unknown dual-sensor verification cannot carry "
                "a trusted vision point."
            )

        if self.visual_verification is not None:
            raise ValueError(
                "Unknown dual-sensor verification cannot carry "
                "trusted visual evidence."
            )

        if (
            len(self.diagnostics) != 1
            or self.diagnostics[0] not in UNKNOWN_CODES
        ):
            raise ValueError(
                "Unknown dual-sensor verification requires "
                "one structured diagnostic."
            )

    @property
    def matched(self):
        return (
            self.status == VERIFICATION_STATUS_MATCHED
            and bool(self.fresh_observation_id)
            and type(self.vision_x) is int
            and type(self.vision_y) is int
            and self.visual_verification is not None
        )

    @property
    def vision_point(self):
        if not self.matched:
            return None

        return (
            self.vision_x,
            self.vision_y,
        )


def verify_runtime_dual_sensor_vision_target(
    *,
    raw_target_intent,
    original_observation_id,
    x,
    y,
    human_goal,
    gui_target_verifier,
    refresh_fn=None,
    derive_fn=None,
    visual_verify_fn=None,
    produce_fn=None,
    consume_fn=None,
    consume_evidence=True,
):
    """Verify one runtime click against fresh visual + AX evidence.

    The supplied x/y are model proposals only.

    B8K2 consumes the original observation context and creates a new trusted
    screen observation. K4 derives a deterministic executable point from the
    fresh structured target geometry. The visual verifier runs exactly once
    on that fresh observation and derived point. The exact returned verifier
    object then passes through B8J and B8G without reconstruction.
    """

    def unknown(code):
        return RuntimeDualSensorVisionVerificationResult(
            status=VERIFICATION_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    if (
        type(consume_evidence) is not bool
        or type(original_observation_id) is not str
        or not original_observation_id.strip()
        or type(x) is not int
        or type(y) is not int
        or type(human_goal) is not str
        or not human_goal.strip()
    ):
        return unknown("invalid_request")

    try:
        intent = StructuredUITargetIntent.from_dict(
            raw_target_intent
        )
    except Exception:
        return unknown("invalid_target_intent")

    if refresh_fn is None:
        from app.agent.gui_perception_refresh import (
            refresh_structured_ui_screen_context,
        )
        refresh_fn = refresh_structured_ui_screen_context

    if derive_fn is None:
        from app.agent.gui_target_point_derivation import (
            derive_correlated_structured_ui_target_point,
        )
        derive_fn = (
            derive_correlated_structured_ui_target_point
        )

    if visual_verify_fn is None:
        from app.vision.gui_target_verifier import (
            safe_verify_gui_target,
        )
        visual_verify_fn = safe_verify_gui_target

    if produce_fn is None:
        from app.agent.gui_target_evidence_producer import (
            produce_structured_ui_visual_target_evidence,
        )
        produce_fn = produce_structured_ui_visual_target_evidence

    if consume_fn is None:
        from app.agent.gui_target_evidence_consumption import (
            consume_structured_ui_visual_target_evidence,
        )
        consume_fn = consume_structured_ui_visual_target_evidence

    try:
        refresh_result = refresh_fn(
            original_observation_id.strip()
        )
    except Exception:
        return unknown(
            "fresh_corroboration_unavailable"
        )

    if not bool(
        getattr(
            refresh_result,
            "available",
            False,
        )
    ):
        return unknown(
            "fresh_corroboration_unavailable"
        )

    corroboration = getattr(
        refresh_result,
        "corroboration",
        None,
    )

    if corroboration is None:
        return unknown(
            "fresh_corroboration_unavailable"
        )

    fresh_observation_id = getattr(
        corroboration,
        "fresh_screen_observation_id",
        "",
    )

    if (
        type(fresh_observation_id) is not str
        or not fresh_observation_id
        or fresh_observation_id
        == original_observation_id.strip()
    ):
        return unknown(
            "fresh_observation_mismatch"
        )

    # -----------------------------------------------------
    # K4 — TRUSTED EXECUTABLE POINT DERIVATION
    # -----------------------------------------------------

    try:
        point_derivation = derive_fn(
            intent,
            corroboration.original_observation,
            corroboration.original_binding,
            corroboration.fresh_observation,
            corroboration.fresh_binding,
        )
    except Exception:
        return unknown(
            "trusted_point_derivation_unavailable"
        )

    if not bool(
        getattr(
            point_derivation,
            "matched",
            False,
        )
    ):
        return unknown(
            "trusted_point_derivation_unavailable"
        )

    derived_screen_id = getattr(
        point_derivation,
        "screen_observation_id",
        "",
    )

    derived_point = getattr(
        point_derivation,
        "vision_point",
        None,
    )

    if (
        derived_screen_id != fresh_observation_id
        or type(derived_point) is not tuple
        or len(derived_point) != 2
        or type(derived_point[0]) is not int
        or type(derived_point[1]) is not int
        or derived_point[0] < 0
        or derived_point[1] < 0
    ):
        return unknown(
            "trusted_point_derivation_unavailable"
        )

    derived_x, derived_y = (
        derived_point
    )

    # -----------------------------------------------------
    # EXACTLY ONE VISUAL VERIFIER CALL — FRESH O1 + K4 POINT
    # -----------------------------------------------------

    try:
        visual_verification = visual_verify_fn(
            gui_target_verifier,
            goal=human_goal,
            observation_id=fresh_observation_id,
            x=derived_x,
            y=derived_y,
        )
    except Exception:
        return unknown(
            "visual_verification_unavailable"
        )

    if not bool(
        getattr(
            visual_verification,
            "satisfied",
            False,
        )
    ):
        return unknown(
            "visual_verification_unavailable"
        )

    # -----------------------------------------------------
    # B8J — SAME EXACT VISUAL OBJECT
    # -----------------------------------------------------

    try:
        production_result = produce_fn(
            intent,
            corroboration.original_observation,
            corroboration.original_binding,
            corroboration.fresh_observation,
            corroboration.fresh_binding,
            derived_x,
            derived_y,
            visual_verification,
            human_goal,
        )
    except Exception:
        return unknown(
            "dual_evidence_production_unavailable"
        )

    if not bool(
        getattr(
            production_result,
            "issued",
            False,
        )
    ):
        return unknown(
            "dual_evidence_production_unavailable"
        )

    production = getattr(
        production_result,
        "production",
        None,
    )

    if (
        production is None
        or getattr(
            production,
            "visual_verification",
            None,
        )
        is not visual_verification
    ):
        return unknown(
            "dual_evidence_production_unavailable"
        )

    # -----------------------------------------------------
    # OPTIONAL B8G RESERVATION
    # -----------------------------------------------------
    #
    # Trusted pointer actions consume B8G here exactly as before.
    #
    # Trusted focused typing deliberately stops after B8J.
    # Only that non-consuming path requires the exact B7
    # StructuredUITargetRevalidationResult object carried by
    # the real B8J production graph.
    #
    # Pointer-mode test doubles are therefore not required to
    # manufacture semantic provenance they never previously
    # needed.
    # -----------------------------------------------------

    if not consume_evidence:

        try:
            semantic_result = (
                production
                .orchestration_result
                .revalidation_result
            )
        except Exception:
            semantic_result = None

        if semantic_result is None:
            return unknown(
                "dual_evidence_production_unavailable"
            )

        return RuntimeDualSensorVisionVerificationResult(
            status=VERIFICATION_STATUS_MATCHED,
            fresh_observation_id=fresh_observation_id,
            vision_x=derived_x,
            vision_y=derived_y,
            visual_verification=visual_verification,
            semantic_result=semantic_result,
            evidence_consumed=False,
        )

    # -----------------------------------------------------
    # B8G — CLAIM CARRIER + EXACT OBJECT IDENTITY
    # -----------------------------------------------------

    try:
        consumption_result = consume_fn(
            visual_verification,
            human_goal=human_goal,
            observation_id=fresh_observation_id,
            x=derived_x,
            y=derived_y,
        )
    except Exception:
        return unknown(
            "dual_evidence_consumption_unavailable"
        )

    if not bool(
        getattr(
            consumption_result,
            "matched",
            False,
        )
    ):
        return unknown(
            "dual_evidence_consumption_unavailable"
        )

    consumption = getattr(
        consumption_result,
        "consumption",
        None,
    )

    if (
        consumption is None
        or getattr(
            consumption,
            "visual_verification",
            None,
        )
        is not visual_verification
    ):
        return unknown(
            "dual_evidence_consumption_unavailable"
        )

    return RuntimeDualSensorVisionVerificationResult(
        status=VERIFICATION_STATUS_MATCHED,
        fresh_observation_id=fresh_observation_id,
        vision_x=derived_x,
        vision_y=derived_y,
        visual_verification=visual_verification,
        evidence_consumed=True,
    )

# =========================================================
# TRUSTED FOCUSED-TEXT TARGET VERIFICATION
# =========================================================

def verify_runtime_focused_text_target(
    *,
    intent,
    original_observation_id,
    human_goal,
    gui_target_verifier,
    refresh_fn=None,
    derive_fn=None,
    visual_verify_fn=None,
    produce_fn=None,
):
    """Resolve and visually verify a focused-text semantic target.

    Unlike pointer admission, this lane accepts NO model-proposed x/y
    coordinates.

    The executable point is derived exclusively from structured UI
    continuity across O0 -> O1, visually verified exactly once, and
    published through B8J.

    B8G is deliberately NOT consumed here. FocusedTextReceiptProducer
    owns the one-and-only B8G consumption for trusted typing.
    """

    def unknown(
        code,
    ):
        return RuntimeDualSensorVisionVerificationResult(
            status=VERIFICATION_STATUS_UNKNOWN,
            diagnostics=(code,),
            evidence_consumed=False,
        )

    if refresh_fn is None:
        refresh_fn = refresh_structured_ui_screen_context

    if derive_fn is None:
        derive_fn = derive_correlated_structured_ui_target_point

    if visual_verify_fn is None:
        visual_verify_fn = safe_verify_gui_target

    if produce_fn is None:
        produce_fn = produce_structured_ui_visual_target_evidence

    # -----------------------------------------------------
    # O0 -> O1 FRESH CORROBORATION
    # -----------------------------------------------------

    try:
        refresh_result = refresh_fn(
            original_observation_id
        )
    except Exception:
        return unknown(
            "fresh_context_unavailable"
        )

    if not bool(
        getattr(
            refresh_result,
            "available",
            False,
        )
    ):
        return unknown(
            "fresh_context_unavailable"
        )

    corroboration = getattr(
        refresh_result,
        "corroboration",
        None,
    )

    if corroboration is None:
        return unknown(
            "fresh_context_unavailable"
        )

    original_observation = getattr(
        corroboration,
        "original_observation",
        None,
    )

    fresh_observation = getattr(
        corroboration,
        "fresh_observation",
        None,
    )

    original_binding = getattr(
        corroboration,
        "original_binding",
        None,
    )

    fresh_binding = getattr(
        corroboration,
        "fresh_binding",
        None,
    )

    if (
        original_observation is None
        or fresh_observation is None
        or original_binding is None
        or fresh_binding is None
    ):
        return unknown(
            "fresh_context_unavailable"
        )

    original_id = getattr(
        original_observation,
        "observation_id",
        "",
    )

    fresh_id = getattr(
        fresh_observation,
        "observation_id",
        "",
    )

    if (
        type(original_observation_id) is not str
        or not original_observation_id.strip()
        or original_id
        != original_observation_id.strip()
        or type(fresh_id) is not str
        or not fresh_id.strip()
        or fresh_id == original_id
    ):
        return unknown(
            "fresh_context_unavailable"
        )

    # -----------------------------------------------------
    # SEMANTIC CONTINUITY -> TRUSTED EXECUTABLE POINT
    # -----------------------------------------------------

    try:
        point_derivation = derive_fn(
            intent,
            original_observation,
            original_binding,
            fresh_observation,
            fresh_binding,
        )
    except Exception:
        return unknown(
            "trusted_point_derivation_unavailable"
        )

    if not bool(
        getattr(
            point_derivation,
            "matched",
            False,
        )
    ):
        return unknown(
            "trusted_point_derivation_unavailable"
        )

    derived_screen_id = getattr(
        point_derivation,
        "screen_observation_id",
        "",
    )

    derived_point = getattr(
        point_derivation,
        "vision_point",
        None,
    )

    if (
        derived_screen_id != fresh_id
        or type(derived_point) is not tuple
        or len(derived_point) != 2
        or type(derived_point[0]) is not int
        or type(derived_point[1]) is not int
        or derived_point[0] < 0
        or derived_point[1] < 0
    ):
        return unknown(
            "trusted_point_derivation_unavailable"
        )

    derived_x, derived_y = (
        derived_point
    )

    # -----------------------------------------------------
    # EXACTLY ONE VISUAL VERIFICATION
    # -----------------------------------------------------

    try:
        visual_verification = visual_verify_fn(
            gui_target_verifier,
            goal=human_goal,
            observation_id=fresh_id,
            x=derived_x,
            y=derived_y,
        )
    except Exception:
        return unknown(
            "visual_verification_unavailable"
        )

    if not bool(
        getattr(
            visual_verification,
            "satisfied",
            False,
        )
    ):
        return unknown(
            "visual_verification_unavailable"
        )

    # -----------------------------------------------------
    # B8J — PUBLISH, BUT DO NOT CONSUME B8G
    # -----------------------------------------------------

    try:
        production_result = produce_fn(
            intent,
            original_observation,
            original_binding,
            fresh_observation,
            fresh_binding,
            derived_x,
            derived_y,
            visual_verification,
            human_goal,
        )
    except Exception:
        return unknown(
            "dual_evidence_production_unavailable"
        )

    if not bool(
        getattr(
            production_result,
            "issued",
            False,
        )
    ):
        return unknown(
            "dual_evidence_production_unavailable"
        )

    production = getattr(
        production_result,
        "production",
        None,
    )

    if (
        production is None
        or getattr(
            production,
            "visual_verification",
            None,
        )
        is not visual_verification
    ):
        return unknown(
            "dual_evidence_production_unavailable"
        )

    try:
        semantic_result = (
            production
            .orchestration_result
            .revalidation_result
        )
    except Exception:
        semantic_result = None

    if semantic_result is None:
        return unknown(
            "dual_evidence_production_unavailable"
        )

    return RuntimeDualSensorVisionVerificationResult(
        status=VERIFICATION_STATUS_MATCHED,
        fresh_observation_id=fresh_id,
        vision_x=derived_x,
        vision_y=derived_y,
        visual_verification=visual_verification,
        semantic_result=semantic_result,
        evidence_consumed=False,
    )
