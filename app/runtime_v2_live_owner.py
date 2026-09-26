from __future__ import annotations

"""
KUMA RUNTIME-V2D — live explicit-caller production invocation owner.

This additive owner exposes the frozen Runtime-V2C dispatcher to production
callers without widening Runtime-V2C's deliberately narrow public surface.

The caller must already possess explicit intent and an operation. This owner
constructs one RuntimeInvocation, optionally carrying one already-admitted
zero-authority observation, and dispatches it exactly once through Runtime-V2C.

Pipeline observation is structural trace attachment only. The observer bridge
reuses Runtime-V2C's internally owned frozen Runtime V1 binding so events land
on the exact active dispatcher-owned correlation. It accepts no payload.

CALLER INTENT -> EXPLICIT OPERATION -> RuntimeInvocation -> Runtime-V2C
PIPELINE EVENT -> ACTIVE TURN TRACE ONLY
OPTIONAL OBSERVATION -> EVIDENCE ONLY

OWNER != ADMISSION
OWNER != SCHEDULER
OWNER != PERMISSION
OWNER != EXECUTION AUTHORITY
PIPELINE OBSERVATION != CONTROL
OBSERVATION != INVOCATION
ONE RUN CALL = ONE RuntimeInvocation
AUTHORITY: NONE
"""

from typing import Callable, TypeVar

from app.runtime_v2_dispatch import (
    KumaRuntimeInvocationDispatcher,
)
from app.runtime_v2_invocation import (
    RuntimeInvocation,
)


_ResultT = TypeVar("_ResultT")

RUNTIME_V2D_AUTHORITY_NONE = "NONE"


class KumaRuntimeV2LiveOwner:
    """
    Production owner for one explicit caller invocation at a time.

    The owner acquires no realtime signal, chooses no observation, performs no
    admission, and owns no model/tool permission. Optional observation input is
    accepted only as already-existing evidence for RuntimeInvocation validation.
    """

    def __init__(
        self,
    ) -> None:
        self._dispatcher = (
            KumaRuntimeInvocationDispatcher()
        )

        if (
            self._dispatcher.authority
            != RUNTIME_V2D_AUTHORITY_NONE
        ):
            raise ValueError(
                "runtime dispatcher authority must remain NONE."
            )

        # Runtime-V2C intentionally exposes only run/events/close.
        # Runtime-V2D is the single descendant bridge allowed to reuse the
        # dispatcher's internally owned frozen Runtime V1 structural observer.
        # Both plain and observed branches share the same correlation, so this
        # callback always targets the exact active dispatcher-owned turn.
        plain_binding = getattr(
            self._dispatcher,
            "_plain_binding",
            None,
        )

        observer = getattr(
            plain_binding,
            "observe_pipeline_event",
            None,
        )

        if not callable(observer):
            raise RuntimeError(
                "runtime dispatcher does not expose its frozen trace observer."
            )

        self._pipeline_observer = observer

    @property
    def authority(
        self,
    ) -> str:
        return RUNTIME_V2D_AUTHORITY_NONE

    def run(
        self,
        operation: Callable[[], _ResultT],
        *,
        observation=None,
    ) -> _ResultT:
        """
        Dispatch one already-explicit caller operation exactly once.

        Optional observation data cannot create the invocation. Runtime-V2B
        validates its type and permanent zero-authority contract.
        """
        invocation = RuntimeInvocation(
            operation=operation,
            observation=observation,
        )

        return self._dispatcher.run(
            invocation
        )

    def observe_pipeline_event(
        self,
        *,
        event_kind: str,
        outcome: str,
    ) -> None:
        """
        Attach one payload-free structural event to the active runtime turn.

        Diagnostics remain fail-soft and have no effect on execution.
        """
        try:
            return self._pipeline_observer(
                event_kind=event_kind,
                outcome=outcome,
            )
        except Exception:
            return None

    def events(
        self,
    ):
        """Return the bounded dispatcher-owned runtime trace snapshot."""
        return self._dispatcher.events()

    def close(
        self,
    ) -> None:
        """Close the one dispatcher-owned runtime session."""
        return self._dispatcher.close()
