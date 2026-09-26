from __future__ import annotations

from dataclasses import dataclass, field

from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.realtime.runtime import RealtimeRuntime
from app.realtime.runtime_trigger import (
    propose_runtime_trigger,
)
from app.realtime.trigger_policy import (
    RealtimeTriggerEligibilityStatus,
    evaluate_trigger_eligibility,
)


INTEGRATION_V2C_AUTHORITY_NONE = "NONE"


# =========================================================
# KUMA INTEGRATION-V2C — REALTIME TURN PREFLIGHT
# =========================================================
#
# EXPLICIT CALLER -> TICK ATTEMPT -> ONE SNAPSHOT -> ELIGIBILITY INSPECTION
# FIRST ELIGIBLE BY SNAPSHOT ORDER -> OPTIONAL SIGNAL -> STOP
#
# TICK != WAKE
# SNAPSHOT != DRAIN
# SELECTION != RANKING
# SELECTED SIGNAL != COMMAND
# PREFLIGHT != ADMISSION
# PREFLIGHT != REQUEST
# PREFLIGHT != OBSERVATION
# PREFLIGHT != INVOCATION
# PREFLIGHT != PERMISSION
# PREFLIGHT != EXECUTION
# AUTHORITY: NONE
#
# This layer owns only explicit-turn preparation over a caller-supplied
# RealtimeRuntime. It does not acquire the process-global runtime, does not
# invoke KUMA, and does not convert a selected signal into an observation.
#
# Snapshot order is already caller-owned bounded RealtimeRuntime queue order.
# V2C deliberately does not create a second relevance ranking policy.
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class RealtimeTurnPreflight:
    """Immutable zero-authority evidence prepared for one explicit turn."""

    signals: tuple[RealtimeSignal, ...]
    selected_signal: RealtimeSignal | None
    tick_attempted: bool
    tick_succeeded: bool
    snapshot_succeeded: bool
    authority: str = field(
        default=INTEGRATION_V2C_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(
            self.signals,
            tuple,
        ):
            raise TypeError(
                "signals must be a tuple of RealtimeSignal values."
            )

        for signal in self.signals:
            if not isinstance(
                signal,
                RealtimeSignal,
            ):
                raise TypeError(
                    "signals must contain only RealtimeSignal values."
                )

            if signal.authority != INTEGRATION_V2C_AUTHORITY_NONE:
                raise ValueError(
                    "RealtimeSignal authority must remain NONE."
                )

        if self.selected_signal is not None:
            if not isinstance(
                self.selected_signal,
                RealtimeSignal,
            ):
                raise TypeError(
                    "selected_signal must be RealtimeSignal or None."
                )

            if not any(
                self.selected_signal is signal
                for signal in self.signals
            ):
                raise ValueError(
                    "selected_signal must be the exact identity of one "
                    "signal in signals."
                )

            if (
                self.selected_signal.authority
                != INTEGRATION_V2C_AUTHORITY_NONE
            ):
                raise ValueError(
                    "selected_signal authority must remain NONE."
                )

        for field_name in (
            "tick_attempted",
            "tick_succeeded",
            "snapshot_succeeded",
        ):
            if type(
                getattr(
                    self,
                    field_name,
                )
            ) is not bool:
                raise TypeError(
                    f"{field_name} must be bool."
                )

        if (
            self.tick_succeeded
            and not self.tick_attempted
        ):
            raise ValueError(
                "tick_succeeded cannot be true when tick was not attempted."
            )

        if self.authority != INTEGRATION_V2C_AUTHORITY_NONE:
            raise ValueError(
                "RealtimeTurnPreflight authority must remain NONE."
            )


def prepare_realtime_turn(
    realtime_runtime: RealtimeRuntime | None,
    *,
    minimum_level: RealtimeRelevanceLevel,
    minimum_score: float,
) -> RealtimeTurnPreflight:
    """
    Prepare zero-authority realtime evidence for one explicit caller-owned turn.

    A supplied runtime receives exactly one tick attempt. Tick failure is
    isolated, matching the existing user-turn boundary. The pending
    signal queue is then read exactly once and never drained.

    Selection is intentionally not ranking: the first signal in the existing
    bounded snapshot order that satisfies frozen Realtime-2A/2B eligibility is
    returned by identity. No request or observation is created here.
    """

    if realtime_runtime is None:
        return RealtimeTurnPreflight(
            signals=(),
            selected_signal=None,
            tick_attempted=False,
            tick_succeeded=False,
            snapshot_succeeded=False,
        )

    if not isinstance(
        realtime_runtime,
        RealtimeRuntime,
    ):
        raise TypeError(
            "realtime_runtime must be RealtimeRuntime or None."
        )

    tick_attempted = True

    try:
        realtime_runtime.tick()
    except Exception:
        tick_succeeded = False
    else:
        tick_succeeded = True

    try:
        signals = tuple(
            realtime_runtime.pending_signals()
        )
    except Exception:
        return RealtimeTurnPreflight(
            signals=(),
            selected_signal=None,
            tick_attempted=tick_attempted,
            tick_succeeded=tick_succeeded,
            snapshot_succeeded=False,
        )

    selected_signal = None

    for signal in signals:
        proposal = propose_runtime_trigger(
            signal
        )

        if proposal is None:
            continue

        decision = evaluate_trigger_eligibility(
            proposal,
            minimum_level=minimum_level,
            minimum_score=minimum_score,
        )

        if (
            decision.status
            == RealtimeTriggerEligibilityStatus.ELIGIBLE
        ):
            selected_signal = signal
            break

    return RealtimeTurnPreflight(
        signals=signals,
        selected_signal=selected_signal,
        tick_attempted=tick_attempted,
        tick_succeeded=tick_succeeded,
        snapshot_succeeded=True,
    )
