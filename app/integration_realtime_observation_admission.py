from __future__ import annotations

"""
KUMA INTEGRATION-V2A — pure explicit-signal Realtime V2 observation admission.

This additive adapter composes the already-frozen Realtime V2 contracts:

    caller-supplied RealtimeSignal
              +
    caller-supplied minimum_level
              +
    caller-supplied minimum_score
              ↓
    Realtime-2A proposal
              ↓
    Realtime-2B eligibility
              ↓
    Realtime-2C request
              ↓
    Realtime-2D observation
              ↓
              STOP

It deliberately owns no realtime queue, signal selection, attention ranking,
seen/ack state, runtime turn, agent invocation, GUI lifecycle, scheduler,
background wake, tool/model call, permission decision, or execution.

EXPLICIT SIGNAL INPUT ONLY
SIGNAL INPUT != INVOCATION
ELIGIBILITY != PERMISSION
ADMISSION != ATTENTION SELECTION
OBSERVATION != INVOCATION
OBSERVATION != EXECUTION
AUTHORITY: NONE
"""

from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.realtime.runtime_trigger import (
    propose_runtime_trigger,
)
from app.realtime.trigger_policy import (
    evaluate_trigger_eligibility,
)
from app.realtime.trigger_request import (
    create_trigger_request,
)
from app.realtime.trigger_observation import (
    RealtimeTriggerObservation,
    observe_trigger_request,
)


INTEGRATION_V2A_AUTHORITY_NONE = "NONE"


def admit_realtime_observation(
    signal: RealtimeSignal,
    *,
    minimum_level: RealtimeRelevanceLevel,
    minimum_score: float,
) -> RealtimeTriggerObservation | None:
    """
    Admit one explicit caller-supplied signal through frozen Realtime V2.

    Eligibility thresholds are mandatory caller inputs. This adapter owns no
    defaults and never selects among multiple signals.

    Returning an observation does not invoke KUMA and does not grant
    permission or execution authority.
    """

    proposal = propose_runtime_trigger(
        signal
    )

    if proposal is None:
        return None

    decision = evaluate_trigger_eligibility(
        proposal,
        minimum_level=minimum_level,
        minimum_score=minimum_score,
    )

    request = create_trigger_request(
        proposal,
        decision,
    )

    if request is None:
        return None

    return observe_trigger_request(
        request
    )
