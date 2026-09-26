from __future__ import annotations

"""
KUMA REALTIME-2F — explicit-caller runtime trace adapter.

This module records one already-existing RealtimeTriggerObservation into an
already-existing caller-owned Runtime turn trace.

The adapter does not acquire Realtime state, start or end a runtime turn, wake
KUMA, surface UI, notify the user, schedule work, call a model or tool, grant
permission, execute an action, or claim completion.

RECORDING != CONTROL
TRACE != AUTHORITY
OBSERVATION != EXECUTION
RECORDING != DELIVERY
RECORDING != ACKNOWLEDGMENT
RECORDING != VERIFIED COMPLETION
AUTHORITY: NONE
"""

from app.realtime.trigger_observation import (
    REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE,
    RealtimeTriggerObservation,
    RealtimeTriggerObservationStatus,
)
from app.runtime_correlation import (
    CORRELATION_AUTHORITY_NONE,
    KumaRuntimeCorrelation,
    RuntimeTurnCorrelation,
    correlation_metadata,
)
from app.runtime_trace import (
    TRACE_AUTHORITY_NONE,
    KumaRuntimeTrace,
    RuntimeTraceEvent,
)


REALTIME_RUNTIME_TRACE_AUTHORITY_NONE = "NONE"

_REALTIME_TRACE_STAGE = "realtime"
_REALTIME_TRACE_EVENT_KIND = "trigger.observed"
_REALTIME_TRACE_OUTCOME = "observed"


def record_trigger_observation(
    observation: RealtimeTriggerObservation,
    *,
    correlation: KumaRuntimeCorrelation,
    turn: RuntimeTurnCorrelation,
) -> RuntimeTraceEvent | None:
    """
    Record one zero-authority trigger observation into one active caller turn.

    The caller must supply the exact active RuntimeTurnCorrelation owned by the
    supplied KumaRuntimeCorrelation. The adapter records through the public
    correlation.trace property and never reaches into private runtime state.

    Diagnostic recording is fail-soft after all boundary validation succeeds.
    """

    if not isinstance(
        observation,
        RealtimeTriggerObservation,
    ):
        raise TypeError(
            "observation must be a RealtimeTriggerObservation."
        )

    if (
        observation.authority
        != REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE
    ):
        raise ValueError(
            "RealtimeTriggerObservation authority must remain NONE."
        )

    if (
        observation.status
        != RealtimeTriggerObservationStatus.OBSERVED
    ):
        raise ValueError(
            "RealtimeTriggerObservation status must remain OBSERVED."
        )

    if not isinstance(
        correlation,
        KumaRuntimeCorrelation,
    ):
        raise TypeError(
            "correlation must be a KumaRuntimeCorrelation."
        )

    if (
        correlation.authority
        != CORRELATION_AUTHORITY_NONE
    ):
        raise ValueError(
            "KumaRuntimeCorrelation authority must remain NONE."
        )

    if not isinstance(
        turn,
        RuntimeTurnCorrelation,
    ):
        raise TypeError(
            "turn must be a RuntimeTurnCorrelation."
        )

    if (
        turn.authority
        != CORRELATION_AUTHORITY_NONE
    ):
        raise ValueError(
            "RuntimeTurnCorrelation authority must remain NONE."
        )

    active = correlation.active_turn

    if active is not turn:
        raise ValueError(
            "turn must be the exact active RuntimeTurnCorrelation owned by correlation."
        )

    trace = correlation.trace

    if not isinstance(
        trace,
        KumaRuntimeTrace,
    ):
        raise TypeError(
            "correlation.trace must be a KumaRuntimeTrace."
        )

    if (
        trace.authority
        != TRACE_AUTHORITY_NONE
    ):
        raise ValueError(
            "KumaRuntimeTrace authority must remain NONE."
        )

    metadata = dict(
        correlation_metadata(
            turn
        )
    )

    metadata.update(
        {
            "realtime.observation_id": (
                observation.observation_id
            ),
            "realtime.kind": (
                observation.kind
            ),
            "realtime.status": (
                observation.status.value
            ),
        }
    )

    try:
        return trace.record(
            trace_id=turn.trace_id,
            stage=_REALTIME_TRACE_STAGE,
            event_kind=(
                _REALTIME_TRACE_EVENT_KIND
            ),
            outcome=(
                _REALTIME_TRACE_OUTCOME
            ),
            metadata=metadata,
        )

    except Exception:
        # Diagnostics must never become control.
        return None
