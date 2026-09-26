"""
KUMA-RUNTIME-2C — live zero-authority GUI turn trace binding.

Runtime-2C binds frozen Runtime-2A tracing and Runtime-2B turn/session
correlation to the existing synchronous GUI runtime boundary.

Observed lifecycle only:

    turn.started
    agent.run.started
    agent.run.returned | agent.run.raised
    turn.ended

Boundaries:

- TRACE != AUTHORITY
- OBSERVATION != COMMAND
- RESPONSE != VERIFIED GOAL COMPLETION
- TRACE FAILURE != KUMA FAILURE
- CORRELATION FAILURE != EXECUTION DENIAL
- LIVE TRACE != MODEL CONTEXT
- LIVE TRACE != MEMORY
- LIVE TRACE != PERMISSION
- LIVE TRACE != EXECUTION
- AUTHORITY = NONE

No request payload is accepted here. The wrapped operation is an opaque
callable. Its arguments, return value, exception message, model state,
memory state, tool arguments, screen content, and response content are never
copied into trace metadata.

Observability is fail-soft: diagnostic failure must never become authority
over whether the wrapped KUMA operation runs.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from app.runtime_correlation import (
    CORRELATION_AUTHORITY_NONE,
    KumaRuntimeCorrelation,
    RuntimeTurnCorrelation,
    RuntimeTurnEndKind,
    correlation_metadata,
)


LIVE_TRACE_AUTHORITY_NONE = CORRELATION_AUTHORITY_NONE
_ResultT = TypeVar("_ResultT")


class KumaRuntimeLiveTraceBinding:
    """Diagnostic-only binding around one real synchronous runtime call."""

    def __init__(
        self,
        *,
        correlation: KumaRuntimeCorrelation | None = None,
    ):
        if correlation is not None and not isinstance(
            correlation,
            KumaRuntimeCorrelation,
        ):
            raise TypeError(
                "correlation must be KumaRuntimeCorrelation or None."
            )

        self._correlation = (
            correlation
            if correlation is not None
            else KumaRuntimeCorrelation()
        )

    @property
    def authority(self) -> str:
        return LIVE_TRACE_AUTHORITY_NONE

    @property
    def session_id(self) -> str:
        return self._correlation.session_id

    @property
    def active_turn(self) -> RuntimeTurnCorrelation | None:
        return self._correlation.active_turn

    def events(self):
        """Return bounded in-memory session events; diagnostics fail soft."""
        try:
            return self._correlation.events_for_session()
        except Exception:
            return ()

    def _record(
        self,
        *,
        context: RuntimeTurnCorrelation,
        event_kind: str,
        outcome: str,
    ) -> None:
        try:
            self._correlation.trace.record(
                trace_id=context.trace_id,
                stage="runtime",
                event_kind=event_kind,
                outcome=outcome,
                metadata=correlation_metadata(context),
            )
        except Exception:
            return

    def _end(
        self,
        *,
        context: RuntimeTurnCorrelation,
        end_kind: RuntimeTurnEndKind,
    ) -> None:
        try:
            self._correlation.end_turn(
                turn_id=context.turn_id,
                end_kind=end_kind,
            )
        except Exception:
            return

    def observe_pipeline_event(
        self,
        *,
        event_kind: str,
        outcome: str,
    ) -> None:
        # Structural diagnostics only. No payload is accepted here.
        rules = {
            "permission.classified": (
                "authority",
                frozenset(
                    (
                        "safe",
                        "user_authorized",
                        "dangerous",
                    )
                ),
            ),
            "confirmation.resolved": (
                "authority",
                frozenset(
                    (
                        "approved",
                        "denied",
                    )
                ),
            ),
            "executor.returned": (
                "execution",
                frozenset(
                    (
                        "success",
                        "failure",
                    )
                ),
            ),
            "verifier.returned": (
                "verification",
                frozenset(
                    (
                        "true",
                        "false",
                    )
                ),
            ),
            "body_verifier.returned": (
                "verification",
                frozenset(("true", "false")),
            ),
            "state_verification.returned": (
                "verification",
                frozenset(
                    (
                        "known_changed",
                        "known_unchanged",
                        "unknown",
                        "contract_failure",
                    )
                ),
            ),
            "objective_verification.returned": (
                "verification",
                frozenset(
                    (
                        "satisfied",
                        "unsatisfied",
                        "unknown",
                        "contract_failure",
                    )
                ),
            ),
            "recovery.effect_barrier": (
                "recovery",
                frozenset(("escalate",)),
            ),
            "recovery.decision": (
                "recovery",
                frozenset(
                    (
                        "none",
                        "retry",
                        "repair_arguments",
                        "alternative_capability",
                        "resume",
                        "escalate",
                    )
                ),
            ),
            "recovery.strategy_mode": (
                "recovery",
                frozenset(("automatic", "manual")),
            ),
        }

        if type(event_kind) is not str:
            return

        if type(outcome) is not str:
            return

        rule = rules.get(
            event_kind
        )

        if rule is None:
            return

        stage, allowed_outcomes = rule

        if outcome not in allowed_outcomes:
            return

        try:
            context = (
                self._correlation.active_turn
            )

            if context is None:
                return

            self._correlation.trace.record(
                trace_id=context.trace_id,
                stage=stage,
                event_kind=event_kind,
                outcome=outcome,
                metadata=(
                    correlation_metadata(
                        context
                    )
                ),
            )

        except Exception:
            return

    def run(
        self,
        operation: Callable[[], _ResultT],
    ) -> _ResultT:
        """
        Run one opaque operation while observing structural lifecycle only.

        If correlation setup fails, the operation still runs exactly once.
        If the operation raises, the same exception propagates after a
        best-effort ERROR terminal observation.
        """
        if not callable(operation):
            raise TypeError(
                "operation must be callable."
            )

        try:
            context = self._correlation.begin_turn()
        except Exception:
            return operation()

        self._record(
            context=context,
            event_kind="agent.run.started",
            outcome="observed",
        )

        try:
            result = operation()
        except BaseException:
            self._record(
                context=context,
                event_kind="agent.run.raised",
                outcome="error",
            )
            self._end(
                context=context,
                end_kind=RuntimeTurnEndKind.ERROR,
            )
            raise

        self._record(
            context=context,
            event_kind="agent.run.returned",
            outcome="response",
        )
        self._end(
            context=context,
            end_kind=RuntimeTurnEndKind.RESPONSE,
        )
        return result

    def close(self):
        """
        Best-effort session close.

        Runtime-2B converts any active turn to CANCELLED. Diagnostic failure
        remains isolated from application shutdown.
        """
        try:
            return self._correlation.close_session()
        except Exception:
            return None
