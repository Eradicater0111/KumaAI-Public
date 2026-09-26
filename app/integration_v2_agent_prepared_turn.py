from __future__ import annotations

from app.integration_v2_realtime_turn_preflight import (
    RealtimeTurnPreflight,
)
from app.realtime.change_detection import (
    RealtimeSignal,
)


INTEGRATION_V2E_AUTHORITY_NONE = "NONE"


# =========================================================
# KUMA INTEGRATION-V2E — AGENT PREPARED REALTIME TURN SEAM
# =========================================================
#
# PREPARED TURN != INVOCATION
# PREPARED SNAPSHOT != ACQUISITION
# PREPARED SNAPSHOT != DRAIN
# SNAPSHOT CONSUMPTION != SIGNAL SELECTION
# SNAPSHOT CONSUMPTION != ADMISSION
# SNAPSHOT CONSUMPTION != PERMISSION
# SNAPSHOT CONSUMPTION != EXECUTION
# AUTHORITY: NONE
#
# This module validates an already-prepared immutable V2C carrier and exposes
# its exact signals tuple for agent-side cognitive reuse. None means the
# legacy agent path remains responsible for its existing tick/snapshot flow.
# An empty prepared tuple is meaningful and must not fall back to acquisition.
# =========================================================


def resolve_prepared_realtime_signals(
    prepared_realtime_turn: RealtimeTurnPreflight | None,
) -> tuple[RealtimeSignal, ...] | None:
    """
    Return the exact prepared signal tuple, or None for the legacy path.

    No realtime runtime is acquired or read here. The returned tuple is the
    exact immutable carrier field by identity, including the empty tuple.
    """

    if prepared_realtime_turn is None:
        return None

    if not isinstance(
        prepared_realtime_turn,
        RealtimeTurnPreflight,
    ):
        raise TypeError(
            "prepared_realtime_turn must be RealtimeTurnPreflight or None."
        )

    if (
        prepared_realtime_turn.authority
        != INTEGRATION_V2E_AUTHORITY_NONE
    ):
        raise ValueError(
            "prepared_realtime_turn authority must remain NONE."
        )

    return prepared_realtime_turn.signals
