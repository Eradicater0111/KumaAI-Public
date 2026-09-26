"""
KUMA-INTEGRATION-1A — shadow Raphael cognition.

This is the first production integration seam between KUMA's live user-turn
runtime and the frozen RAPHAEL V1 cognitive architecture.

One live KUMA user turn may project already-owned state into:

    TaskState + resolver-gated memory context + registered tool names
        ↓
    WorldStateSnapshot
        ↓
    TacticalSituation
        ↓
    ShadowCognitionResult
    AUTHORITY:NONE
        ↓
    STOP

The result is observational only. It is not added to the model prompt, does
not choose an option, does not prepare an execution handoff, and does not
change KUMA's existing safety/execution path.

Important boundaries:

- SHADOW COGNITION != MODEL CONTEXT
- OBSERVATION != AUTHORITY
- CAPABILITY AVAILABILITY != PERMISSION
- FAILURE != PERMISSION
- SHADOW RESULT != ACTION CANDIDATE
- SHADOW RESULT != EXECUTION HANDOFF
- NO REALTIME QUEUE IS DRAINED OR POLLED HERE
- NO DESKTOP SENSOR IS INVOKED HERE

KumaAgent owns failure isolation. If this evaluator raises, the caller may log
the failure and continue the pre-existing user-turn path unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from app.agent.capability_registry import (
    create_default_capability_registry,
)
from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.task_state import TaskState
from app.agent.tactical_analysis import (
    TacticalAnalyzer,
)
from app.agent.world_model import (
    WorldModelBuilder,
)


SHADOW_COGNITION_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_TOOL_NAMES = 128
_MAX_TOOL_NAME_CHARS = 240
_MAX_MEMORY_CONTEXT_CHARS = 1200


def _tool_names(
    values: Iterable[str],
) -> tuple[str, ...]:
    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        raise TypeError(
            "available_tool_names must be an iterable of strings."
        )

    try:
        raw = tuple(
            values
        )
    except TypeError as error:
        raise TypeError(
            "available_tool_names must be iterable."
        ) from error

    if len(
        raw
    ) > _MAX_TOOL_NAMES:
        raise ValueError(
            "available_tool_names exceed the bounded shadow limit."
        )

    normalized = []

    for value in raw:
        if type(
            value
        ) is not str:
            raise TypeError(
                "available_tool_names must contain strings."
            )

        name = value.strip()

        if not name:
            raise ValueError(
                "available_tool_names cannot contain blank names."
            )

        if len(
            name
        ) > _MAX_TOOL_NAME_CHARS:
            raise ValueError(
                "available tool name exceeds the bounded shadow limit."
            )

        normalized.append(
            name
        )

    return tuple(
        sorted(
            set(
                normalized
            )
        )
    )


def _memory_evidence(
    memory_context: str,
) -> tuple[str, ...]:
    if type(
        memory_context
    ) is not str:
        raise TypeError(
            "memory_context must be a string."
        )

    normalized = " ".join(
        memory_context.split()
    )

    if not normalized:
        return ()

    return (
        normalized[
            :_MAX_MEMORY_CONTEXT_CHARS
        ],
    )


@dataclass(
    frozen=True,
    slots=True,
)
class ShadowCognitionResult:
    """
    Immutable zero-authority result of one live-turn shadow projection.

    It intentionally contains only the first two RAPHAEL cognition layers.
    No option generation, decision, attention, handoff, permission or
    execution state is represented here.
    """

    snapshot: WorldStateSnapshot
    situation: TacticalSituation
    authority: str = field(
        default=SHADOW_COGNITION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.snapshot,
            WorldStateSnapshot,
        ):
            raise TypeError(
                "snapshot must be WorldStateSnapshot."
            )

        if (
            self.snapshot.authority
            != SHADOW_COGNITION_AUTHORITY_NONE
        ):
            raise ValueError(
                "WorldStateSnapshot authority must remain NONE."
            )

        if not isinstance(
            self.situation,
            TacticalSituation,
        ):
            raise TypeError(
                "situation must be TacticalSituation."
            )

        if (
            self.situation.authority
            != SHADOW_COGNITION_AUTHORITY_NONE
        ):
            raise ValueError(
                "TacticalSituation authority must remain NONE."
            )

        if (
            self.situation.world_state
            != self.snapshot
        ):
            raise ValueError(
                "TacticalSituation must remain bound to the shadow snapshot."
            )


def evaluate_shadow_cognition(
    *,
    task_state: TaskState,
    available_tool_names: Iterable[str] = (),
    memory_context: str = "",
    now: datetime | None = None,
) -> ShadowCognitionResult:
    """
    Build exactly one observational RAPHAEL shadow projection.

    The caller supplies already-owned state. This function performs no tool
    lookup, tool execution, realtime polling, desktop capture, memory
    retrieval, model call, notification, persistence, or runtime mutation.
    """

    if not isinstance(
        task_state,
        TaskState,
    ):
        raise TypeError(
            "task_state must be TaskState."
        )

    tools = _tool_names(
        available_tool_names
    )

    relevant_memory = _memory_evidence(
        memory_context
    )

    snapshot = WorldModelBuilder().build(
        task_state=task_state,
        relevant_memory=relevant_memory,
        now=now,
    )

    situation = TacticalAnalyzer(
        capability_registry=(
            create_default_capability_registry()
        )
    ).analyze(
        snapshot,
        available_tool_names=tools,
    )

    return ShadowCognitionResult(
        snapshot=snapshot,
        situation=situation,
    )
