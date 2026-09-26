"""B8K4 trusted executable point derivation from fresh structured UI evidence.

This stage accepts one exact available B8C orchestration result and derives a
deterministic vision-space point from the trusted fresh AX rectangle.

The model does not supply the derived point.

Derivation uses KUMA's existing CoordinateMapper lattice. For each axis, only
vision coordinates whose exact ``vision_to_screen`` mapping lies inside the
half-open trusted AX rectangle are eligible. Among those representable points,
the native coordinate nearest the AX rectangle center is selected. Ties select
the lower vision coordinate deterministically.

The resulting two-dimensional point is then passed through B8D itself. B8D
therefore remains the canonical proof that the derived vision point maps to an
exact native point inside the fresh AX target rectangle.

If the AX rectangle contains no point representable by the trusted vision
coordinate lattice, derivation fails closed rather than inventing or clipping a
coordinate.

This module is evidence derivation only. It grants no permission, GUI argument
authority, semantic attestation, semantic_target_verified state, or execution
authority and performs no physical action or visual-model verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

from app.agent.gui_target_orchestration import (
    ORCHESTRATION_STATUS_AVAILABLE,
    StructuredUITargetOrchestrationResult,
    orchestrate_structured_ui_target_evidence,
)
from app.agent.gui_target_point_binding import (
    POINT_BINDING_STATUS_MATCHED,
    StructuredUITargetPointBindingResult,
    bind_structured_ui_target_point,
)
from app.vision.coordinates import (
    CoordinateMapper,
    CoordinateMappingError,
)
from app.vision.observation import (
    SCREEN_OBSERVATIONS,
    ScreenObservation,
    ScreenObservationError,
)


DERIVATION_STATUS_MATCHED = "matched"
DERIVATION_STATUS_UNKNOWN = "unknown"

VALID_DERIVATION_STATUSES = frozenset({
    DERIVATION_STATUS_MATCHED,
    DERIVATION_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "clock_unavailable",
    "invalid_orchestration",
    "orchestration_unavailable",
    "evidence_not_current",
    "screen_observation_unavailable",
    "geometry_unavailable",
    "coordinate_space_unsupported",
    "coordinate_mapping_failed",
    "no_representable_point",
    "point_binding_unavailable",
    "invalid_derivation_contract",
})


def _timestamp(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _finite_number(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
    )


def _native_target_rect(
    evidence,
    screen_observation,
):
    """Conservative prefilter matching B8D's native-space contract.

    This is not the final point authority. B8D revalidates the resulting point
    independently before any matched derivation can be returned.
    """

    geometry = evidence.ax_geometry

    if (
        type(geometry) is not tuple
        or len(geometry) != 4
        or not all(
            _finite_number(value)
            for value in geometry
        )
    ):
        return None, "geometry_unavailable"

    left, top, width, height = geometry

    if width <= 0 or height <= 0:
        return None, "geometry_unavailable"

    right = left + width
    bottom = top + height

    if not all(
        _finite_number(value)
        for value in (
            right,
            bottom,
        )
    ):
        return None, "geometry_unavailable"

    if not (
        0 <= left < right
        <= screen_observation.native_width
        and
        0 <= top < bottom
        <= screen_observation.native_height
    ):
        return None, "coordinate_space_unsupported"

    return (
        left,
        top,
        right,
        bottom,
    ), None


def _nearest_representable_axis_point(
    mapper,
    *,
    axis,
    vision_limit,
    native_low,
    native_high,
):
    """Return deterministic nearest-center vision/native coordinate pair."""

    center = (
        native_low
        + native_high
    ) / 2.0

    best = None

    for vision_coordinate in range(
        vision_limit
    ):
        if axis == "x":
            native_coordinate = (
                mapper.vision_to_screen(
                    vision_coordinate,
                    0,
                )[0]
            )
        else:
            native_coordinate = (
                mapper.vision_to_screen(
                    0,
                    vision_coordinate,
                )[1]
            )

        if not (
            native_low
            <= native_coordinate
            < native_high
        ):
            continue

        candidate_key = (
            abs(
                native_coordinate
                - center
            ),
            vision_coordinate,
        )

        if (
            best is None
            or candidate_key < best[0]
        ):
            best = (
                candidate_key,
                vision_coordinate,
                native_coordinate,
            )

    if best is None:
        return None

    return (
        best[1],
        best[2],
    )


@dataclass(frozen=True)
class StructuredUITargetPointDerivation:
    """Exact non-authorizing receipt for one trusted derived target point."""

    orchestration_result: StructuredUITargetOrchestrationResult = field(
        repr=False,
    )

    screen_observation: ScreenObservation = field(
        repr=False,
    )

    point_binding_result: StructuredUITargetPointBindingResult = field(
        repr=False,
    )

    def __post_init__(self):
        if (
            type(self.orchestration_result)
            is not StructuredUITargetOrchestrationResult
            or self.orchestration_result.status
            != ORCHESTRATION_STATUS_AVAILABLE
            or not self.orchestration_result.available
        ):
            raise ValueError(
                "Point derivation requires exact available "
                "B8C orchestration evidence."
            )

        if (
            type(self.screen_observation)
            is not ScreenObservation
        ):
            raise ValueError(
                "Point derivation requires an exact trusted "
                "screen observation."
            )

        if (
            type(self.point_binding_result)
            is not StructuredUITargetPointBindingResult
            or self.point_binding_result.status
            != POINT_BINDING_STATUS_MATCHED
            or not self.point_binding_result.matched
        ):
            raise ValueError(
                "Point derivation requires an exact matched "
                "B8D point binding."
            )

        binding = (
            self.point_binding_result.binding
        )

        if (
            binding.orchestration_result
            is not self.orchestration_result
            or binding.screen_observation
            is not self.screen_observation
        ):
            raise ValueError(
                "Point derivation requires one exact B8C/B8D "
                "trusted object graph."
            )

        try:
            active = SCREEN_OBSERVATIONS.peek(
                binding.screen_observation_id,
                now=binding.checked_at_monotonic,
            )
        except ScreenObservationError as error:
            raise ValueError(
                "Derived point screen observation is no longer active."
            ) from error

        if active is not self.screen_observation:
            raise ValueError(
                "Point derivation requires the exact active screen object."
            )

    @property
    def evidence(self):
        return (
            self.orchestration_result.evidence
        )

    @property
    def binding(self):
        return (
            self.point_binding_result.binding
        )

    @property
    def screen_observation_id(self):
        return (
            self.binding.screen_observation_id
        )

    @property
    def ui_observation_id(self):
        return (
            self.binding.ui_observation_id
        )

    @property
    def vision_point(self):
        return (
            self.binding.vision_point
        )

    @property
    def native_point(self):
        return (
            self.binding.native_point
        )

    @property
    def ax_geometry(self):
        return (
            self.binding.ax_geometry
        )

    @property
    def checked_at_monotonic(self):
        return (
            self.binding.checked_at_monotonic
        )

    @property
    def expires_at_monotonic(self):
        return (
            self.binding.expires_at_monotonic
        )


@dataclass(frozen=True)
class StructuredUITargetPointDerivationResult:
    status: str

    derivation: StructuredUITargetPointDerivation | None = field(
        default=None,
        repr=False,
    )

    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            type(self.status) is not str
            or self.status
            not in VALID_DERIVATION_STATUSES
        ):
            raise ValueError(
                "Invalid structured target point derivation status."
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
                "Point derivation diagnostics must be immutable "
                "and unique."
            )

        if self.status == DERIVATION_STATUS_MATCHED:
            if (
                type(self.derivation)
                is not StructuredUITargetPointDerivation
            ):
                raise ValueError(
                    "Matched point derivation requires exact evidence."
                )

            if self.diagnostics:
                raise ValueError(
                    "Matched point derivation has no local diagnostics."
                )

            return

        if self.derivation is not None:
            raise ValueError(
                "Unknown point derivation cannot carry trusted evidence."
            )

        if (
            len(self.diagnostics) != 1
            or self.diagnostics[0]
            not in UNKNOWN_CODES
        ):
            raise ValueError(
                "Unknown point derivation requires one "
                "structured diagnostic."
            )

    @property
    def matched(self):
        return (
            self.status
            == DERIVATION_STATUS_MATCHED
            and self.derivation is not None
        )

    @property
    def screen_observation_id(self):
        if not self.matched:
            return ""

        return (
            self.derivation.screen_observation_id
        )

    @property
    def vision_point(self):
        if not self.matched:
            return None

        return (
            self.derivation.vision_point
        )

    @property
    def native_point(self):
        if not self.matched:
            return None

        return (
            self.derivation.native_point
        )


def derive_structured_ui_target_point(
    orchestration_result,
    *,
    clock=time.monotonic,
):
    """Derive one exact representable vision point from fresh B8C AX evidence."""

    if not callable(clock):
        raise TypeError(
            "clock must be callable."
        )

    def unknown(code):
        return StructuredUITargetPointDerivationResult(
            status=DERIVATION_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    try:
        now = clock()
    except Exception:
        return unknown(
            "clock_unavailable"
        )

    if not _timestamp(now):
        return unknown(
            "clock_unavailable"
        )

    if (
        type(orchestration_result)
        is not StructuredUITargetOrchestrationResult
    ):
        return unknown(
            "invalid_orchestration"
        )

    if (
        orchestration_result.status
        != ORCHESTRATION_STATUS_AVAILABLE
        or not orchestration_result.available
        or orchestration_result.evidence is None
    ):
        return unknown(
            "orchestration_unavailable"
        )

    evidence = (
        orchestration_result.evidence
    )

    if not evidence.is_fresh(now):
        return unknown(
            "evidence_not_current"
        )

    try:
        screen_observation = (
            SCREEN_OBSERVATIONS.peek(
                evidence.screen_observation_id,
                now=now,
            )
        )
    except ScreenObservationError:
        return unknown(
            "screen_observation_unavailable"
        )

    rect, geometry_error = (
        _native_target_rect(
            evidence,
            screen_observation,
        )
    )

    if geometry_error is not None:
        return unknown(
            geometry_error
        )

    left, top, right, bottom = rect

    try:
        mapper = CoordinateMapper(
            vision_width=(
                screen_observation.vision_width
            ),
            vision_height=(
                screen_observation.vision_height
            ),
            screen_width=(
                screen_observation.native_width
            ),
            screen_height=(
                screen_observation.native_height
            ),
        )

        x_point = (
            _nearest_representable_axis_point(
                mapper,
                axis="x",
                vision_limit=(
                    screen_observation.vision_width
                ),
                native_low=left,
                native_high=right,
            )
        )

        y_point = (
            _nearest_representable_axis_point(
                mapper,
                axis="y",
                vision_limit=(
                    screen_observation.vision_height
                ),
                native_low=top,
                native_high=bottom,
            )
        )

    except (
        CoordinateMappingError,
        ZeroDivisionError,
        OverflowError,
        ValueError,
    ):
        return unknown(
            "coordinate_mapping_failed"
        )

    if (
        x_point is None
        or y_point is None
    ):
        return unknown(
            "no_representable_point"
        )

    vision_x, _derived_native_x = (
        x_point
    )

    vision_y, _derived_native_y = (
        y_point
    )

    # -----------------------------------------------------
    # B8D REMAINS THE FINAL CANONICAL POINT PROOF
    # -----------------------------------------------------

    try:
        point_binding_result = (
            bind_structured_ui_target_point(
                orchestration_result,
                vision_x,
                vision_y,
                clock=lambda: now,
            )
        )
    except Exception:
        return unknown(
            "point_binding_unavailable"
        )

    if (
        type(point_binding_result)
        is not StructuredUITargetPointBindingResult
        or point_binding_result.status
        != POINT_BINDING_STATUS_MATCHED
        or not point_binding_result.matched
    ):
        return unknown(
            "point_binding_unavailable"
        )

    binding = (
        point_binding_result.binding
    )

    # The mapper result selected above must be exactly the same
    # native point independently recomputed and trusted by B8D.
    if binding.native_point != (
        _derived_native_x,
        _derived_native_y,
    ):
        return unknown(
            "point_binding_unavailable"
        )

    try:
        derivation = (
            StructuredUITargetPointDerivation(
                orchestration_result=(
                    orchestration_result
                ),
                screen_observation=(
                    screen_observation
                ),
                point_binding_result=(
                    point_binding_result
                ),
            )
        )
    except Exception:
        return unknown(
            "invalid_derivation_contract"
        )

    return StructuredUITargetPointDerivationResult(
        status=DERIVATION_STATUS_MATCHED,
        derivation=derivation,
    )

def derive_correlated_structured_ui_target_point(
    intent,
    original_observation,
    original_binding,
    fresh_observation,
    fresh_binding,
    *,
    clock=time.monotonic,
):
    """Build fresh B8C evidence and derive its trusted executable point.

    This is a read-only composition boundary. It performs no visual
    verification, authorization, permission check, attestation, or action.
    """

    if not callable(clock):
        raise TypeError(
            "clock must be callable."
        )

    try:
        orchestration_result = (
            orchestrate_structured_ui_target_evidence(
                intent,
                original_observation,
                original_binding,
                fresh_observation,
                fresh_binding,
                clock=clock,
            )
        )
    except Exception:
        return StructuredUITargetPointDerivationResult(
            status=DERIVATION_STATUS_UNKNOWN,
            diagnostics=(
                "orchestration_unavailable",
            ),
        )

    return derive_structured_ui_target_point(
        orchestration_result,
        clock=clock,
    )
