"""Exact process-local provenance joining KUMA's semantic target and focus evidence.

8D2E composes three independent evidence roots:

1. one exact matched StructuredUITargetRevalidationResult,
2. one exact active FocusDesktopProvenance,
3. one fresh parent-accepted MATCHED FocusTargetCorrelationResult.

The 8D2 correlation proves only that a fresh independently resolved semantic
selector referred to the native focused AX element inside its isolated worker.

This module deliberately does NOT claim that the 8D1 native focused AX object
and the 8D2 native focused AX object were compared across processes.

No native AX reference is retained here. No permission, keyboard authority,
typing authority, model decision, AX action, or physical execution is granted.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
)
import math
import threading
import time

from app.ui_observation.focus_provenance import (
    FOCUS_DESKTOP_PROVENANCE,
    FocusDesktopProvenance,
)
from app.ui_observation.focus_target_correlation import (
    CORRELATION_STATUS_MATCHED,
    FocusTargetCorrelationResult,
)
from app.ui_observation.target_revalidation import (
    CONTINUITY_STATUS_MATCHED,
    StructuredUITargetRevalidationResult,
)


FOCUS_TARGET_CORRELATION_MAX_AGE_SECONDS = 5.0


def _timestamp(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _same_application(
    semantic,
    focus,
    correlation,
):
    application = correlation.expected_application

    return (
        semantic.application_pid
        == focus.application_pid
        == application.pid
        and semantic.application_bundle_id
        == focus.application_bundle_id
        == application.bundle_id
    )


def _expected_expiry(
    semantic_result,
    focus_provenance,
    correlation,
):
    semantic = semantic_result.revalidation

    return min(
        semantic.expires_at_monotonic,
        focus_provenance.binding.expires_at_monotonic,
        correlation.captured_at_monotonic
        + FOCUS_TARGET_CORRELATION_MAX_AGE_SECONDS,
    )


@dataclass(frozen=True)
class FocusTargetProvenance:
    """Exact parent-side evidence graph for one focused semantic target.

    correlation.selector crosses JSON and is therefore compared with the
    semantic selector by value, not by Python object identity.

    Snapshot-local AX paths are deliberately not compared across evidence
    roots and no cross-process native-object identity is claimed.
    """

    semantic_result: StructuredUITargetRevalidationResult = field(
        repr=False
    )

    focus_provenance: FocusDesktopProvenance = field(
        repr=False
    )

    correlation: FocusTargetCorrelationResult = field(
        repr=False
    )

    issued_at_monotonic: float

    expires_at_monotonic: float

    def __post_init__(self):
        if (
            type(self.semantic_result)
            is not StructuredUITargetRevalidationResult
        ):
            raise ValueError(
                "Exact semantic revalidation result is required."
            )

        if (
            type(self.focus_provenance)
            is not FocusDesktopProvenance
        ):
            raise ValueError(
                "Exact active focus provenance is required."
            )

        if (
            type(self.correlation)
            is not FocusTargetCorrelationResult
        ):
            raise ValueError(
                "Exact focus-target correlation is required."
            )

        semantic_result = self.semantic_result
        semantic = semantic_result.revalidation
        focus = self.focus_provenance
        correlation = self.correlation

        if (
            semantic_result.status
            != CONTINUITY_STATUS_MATCHED
            or not semantic_result.revalidated
            or semantic is None
            or semantic_result.fresh_resolution is None
            or (
                semantic_result
                .fresh_resolution
                .resolution
                is not semantic.fresh_resolution
            )
        ):
            raise ValueError(
                "Semantic target provenance must be "
                "one exact matched revalidation graph."
            )

        if (
            correlation.status
            != CORRELATION_STATUS_MATCHED
            or not correlation.matched
            or correlation.candidate is None
            or correlation.candidate_count != 1
        ):
            raise ValueError(
                "Focus-target provenance requires "
                "one matched native correlation."
            )

        if not (
            _timestamp(self.issued_at_monotonic)
            and _timestamp(self.expires_at_monotonic)
        ):
            raise ValueError(
                "Focus-target provenance times are invalid."
            )

        if not (
            self.issued_at_monotonic
            < self.expires_at_monotonic
        ):
            raise ValueError(
                "Focus-target provenance is already expired."
            )

        if not _same_application(
            semantic,
            focus,
            correlation,
        ):
            raise ValueError(
                "Semantic, focus, and correlation "
                "application identity do not agree."
            )

        if (
            correlation.selector
            != semantic.selector
        ):
            raise ValueError(
                "Correlation belongs to a different "
                "semantic selector."
            )

        if (
            correlation.captured_at_monotonic
            < semantic.revalidated_at_monotonic
        ):
            raise ValueError(
                "Correlation predates semantic revalidation."
            )

        if (
            correlation.captured_at_monotonic
            < focus.binding.bound_at_monotonic
        ):
            raise ValueError(
                "Correlation predates trusted focus binding."
            )

        if (
            correlation.captured_at_monotonic
            > self.issued_at_monotonic
        ):
            raise ValueError(
                "Correlation cannot come from the future."
            )

        if not semantic.is_fresh(
            self.issued_at_monotonic
        ):
            raise ValueError(
                "Semantic target evidence is not current "
                "at provenance issuance."
            )

        if not focus.is_fresh(
            self.issued_at_monotonic
        ):
            raise ValueError(
                "Focus provenance is not current "
                "at provenance issuance."
            )

        if not (
            correlation.captured_at_monotonic
            <= self.issued_at_monotonic
            < (
                correlation.captured_at_monotonic
                + FOCUS_TARGET_CORRELATION_MAX_AGE_SECONDS
            )
        ):
            raise ValueError(
                "Native correlation is not current "
                "at provenance issuance."
            )

        expected_expiry = _expected_expiry(
            semantic_result,
            focus,
            correlation,
        )

        if (
            self.expires_at_monotonic
            != expected_expiry
        ):
            raise ValueError(
                "Focus-target provenance lifetime does not "
                "match its shortest trusted source."
            )

        if not (
            self.issued_at_monotonic
            < expected_expiry
        ):
            raise ValueError(
                "Trusted source evidence expired "
                "before provenance issuance."
            )

    @property
    def semantic_target(self):
        return self.semantic_result.revalidation

    @property
    def selector(self):
        return self.semantic_target.selector

    @property
    def application_pid(self):
        return self.semantic_target.application_pid

    @property
    def application_bundle_id(self):
        return self.semantic_target.application_bundle_id

    @property
    def focus_observation_id(self):
        return self.focus_provenance.focus_observation_id

    def is_fresh(self, now):
        if not _timestamp(now):
            return False

        semantic = self.semantic_target
        focus = self.focus_provenance
        correlation = self.correlation

        return (
            self.issued_at_monotonic
            <= now
            < self.expires_at_monotonic
            and semantic.is_fresh(now)
            and focus.is_fresh(now)
            and (
                correlation.captured_at_monotonic
                <= now
                < (
                    correlation.captured_at_monotonic
                    + FOCUS_TARGET_CORRELATION_MAX_AGE_SECONDS
                )
            )
        )


def compose_focus_target_provenance(
    semantic_result,
    focus_provenance,
    correlation,
    *,
    clock=time.monotonic,
):
    """Compose three already-produced evidence roots without effects."""

    if not callable(clock):
        raise TypeError(
            "clock must be callable."
        )

    try:
        now = clock()
    except Exception:
        raise ValueError(
            "Focus-target provenance clock is unavailable."
        ) from None

    if not _timestamp(now):
        raise ValueError(
            "Focus-target provenance clock is unavailable."
        )

    if (
        type(semantic_result)
        is not StructuredUITargetRevalidationResult
        or type(focus_provenance)
        is not FocusDesktopProvenance
        or type(correlation)
        is not FocusTargetCorrelationResult
    ):
        raise ValueError(
            "Exact focus-target provenance sources are required."
        )

    expires = _expected_expiry(
        semantic_result,
        focus_provenance,
        correlation,
    )

    return FocusTargetProvenance(
        semantic_result=semantic_result,
        focus_provenance=focus_provenance,
        correlation=correlation,
        issued_at_monotonic=now,
        expires_at_monotonic=expires,
    )


class FocusTargetProvenanceError(
    RuntimeError
):
    """Raised when active 8D2E provenance cannot be trusted."""


class FocusTargetProvenanceStore:
    """Hold exactly one active focus-target provenance graph.

    There is deliberately no latest lookup and no ID-only fallback.

    Retrieval requires the exact FocusTargetProvenance object that was
    published. Equal-value reconstruction cannot substitute for it.

    Active validity also requires the embedded FocusDesktopProvenance to
    remain the exact currently-active 8D1 provenance object.
    """

    def __init__(
        self,
        *,
        focus_lookup=None,
        clock=time.monotonic,
    ):
        if (
            focus_lookup is not None
            and not callable(focus_lookup)
        ):
            raise TypeError(
                "focus_lookup must be callable."
            )

        if not callable(clock):
            raise TypeError(
                "clock must be callable."
            )

        self._focus_lookup = (
            (
                lambda observation_id:
                FOCUS_DESKTOP_PROVENANCE.get(
                    observation_id
                )
            )
            if focus_lookup is None
            else focus_lookup
        )

        self._clock = clock
        self._active = None
        self._lock = threading.Lock()
        self._last_now = None

    def _clear_active(self):
        self._active = None

    def _now(self):
        try:
            now = self._clock()
        except Exception:
            self._clear_active()
            raise FocusTargetProvenanceError(
                "Focus-target provenance clock "
                "is unavailable."
            ) from None

        if not _timestamp(now):
            self._clear_active()
            raise FocusTargetProvenanceError(
                "Focus-target provenance clock "
                "is unavailable."
            )

        if (
            self._last_now is not None
            and now < self._last_now
        ):
            self._clear_active()
            raise FocusTargetProvenanceError(
                "Focus-target provenance clock "
                "moved backward."
            )

        self._last_now = now
        return now

    def _sources_are_current(
        self,
        provenance,
        now,
    ):
        if not provenance.is_fresh(now):
            return False

        try:
            active_focus = self._focus_lookup(
                provenance.focus_observation_id
            )
        except Exception:
            return False

        return (
            active_focus
            is provenance.focus_provenance
        )

    def publish(self, provenance):
        if (
            type(provenance)
            is not FocusTargetProvenance
        ):
            raise TypeError(
                "Expected FocusTargetProvenance."
            )

        with self._lock:
            now = self._now()

            if not self._sources_are_current(
                provenance,
                now,
            ):
                self._clear_active()
                return False

            self._active = provenance
            return True

    def get(self, provenance):
        if (
            type(provenance)
            is not FocusTargetProvenance
        ):
            raise TypeError(
                "Expected FocusTargetProvenance."
            )

        with self._lock:
            now = self._now()
            active = self._active

            if (
                active is None
                or active is not provenance
            ):
                return None

            if not self._sources_are_current(
                active,
                now,
            ):
                self._clear_active()
                return None

            return active

    def clear(self):
        with self._lock:
            self._clear_active()

    def __len__(self):
        with self._lock:
            return (
                1
                if self._active is not None
                else 0
            )


FOCUS_TARGET_PROVENANCE = (
    FocusTargetProvenanceStore()
)
