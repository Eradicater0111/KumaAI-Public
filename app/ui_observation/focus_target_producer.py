"""Trusted parent-side producer for KUMA 8D2 focus-target provenance.

The caller supplies semantic revalidation evidence and the exact 8D1 focus
observation ID only.

The caller never supplies native focus-target correlation evidence.

This producer itself:
1. recovers the exact active 8D1 FocusDesktopProvenance,
2. runs the isolated native focus-target correlation,
3. requires a MATCHED correlation,
4. composes exact FocusTargetProvenance,
5. publishes that exact parent-side provenance graph.

Every new attempt invalidates prior 8D2E publication before doing work.

This remains evidence production only. It grants no permission, keyboard
authority, typing authority, AX action, or physical execution.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
)
import math
import threading
import time

from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation.focus_provenance import (
    FOCUS_DESKTOP_PROVENANCE,
    FocusDesktopProvenance,
    FocusDesktopProvenanceStore,
)
from app.ui_observation.focus_target_correlation import (
    CORRELATION_STATUS_AMBIGUOUS,
    CORRELATION_STATUS_MATCHED,
    CORRELATION_STATUS_MISMATCHED,
    CORRELATION_STATUS_UNKNOWN,
    FocusTargetCorrelationResult,
)
from app.ui_observation.focus_target_provenance import (
    FOCUS_TARGET_PROVENANCE,
    FocusTargetProvenance,
    FocusTargetProvenanceStore,
    compose_focus_target_provenance,
)
from app.ui_observation.focus_target_runtime import (
    collect_focus_target_correlation_isolated,
)
from app.ui_observation.target_revalidation import (
    CONTINUITY_STATUS_MATCHED,
    StructuredUITargetRevalidationResult,
)


PRODUCTION_STATUS_MATCHED = "matched"
PRODUCTION_STATUS_UNKNOWN = "unknown"

VALID_PRODUCTION_STATUSES = frozenset({
    PRODUCTION_STATUS_MATCHED,
    PRODUCTION_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "invalid_semantic_result",
    "semantic_target_not_revalidated",
    "semantic_target_expired",
    "focus_provenance_unavailable",
    "focus_application_mismatch",
    "correlation_unknown",
    "correlation_ambiguous",
    "correlation_mismatch",
    "correlation_invalid",
    "composition_failed",
    "publication_failed",
    "clock_unavailable",
    "production_busy",
})


def _timestamp(
    value,
):
    return (
        type(value)
        in (
            int,
            float,
        )
        and math.isfinite(
            value
        )
        and value >= 0
    )


@dataclass(frozen=True)
class FocusTargetProvenanceProduction:
    """Exact non-authorizing result of one trusted 8D2E production attempt."""

    status: str

    provenance: (
        FocusTargetProvenance
        | None
    ) = field(
        default=None,
        repr=False,
    )

    correlation: (
        FocusTargetCorrelationResult
        | None
    ) = field(
        default=None,
        repr=False,
    )

    diagnostics: tuple[str, ...] = ()

    def __post_init__(
        self,
    ):
        if (
            type(self.status)
            is not str
            or self.status
            not in VALID_PRODUCTION_STATUSES
        ):
            raise ValueError(
                "Invalid focus-target production status."
            )

        if (
            type(self.diagnostics)
            is not tuple
            or any(
                type(code)
                is not str
                for code
                in self.diagnostics
            )
            or len(
                set(
                    self.diagnostics
                )
            )
            != len(
                self.diagnostics
            )
        ):
            raise ValueError(
                "Production diagnostics must be immutable and unique."
            )

        if (
            self.status
            == PRODUCTION_STATUS_MATCHED
        ):
            if (
                type(self.provenance)
                is not FocusTargetProvenance
                or type(self.correlation)
                is not FocusTargetCorrelationResult
                or self.correlation.status
                != CORRELATION_STATUS_MATCHED
                or not self.correlation.matched
                or self.provenance.correlation
                is not self.correlation
                or self.diagnostics
            ):
                raise ValueError(
                    "Matched production requires its exact "
                    "published provenance and correlation."
                )

            return

        if (
            self.provenance is not None
            or self.correlation is not None
        ):
            raise ValueError(
                "Unknown production cannot carry trusted evidence."
            )

        if (
            len(
                self.diagnostics
            )
            != 1
            or self.diagnostics[
                0
            ]
            not in UNKNOWN_CODES
        ):
            raise ValueError(
                "Unknown production requires one "
                "structured diagnostic."
            )

    @property
    def produced(
        self,
    ):
        return (
            self.status
            == PRODUCTION_STATUS_MATCHED
            and self.provenance
            is not None
        )


class FocusTargetProvenanceProducer:
    """Serialize trusted production of one active 8D2E provenance graph."""

    def __init__(
        self,
        *,
        focus_store=FOCUS_DESKTOP_PROVENANCE,
        provenance_store=FOCUS_TARGET_PROVENANCE,
        correlation_runtime=(
            collect_focus_target_correlation_isolated
        ),
        clock=time.monotonic,
    ):
        if (
            type(focus_store)
            is not FocusDesktopProvenanceStore
        ):
            raise TypeError(
                "focus_store must be an exact "
                "FocusDesktopProvenanceStore."
            )

        if (
            type(provenance_store)
            is not FocusTargetProvenanceStore
        ):
            raise TypeError(
                "provenance_store must be an exact "
                "FocusTargetProvenanceStore."
            )

        if not callable(
            correlation_runtime
        ):
            raise TypeError(
                "correlation_runtime must be callable."
            )

        if not callable(
            clock
        ):
            raise TypeError(
                "clock must be callable."
            )

        self._focus_store = (
            focus_store
        )

        self._provenance_store = (
            provenance_store
        )

        self._correlation_runtime = (
            correlation_runtime
        )

        self._clock = clock

        self._lock = (
            threading.Lock()
        )

        self._last_now = None

    def _now(
        self,
    ):
        try:
            now = (
                self._clock()
            )
        except Exception:
            return None

        if not _timestamp(
            now
        ):
            return None

        if (
            self._last_now is not None
            and now
            < self._last_now
        ):
            return None

        self._last_now = now

        return now

    @staticmethod
    def _unknown(
        code,
    ):
        return FocusTargetProvenanceProduction(
            status=(
                PRODUCTION_STATUS_UNKNOWN
            ),
            diagnostics=(
                code,
            ),
        )

    def produce(
        self,
        semantic_result,
        focus_observation_id,
        *,
        correlation_timeout_seconds=3.0,
    ):
        """Produce fresh trusted focus-target provenance.

        Prior publication is cleared before every attempt.
        """

        if not self._lock.acquire(
            blocking=False
        ):
            return self._unknown(
                "production_busy"
            )

        try:
            self._provenance_store.clear()

            started = (
                self._now()
            )

            if started is None:
                return self._unknown(
                    "clock_unavailable"
                )

            if (
                type(semantic_result)
                is not StructuredUITargetRevalidationResult
            ):
                return self._unknown(
                    "invalid_semantic_result"
                )

            if (
                semantic_result.status
                != CONTINUITY_STATUS_MATCHED
                or not semantic_result.revalidated
                or semantic_result.revalidation
                is None
            ):
                return self._unknown(
                    "semantic_target_not_revalidated"
                )

            semantic = (
                semantic_result.revalidation
            )

            if not semantic.is_fresh(
                started
            ):
                return self._unknown(
                    "semantic_target_expired"
                )

            if (
                type(focus_observation_id)
                is not str
                or not focus_observation_id
            ):
                return self._unknown(
                    "focus_provenance_unavailable"
                )

            try:
                focus = (
                    self._focus_store.get(
                        focus_observation_id
                    )
                )
            except Exception:
                focus = None

            if (
                type(focus)
                is not FocusDesktopProvenance
            ):
                return self._unknown(
                    "focus_provenance_unavailable"
                )

            if (
                focus.application_pid
                != semantic.application_pid
                or focus.application_bundle_id
                != semantic.application_bundle_id
            ):
                return self._unknown(
                    "focus_application_mismatch"
                )

            expected_application = (
                ApplicationIdentity(
                    semantic.application_pid,
                    semantic.application_bundle_id,
                )
            )

            try:
                correlation = (
                    self._correlation_runtime(
                        expected_application,
                        semantic.selector,
                        timeout_seconds=(
                            correlation_timeout_seconds
                        ),
                    )
                )
            except Exception:
                return self._unknown(
                    "correlation_unknown"
                )

            if (
                type(correlation)
                is not FocusTargetCorrelationResult
            ):
                return self._unknown(
                    "correlation_invalid"
                )

            if (
                correlation.status
                == CORRELATION_STATUS_UNKNOWN
            ):
                return self._unknown(
                    "correlation_unknown"
                )

            if (
                correlation.status
                == CORRELATION_STATUS_AMBIGUOUS
            ):
                return self._unknown(
                    "correlation_ambiguous"
                )

            if (
                correlation.status
                == CORRELATION_STATUS_MISMATCHED
            ):
                return self._unknown(
                    "correlation_mismatch"
                )

            if (
                correlation.status
                != CORRELATION_STATUS_MATCHED
                or not correlation.matched
            ):
                return self._unknown(
                    "correlation_invalid"
                )

            issued = (
                self._now()
            )

            if issued is None:
                return self._unknown(
                    "clock_unavailable"
                )

            try:
                provenance = (
                    compose_focus_target_provenance(
                        semantic_result,
                        focus,
                        correlation,
                        clock=lambda: issued,
                    )
                )
            except Exception:
                return self._unknown(
                    "composition_failed"
                )

            try:
                accepted = (
                    self._provenance_store
                    .publish(
                        provenance
                    )
                )
            except Exception:
                accepted = False

            if not accepted:
                self._provenance_store.clear()

                return self._unknown(
                    "publication_failed"
                )

            try:
                active = (
                    self._provenance_store
                    .get(
                        provenance
                    )
                )
            except Exception:
                active = None

            if (
                active
                is not provenance
            ):
                self._provenance_store.clear()

                return self._unknown(
                    "publication_failed"
                )

            return FocusTargetProvenanceProduction(
                status=(
                    PRODUCTION_STATUS_MATCHED
                ),
                provenance=provenance,
                correlation=correlation,
                diagnostics=(),
            )

        finally:
            self._lock.release()


FOCUS_TARGET_PRODUCER = (
    FocusTargetProvenanceProducer()
)
