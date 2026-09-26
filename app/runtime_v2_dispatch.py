from __future__ import annotations

"""
KUMA RUNTIME-V2C — centrally owned single-turn invocation dispatcher.

The dispatcher consumes one already-explicit RuntimeInvocation and selects
exactly one frozen runtime branch:

    observation is None
        -> frozen Runtime V1 live binding

    observation is present
        -> frozen Runtime-V2A observation owner

The dispatcher owns the shared runtime correlation, synchronous serialization,
re-entrancy admission, closed-state admission, and one close surface.

It does not acquire signals, admit observations, choose thresholds, schedule
background work, invoke itself, own GUI/CLI policy, grant permission, or own
tool/model execution authority.

CALLER INTENT -> RuntimeInvocation -> DISPATCH
OPTIONAL OBSERVATION -> BRANCH METADATA ONLY

DISPATCH != ADMISSION
SYNCHRONIZATION != SCHEDULER
OBSERVATION != INVOCATION
OBSERVATION != PERMISSION
ONE INVOCATION = ONE SELECTED BRANCH
ONE SUCCESSFUL INVOCATION = ONE RUNTIME TURN
OPERATION EXECUTES EXACTLY ONCE
CLOSED DISPATCHER != FAIL-OPEN EXECUTION
RE-ENTRANT DISPATCH != FAIL-OPEN EXECUTION
TRACE != CONTROL
AUTHORITY: NONE
"""

from threading import RLock
from typing import TypeVar

from app.runtime_correlation import (
    KumaRuntimeCorrelation,
)
from app.runtime_live_binding import (
    KumaRuntimeLiveTraceBinding,
)
from app.runtime_v2_invocation import (
    RuntimeInvocation,
)
from app.runtime_v2_turn_observation import (
    KumaRuntimeTurnObservationOwner,
)


_ResultT = TypeVar("_ResultT")

RUNTIME_V2C_AUTHORITY_NONE = "NONE"


class KumaRuntimeInvocationDispatcher:
    """
    Serialize explicit RuntimeInvocation values into exactly one runtime branch.

    The dispatcher intentionally creates and owns its KumaRuntimeCorrelation.
    No external correlation injection is accepted, preventing callers from
    closing or activating the correlation outside this lifecycle boundary.
    """

    def __init__(
        self,
    ) -> None:
        self._lock = RLock()
        self._closed = False
        self._active = False

        self._correlation = (
            KumaRuntimeCorrelation()
        )

        if (
            self._correlation.authority
            != RUNTIME_V2C_AUTHORITY_NONE
        ):
            raise ValueError(
                "runtime correlation authority must remain NONE."
            )

        self._plain_binding = (
            KumaRuntimeLiveTraceBinding(
                correlation=self._correlation
            )
        )

        self._observed_owner = (
            KumaRuntimeTurnObservationOwner(
                correlation=self._correlation
            )
        )

    @property
    def authority(
        self,
    ) -> str:
        return RUNTIME_V2C_AUTHORITY_NONE

    def run(
        self,
        invocation: RuntimeInvocation[_ResultT],
    ) -> _ResultT:
        """
        Dispatch one explicit invocation through exactly one runtime branch.

        Closed, re-entrant, or structurally busy state is rejected before
        entering frozen Runtime V1, preventing its intentional begin-turn
        fail-open behavior from becoming an untraced dispatcher execution.
        """
        if not isinstance(
            invocation,
            RuntimeInvocation,
        ):
            raise TypeError(
                "invocation must be RuntimeInvocation."
            )

        with self._lock:
            if self._closed:
                raise RuntimeError(
                    "runtime invocation dispatcher is closed."
                )

            if self._active:
                raise RuntimeError(
                    "runtime invocation dispatcher is already active."
                )

            if self._correlation.closed:
                raise RuntimeError(
                    "runtime invocation correlation is closed."
                )

            if (
                self._correlation.active_turn
                is not None
            ):
                raise RuntimeError(
                    "runtime invocation correlation is already active."
                )

            before_turn_count = (
                self._correlation.turn_count
            )

            self._active = True

            try:
                if invocation.observation is None:
                    result = (
                        self._plain_binding.run(
                            invocation.operation
                        )
                    )
                else:
                    result = (
                        self._observed_owner.run(
                            invocation.operation,
                            observation=(
                                invocation.observation
                            ),
                        )
                    )
            finally:
                self._active = False

            if (
                self._correlation.active_turn
                is not None
            ):
                raise RuntimeError(
                    "runtime invocation left an active turn."
                )

            if (
                self._correlation.turn_count
                != before_turn_count + 1
            ):
                raise RuntimeError(
                    "runtime invocation completed without exactly one runtime turn."
                )

            return result

    def events(
        self,
    ):
        """
        Return the shared frozen Runtime V1 session trace snapshot.

        Diagnostics remain fail-soft through the frozen live binding.
        """
        with self._lock:
            return (
                self._plain_binding.events()
            )

    def close(
        self,
    ) -> None:
        """
        Close the one dispatcher-owned runtime session.

        Re-entrant close during an active invocation is rejected. Concurrent
        callers serialize on the same lock and observe the final closed state.
        """
        with self._lock:
            if self._active:
                raise RuntimeError(
                    "cannot close dispatcher during active invocation."
                )

            if self._closed:
                return None

            self._closed = True
            self._plain_binding.close()

            return None
