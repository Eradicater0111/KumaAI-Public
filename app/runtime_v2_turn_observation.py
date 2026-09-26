from __future__ import annotations

"""
KUMA RUNTIME-V2A — explicit-caller active-turn observation owner.

This additive owner composes frozen Runtime V1 with frozen Realtime V2.

The caller explicitly invokes run(). Runtime-V2A then:

    1. lets frozen Runtime V1 begin the runtime turn;
    2. attaches an already-created RealtimeTriggerObservation to that turn;
    3. invokes the caller-supplied operation exactly once;
    4. lets frozen Runtime V1 close the turn normally.

The realtime observation is diagnostic evidence only. It is never the reason
the operation begins and never grants permission to execute anything.

CALLER INVOCATION -> RUN
REALTIME OBSERVATION -> TRACE ATTACHMENT ONLY

OBSERVATION ATTACHMENT != ADMISSION TO EXECUTE
TRACE != CONTROL
OBSERVATION != EXECUTION
ATTACHMENT FAILURE != EXECUTION FAILURE
AUTHORITY: NONE
"""

from typing import Callable, TypeVar

from app.realtime.runtime_trace_adapter import (
    record_trigger_observation,
)
from app.realtime.trigger_observation import (
    RealtimeTriggerObservation,
)
from app.runtime_correlation import (
    CORRELATION_AUTHORITY_NONE,
    KumaRuntimeCorrelation,
    RuntimeTurnCorrelation,
)
from app.runtime_live_binding import (
    KumaRuntimeLiveTraceBinding,
)
from app.runtime_trace import (
    RuntimeTraceEvent,
)


_ResultT = TypeVar("_ResultT")

RUNTIME_V2_TURN_OBSERVATION_AUTHORITY_NONE = "NONE"


class KumaRuntimeTurnObservationOwner:
    """
    Explicit-caller owner for zero-authority observation attachment.

    This owner does not acquire realtime signals, create trigger proposals,
    decide eligibility, create requests, create observations, start background
    work, surface UI, call a model/tool, classify permission, or execute a
    capability.

    The only operation it invokes is the zero-argument operation explicitly
    supplied by its caller to run().
    """

    def __init__(
        self,
        *,
        correlation: KumaRuntimeCorrelation | None = None,
    ) -> None:
        if correlation is None:
            correlation = KumaRuntimeCorrelation()

        if not isinstance(
            correlation,
            KumaRuntimeCorrelation,
        ):
            raise TypeError(
                "correlation must be KumaRuntimeCorrelation or None."
            )

        if (
            correlation.authority
            != CORRELATION_AUTHORITY_NONE
        ):
            raise ValueError(
                "runtime correlation authority must remain NONE."
            )

        self._correlation = correlation
        self._binding = KumaRuntimeLiveTraceBinding(
            correlation=correlation
        )

    @property
    def authority(self) -> str:
        return RUNTIME_V2_TURN_OBSERVATION_AUTHORITY_NONE

    @property
    def correlation(self) -> KumaRuntimeCorrelation:
        return self._correlation

    @property
    def active_turn(self) -> RuntimeTurnCorrelation | None:
        return self._binding.active_turn

    def events(self) -> tuple[RuntimeTraceEvent, ...]:
        """
        Return the frozen Runtime V1 bounded session trace snapshot.
        """
        return self._binding.events()

    def run(
        self,
        operation: Callable[[], _ResultT],
        *,
        observation: RealtimeTriggerObservation,
    ) -> _ResultT:
        """
        Run one explicit caller operation inside frozen Runtime V1.

        Observation attachment is best-effort and fail-soft. A malformed,
        stale, unavailable, or otherwise unrecordable observation must never
        decide whether the caller's already-requested operation runs.

        The active turn is created and closed only by frozen Runtime V1.
        Runtime-V2A neither calls begin_turn() nor end_turn().
        """

        if not callable(operation):
            raise TypeError(
                "operation must be callable."
            )

        def operation_with_observation():
            turn = self._correlation.active_turn

            if turn is not None:
                try:
                    record_trigger_observation(
                        observation,
                        correlation=self._correlation,
                        turn=turn,
                    )
                except Exception:
                    # Diagnostic attachment is strictly fail-soft.
                    #
                    # ATTACHMENT FAILURE != EXECUTION FAILURE
                    # TRACE != CONTROL
                    pass

            return operation()

        return self._binding.run(
            operation_with_observation
        )

    def close(self) -> None:
        """
        Close the frozen Runtime V1 binding.

        Closing is explicit caller lifecycle management and creates no
        execution or realtime authority.
        """
        self._binding.close()
