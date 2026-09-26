from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable, TypeVar

from app.integration_v2_explicit_signal_runtime_bridge import (
    run_explicit_operation_with_realtime_signal,
)
from app.integration_v2_realtime_turn_preflight import (
    RealtimeTurnPreflight,
    prepare_realtime_turn,
)
from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
)
from app.realtime.runtime import (
    RealtimeRuntime,
)
from app.runtime_v2_live_owner import (
    KumaRuntimeV2LiveOwner,
)


_ResultT = TypeVar(
    "_ResultT"
)

INTEGRATION_V2D_AUTHORITY_NONE = "NONE"


# =========================================================
# KUMA INTEGRATION-V2D — LIVE TURN COMPOSITION OWNER
# =========================================================
#
# EXPLICIT CALLER OPERATION
#   -> V2C PREFLIGHT ONCE
#   -> OPTIONAL SELECTED SIGNAL
#   -> V2B ADMISSION / RUNTIME-V2D INVOCATION
#   -> EXPLICIT OPERATION ONCE
#
# POLICY INPUT != WAKE POLICY DISCOVERY
# PREFLIGHT != INVOCATION
# SELECTED SIGNAL != INVOCATION
# ADMISSION != INVOCATION
# OBSERVATION != CONTROL
# INTEGRATION OWNER != SCHEDULER
# INTEGRATION OWNER != BACKGROUND LOOP
# INTEGRATION OWNER != PERMISSION
# INTEGRATION OWNER != EXECUTION AUTHORITY
# AUTHORITY: NONE
#
# This owner composes already-frozen public boundaries only.
# It does not acquire the process-global RealtimeRuntime, select hidden
# threshold defaults, invoke itself, call tools/models, or own runtime
# shutdown. Runtime-V2D remains the actual single-turn runtime owner.
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class RealtimeTriggerAdmissionPolicy:
    """
    Explicit caller-owned trigger eligibility criteria.

    No defaults are provided. This carrier deliberately does not borrow
    Raphael attention thresholds; trigger eligibility and attention
    surfacing remain separate policies.
    """

    minimum_level: RealtimeRelevanceLevel
    minimum_score: float
    authority: str = field(
        default=INTEGRATION_V2D_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.minimum_level,
            RealtimeRelevanceLevel,
        ):
            raise TypeError(
                "minimum_level must be RealtimeRelevanceLevel."
            )

        if (
            self.minimum_level
            == RealtimeRelevanceLevel.IGNORE
        ):
            raise ValueError(
                "minimum_level cannot be IGNORE."
            )

        score = float(
            self.minimum_score
        )

        if (
            not math.isfinite(
                score
            )
            or not 0.0 <= score <= 1.0
        ):
            raise ValueError(
                "minimum_score must be finite and between 0.0 and 1.0."
            )

        object.__setattr__(
            self,
            "minimum_score",
            score,
        )

        if self.authority != INTEGRATION_V2D_AUTHORITY_NONE:
            raise ValueError(
                "RealtimeTriggerAdmissionPolicy authority must remain NONE."
            )


class KumaIntegrationV2LiveTurnOwner:
    """
    Explicit-caller composition over frozen Integration-V2B/V2C and Runtime-V2D.

    The caller supplies:
      - one existing Runtime-V2D live owner;
      - one existing RealtimeRuntime or None;
      - one explicit immutable trigger policy.

    run() prepares realtime evidence exactly once, then delegates the explicit
    operation through frozen Integration-V2B. The operation receives the exact
    immutable RealtimeTurnPreflight by identity.
    """

    def __init__(
        self,
        *,
        runtime_owner: KumaRuntimeV2LiveOwner,
        realtime_runtime: RealtimeRuntime | None,
        trigger_policy: RealtimeTriggerAdmissionPolicy,
    ) -> None:
        if not isinstance(
            runtime_owner,
            KumaRuntimeV2LiveOwner,
        ):
            raise TypeError(
                "runtime_owner must be KumaRuntimeV2LiveOwner."
            )

        if (
            realtime_runtime is not None
            and not isinstance(
                realtime_runtime,
                RealtimeRuntime,
            )
        ):
            raise TypeError(
                "realtime_runtime must be RealtimeRuntime or None."
            )

        if not isinstance(
            trigger_policy,
            RealtimeTriggerAdmissionPolicy,
        ):
            raise TypeError(
                "trigger_policy must be RealtimeTriggerAdmissionPolicy."
            )

        if (
            runtime_owner.authority
            != INTEGRATION_V2D_AUTHORITY_NONE
        ):
            raise ValueError(
                "Runtime-V2D owner authority must remain NONE."
            )

        if (
            trigger_policy.authority
            != INTEGRATION_V2D_AUTHORITY_NONE
        ):
            raise ValueError(
                "trigger policy authority must remain NONE."
            )

        self._runtime_owner = (
            runtime_owner
        )
        self._realtime_runtime = (
            realtime_runtime
        )
        self._trigger_policy = (
            trigger_policy
        )

    @property
    def authority(
        self,
    ) -> str:
        return INTEGRATION_V2D_AUTHORITY_NONE

    def run(
        self,
        operation: Callable[
            [RealtimeTurnPreflight],
            _ResultT,
        ],
    ) -> _ResultT:
        """
        Run one already-explicit caller operation through the composition seam.

        The operation is never created from realtime evidence. The prepared
        signal is trace-evidence input only.
        """

        if not callable(
            operation
        ):
            raise TypeError(
                "operation must be callable."
            )

        policy = (
            self._trigger_policy
        )

        preflight = prepare_realtime_turn(
            self._realtime_runtime,
            minimum_level=policy.minimum_level,
            minimum_score=policy.minimum_score,
        )

        return (
            run_explicit_operation_with_realtime_signal(
                self._runtime_owner,
                lambda: operation(
                    preflight
                ),
                signal=preflight.selected_signal,
                minimum_level=policy.minimum_level,
                minimum_score=policy.minimum_score,
            )
        )
