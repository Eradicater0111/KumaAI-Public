"""B8D binding between trusted structured-UI evidence and one vision point.

This stage consumes an available B8C orchestration result, retrieves the exact
active trusted ScreenObservation named by its fresh screen provenance, maps one
model-proposed vision coordinate through KUMA's existing CoordinateMapper, and
checks whether the resulting native point lies inside the fresh AX rectangle.

The AX rectangle is accepted only when it is complete, positive-area, finite,
and wholly contained by the trusted primary native screen rectangle. This is a
conservative coordinate-space boundary: off-primary / partially off-screen AX
geometry is unsupported rather than guessed.

A matched point binding is evidence only. It grants no permission, target
attestation, ``semantic_target_verified`` state, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

from app.agent.gui_target_orchestration import (
    StructuredUITargetOrchestrationResult,
)
from app.vision.coordinates import CoordinateMapper, CoordinateMappingError
from app.vision.observation import (
    SCREEN_OBSERVATIONS,
    ScreenObservation,
    ScreenObservationError,
)


POINT_BINDING_STATUS_MATCHED = "matched"
POINT_BINDING_STATUS_MISMATCH = "mismatch"
POINT_BINDING_STATUS_UNKNOWN = "unknown"
VALID_POINT_BINDING_STATUSES = frozenset({
    POINT_BINDING_STATUS_MATCHED,
    POINT_BINDING_STATUS_MISMATCH,
    POINT_BINDING_STATUS_UNKNOWN,
})

MISMATCH_CODE = "candidate_outside_target"

UNKNOWN_CODES = frozenset({
    "clock_unavailable",
    "invalid_orchestration",
    "orchestration_unavailable",
    "evidence_not_current",
    "screen_observation_unavailable",
    "screen_observation_mismatch",
    "invalid_vision_point",
    "geometry_unavailable",
    "coordinate_space_unsupported",
    "coordinate_mapping_failed",
    "invalid_binding_contract",
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


def _native_target_rect(evidence, screen_observation):
    geometry = evidence.ax_geometry
    if (
        type(geometry) is not tuple
        or len(geometry) != 4
        or not all(_finite_number(value) for value in geometry)
    ):
        return None, "geometry_unavailable"

    left, top, width, height = geometry
    if width <= 0 or height <= 0:
        return None, "geometry_unavailable"

    right = left + width
    bottom = top + height
    if not all(_finite_number(value) for value in (right, bottom)):
        return None, "geometry_unavailable"

    # B8D supports only AX rectangles wholly inside the exact native rectangle
    # used by click_vision / CoordinateMapper. Geometry on another display or
    # partially outside that rectangle is unsupported rather than inferred.
    if not (
        0 <= left < right <= screen_observation.native_width
        and 0 <= top < bottom <= screen_observation.native_height
    ):
        return None, "coordinate_space_unsupported"

    return (left, top, right, bottom), None


def _point_inside(rect, x, y):
    left, top, right, bottom = rect
    return left <= x < right and top <= y < bottom


def _source_screen_capture_time(orchestration_result):
    fresh_resolution = (
        orchestration_result
        .revalidation_result
        .revalidation
        .fresh_resolution
    )
    return (
        fresh_resolution
        .binding
        .screen_provenance
        .binding
        .screen_captured_at
    )


@dataclass(frozen=True)
class StructuredUITargetPointBinding:
    """Exact read-only correspondence between B8C evidence and one vision point."""

    orchestration_result: StructuredUITargetOrchestrationResult = field(repr=False)
    screen_observation: ScreenObservation = field(repr=False)
    vision_x: int
    vision_y: int
    native_x: int
    native_y: int
    checked_at_monotonic: float
    expires_at_monotonic: float

    def __post_init__(self):
        if type(self.orchestration_result) is not StructuredUITargetOrchestrationResult:
            raise ValueError("Point binding requires an exact B8C orchestration result.")
        if not self.orchestration_result.available:
            raise ValueError("Point binding requires available B8C evidence.")
        if type(self.screen_observation) is not ScreenObservation:
            raise ValueError("Point binding requires an exact trusted screen observation.")

        evidence = self.orchestration_result.evidence
        if evidence is None:
            raise ValueError("Point binding requires exact B8C target evidence.")

        if not all(_timestamp(value) for value in (
            self.checked_at_monotonic,
            self.expires_at_monotonic,
        )):
            raise ValueError("Point binding times are invalid.")
        if not evidence.is_fresh(self.checked_at_monotonic):
            raise ValueError("Point binding requires current B8C evidence.")

        expected_expiry = min(
            evidence.expires_at_monotonic,
            self.screen_observation.captured_at_monotonic
            + SCREEN_OBSERVATIONS.max_age_seconds,
        )
        if (
            self.expires_at_monotonic != expected_expiry
            or not self.checked_at_monotonic < self.expires_at_monotonic
        ):
            raise ValueError("Point binding cannot outlive its trusted sources.")

        if (
            self.screen_observation.observation_id
            != evidence.screen_observation_id
            or self.screen_observation.captured_at_monotonic
            != _source_screen_capture_time(self.orchestration_result)
        ):
            raise ValueError("Screen observation does not match B8C screen provenance.")

        # Exact active-object identity prevents equal-value ScreenObservation
        # reconstruction from becoming trusted point evidence.
        try:
            active = SCREEN_OBSERVATIONS.peek(
                evidence.screen_observation_id,
                now=self.checked_at_monotonic,
            )
        except ScreenObservationError as error:
            raise ValueError("Trusted screen observation is no longer active.") from error
        if active is not self.screen_observation:
            raise ValueError("Point binding requires the exact active screen object.")

        if (
            type(self.vision_x) is not int
            or type(self.vision_y) is not int
            or type(self.native_x) is not int
            or type(self.native_y) is not int
        ):
            raise ValueError("Point binding coordinates must be exact integers.")
        if not (
            0 <= self.vision_x < self.screen_observation.vision_width
            and 0 <= self.vision_y < self.screen_observation.vision_height
        ):
            raise ValueError("Vision point is outside trusted observation geometry.")

        mapper = CoordinateMapper(
            vision_width=self.screen_observation.vision_width,
            vision_height=self.screen_observation.vision_height,
            screen_width=self.screen_observation.native_width,
            screen_height=self.screen_observation.native_height,
        )
        expected_native = mapper.vision_to_screen(self.vision_x, self.vision_y)
        if expected_native != (self.native_x, self.native_y):
            raise ValueError("Native point does not match trusted coordinate mapping.")

        rect, error = _native_target_rect(evidence, self.screen_observation)
        if error is not None or not _point_inside(rect, self.native_x, self.native_y):
            raise ValueError("Native point is not inside the trusted AX target rectangle.")

    @property
    def evidence(self):
        return self.orchestration_result.evidence

    @property
    def screen_observation_id(self):
        return self.screen_observation.observation_id

    @property
    def ui_observation_id(self):
        return self.evidence.ui_observation_id

    @property
    def vision_point(self):
        return self.vision_x, self.vision_y

    @property
    def native_point(self):
        return self.native_x, self.native_y

    @property
    def ax_geometry(self):
        return self.evidence.ax_geometry


@dataclass(frozen=True)
class StructuredUITargetPointBindingResult:
    status: str
    binding: StructuredUITargetPointBinding | None = field(default=None, repr=False)
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.status) is not str or self.status not in VALID_POINT_BINDING_STATUSES:
            raise ValueError("Invalid structured UI target point-binding status.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Point-binding diagnostics must be immutable and unique.")

        if self.status == POINT_BINDING_STATUS_MATCHED:
            if type(self.binding) is not StructuredUITargetPointBinding:
                raise ValueError("Matched point binding requires exact evidence.")
            if self.diagnostics:
                raise ValueError("Matched point binding has no local diagnostics.")
            return

        if self.binding is not None:
            raise ValueError("Non-matched point binding cannot carry trusted evidence.")

        if self.status == POINT_BINDING_STATUS_MISMATCH:
            if self.diagnostics != (MISMATCH_CODE,):
                raise ValueError("Point mismatch requires the canonical diagnostic.")
            return

        if len(self.diagnostics) != 1 or self.diagnostics[0] not in UNKNOWN_CODES:
            raise ValueError("Unknown point binding requires one structured diagnostic.")

    @property
    def matched(self):
        return (
            self.status == POINT_BINDING_STATUS_MATCHED
            and self.binding is not None
        )


def bind_structured_ui_target_point(
    orchestration_result,
    vision_x,
    vision_y,
    *,
    clock=time.monotonic,
):
    """Bind one vision point to exact fresh B8C evidence, fail closed.

    Screen dimensions and screen-observation identity are retrieved from KUMA's
    active trusted screen store. The existing CoordinateMapper is reused exactly
    so this stage cannot drift from click_vision rounding/clamping semantics.
    """

    if not callable(clock):
        raise TypeError("clock must be callable.")

    def unknown(code):
        return StructuredUITargetPointBindingResult(
            status=POINT_BINDING_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    def mismatch():
        return StructuredUITargetPointBindingResult(
            status=POINT_BINDING_STATUS_MISMATCH,
            diagnostics=(MISMATCH_CODE,),
        )

    try:
        now = clock()
    except Exception:
        return unknown("clock_unavailable")
    if not _timestamp(now):
        return unknown("clock_unavailable")

    if type(orchestration_result) is not StructuredUITargetOrchestrationResult:
        return unknown("invalid_orchestration")
    if not orchestration_result.available or orchestration_result.evidence is None:
        return unknown("orchestration_unavailable")

    evidence = orchestration_result.evidence
    if not evidence.is_fresh(now):
        return unknown("evidence_not_current")

    if (
        type(vision_x) is not int
        or type(vision_y) is not int
    ):
        return unknown("invalid_vision_point")

    try:
        screen_observation = SCREEN_OBSERVATIONS.peek(
            evidence.screen_observation_id,
            now=now,
        )
    except ScreenObservationError:
        return unknown("screen_observation_unavailable")

    try:
        source_capture_time = _source_screen_capture_time(orchestration_result)
    except Exception:
        return unknown("screen_observation_mismatch")
    if (
        screen_observation.observation_id != evidence.screen_observation_id
        or screen_observation.captured_at_monotonic != source_capture_time
    ):
        return unknown("screen_observation_mismatch")

    if not (
        0 <= vision_x < screen_observation.vision_width
        and 0 <= vision_y < screen_observation.vision_height
    ):
        return unknown("invalid_vision_point")

    rect, geometry_error = _native_target_rect(evidence, screen_observation)
    if geometry_error is not None:
        return unknown(geometry_error)

    try:
        mapper = CoordinateMapper(
            vision_width=screen_observation.vision_width,
            vision_height=screen_observation.vision_height,
            screen_width=screen_observation.native_width,
            screen_height=screen_observation.native_height,
        )
        native_x, native_y = mapper.vision_to_screen(vision_x, vision_y)
    except CoordinateMappingError:
        return unknown("coordinate_mapping_failed")

    if not _point_inside(rect, native_x, native_y):
        return mismatch()

    expiry = min(
        evidence.expires_at_monotonic,
        screen_observation.captured_at_monotonic
        + SCREEN_OBSERVATIONS.max_age_seconds,
    )

    try:
        binding = StructuredUITargetPointBinding(
            orchestration_result=orchestration_result,
            screen_observation=screen_observation,
            vision_x=vision_x,
            vision_y=vision_y,
            native_x=native_x,
            native_y=native_y,
            checked_at_monotonic=now,
            expires_at_monotonic=expiry,
        )
    except Exception:
        return unknown("invalid_binding_contract")

    return StructuredUITargetPointBindingResult(
        status=POINT_BINDING_STATUS_MATCHED,
        binding=binding,
    )
