"""
KUMA RAPHAEL-1C tactical situation analysis.

This module interprets one already-built zero-authority WorldStateSnapshot into
a TacticalSituation. It classifies only structured evidence that RAPHAEL-1B
already normalized, plus explicit caller-supplied constraints/uncertainties.

It does not collect evidence, query providers, retrieve memory, call a model,
generate TacticalOptions, select tools, grant permission, or execute actions.
"""

from __future__ import annotations

from typing import Iterable

from app.agent.capability_registry import (
    CapabilityRegistry,
)
from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
    TacticalSituation,
    WorldStateSnapshot,
)


TACTICAL_ANALYSIS_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_ITEMS = 24
_MAX_TEXT_CHARS = 800


def _bounded_text(
    value,
    *,
    max_chars: int = _MAX_TEXT_CHARS,
) -> str:
    normalized = " ".join(
        str(
            value
            if value is not None
            else ""
        ).split()
    )

    if len(normalized) <= max_chars:
        return normalized

    if max_chars <= 3:
        return normalized[
            :max_chars
        ]

    return (
        normalized[
            : max_chars - 3
        ]
        + "..."
    )


def _text_tuple(
    values: Iterable[str],
    *,
    field_name: str,
    limit: int = _MAX_ITEMS,
) -> tuple[str, ...]:
    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        raise TypeError(
            f"{field_name} must be an iterable of strings."
        )

    try:
        raw = tuple(
            values
        )
    except TypeError as error:
        raise TypeError(
            f"{field_name} must be iterable."
        ) from error

    normalized = []

    for item in raw[
        :limit
    ]:
        if type(item) is not str:
            raise TypeError(
                f"{field_name} must contain strings."
            )

        text = _bounded_text(
            item
        )

        if text:
            normalized.append(
                text
            )

    return tuple(
        normalized
    )


def _dedupe(
    values: Iterable[str],
    *,
    limit: int = _MAX_ITEMS,
) -> tuple[str, ...]:
    result = []
    seen = set()

    for value in values:
        text = _bounded_text(
            value
        )

        if (
            not text
            or text in seen
        ):
            continue

        seen.add(
            text
        )
        result.append(
            text
        )

        if len(result) >= limit:
            break

    return tuple(
        result
    )


def _value_after(
    line: str,
    prefix: str,
) -> str | None:
    if not line.startswith(
        prefix
    ):
        return None

    value = _bounded_text(
        line[
            len(prefix):
        ]
    )

    return value or None


def _structured_task_analysis(
    lines: tuple[str, ...],
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    observations = []
    facts = []
    uncertainties = []

    for line in lines:
        value = _value_after(
            line,
            "observation: ",
        )

        if value is not None:
            observations.append(
                "Task observation: "
                + value
            )
            continue

        value = _value_after(
            line,
            "last_evidence: ",
        )

        if value is not None:
            facts.append(
                "Task evidence: "
                + value
            )
            continue

        value = _value_after(
            line,
            "current_step: ",
        )

        if value is not None:
            facts.append(
                "Current task step: "
                + value
            )
            continue

        value = _value_after(
            line,
            "completed: ",
        )

        if value is not None:
            facts.append(
                "Completed task step: "
                + value
            )
            continue

        value = _value_after(
            line,
            "remaining_objective: ",
        )

        if value is not None:
            uncertainties.append(
                "Unresolved objective: "
                + value
            )
            continue

        value = _value_after(
            line,
            "failure: ",
        )

        if value is not None:
            uncertainties.append(
                "Recorded task failure: "
                + value
            )
            continue

        if (
            line
            == "continuation_verification_pending: true"
        ):
            uncertainties.append(
                "Continuation verification is pending."
            )
            continue

        if line.startswith(
            "action: "
        ):
            if (
                " verified=true"
                in line
            ):
                facts.append(
                    "Verified action evidence: "
                    + line[
                        len("action: "):
                    ]
                )
            elif (
                " verified=false"
                in line
            ):
                uncertainties.append(
                    "Unverified action outcome: "
                    + line[
                        len("action: "):
                    ]
                )

    return (
        _dedupe(
            observations
        ),
        _dedupe(
            facts
        ),
        _dedupe(
            uncertainties
        ),
    )


def _structured_mission_analysis(
    lines: tuple[str, ...],
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    observations = []
    facts = []
    uncertainties = []

    for line in lines:
        value = _value_after(
            line,
            "observation: ",
        )

        if value is not None:
            observations.append(
                "Mission observation: "
                + value
            )
            continue

        value = _value_after(
            line,
            "last_evidence: ",
        )

        if value is not None:
            facts.append(
                "Mission evidence: "
                + value
            )
            continue

        value = _value_after(
            line,
            "status: ",
        )

        if value is not None:
            facts.append(
                "Mission status: "
                + value
            )
            continue

        value = _value_after(
            line,
            "current_step_id: ",
        )

        if value is not None:
            facts.append(
                "Current mission step: "
                + value
            )
            continue

        value = _value_after(
            line,
            "completed_step: ",
        )

        if value is not None:
            facts.append(
                "Completed mission step: "
                + value
            )
            continue

        value = _value_after(
            line,
            "remaining_objective: ",
        )

        if value is not None:
            uncertainties.append(
                "Unresolved mission objective: "
                + value
            )
            continue

        value = _value_after(
            line,
            "failed_step: ",
        )

        if value is not None:
            uncertainties.append(
                "Failed mission step: "
                + value
            )
            continue

        value = _value_after(
            line,
            "failure: ",
        )

        if value is not None:
            uncertainties.append(
                "Recorded mission failure: "
                + value
            )
            continue

        if (
            line
            == "continuation_verification_pending: true"
        ):
            uncertainties.append(
                "Mission continuation verification is pending."
            )

    return (
        _dedupe(
            observations
        ),
        _dedupe(
            facts
        ),
        _dedupe(
            uncertainties
        ),
    )


def _available_capabilities(
    registry: CapabilityRegistry | None,
    tool_names: Iterable[str],
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
]:
    tools = _text_tuple(
        tool_names,
        field_name="available_tool_names",
    )

    if not tools:
        return (
            (),
            (),
        )

    if registry is None:
        raise ValueError(
            "available_tool_names require a CapabilityRegistry "
            "so tactical analysis does not invent capability mappings."
        )

    if not isinstance(
        registry,
        CapabilityRegistry,
    ):
        raise TypeError(
            "capability_registry must be CapabilityRegistry or None."
        )

    mapping = (
        registry.capabilities_for_tools(
            set(
                tools
            )
        )
    )

    capabilities = tuple(
        sorted(
            set(
                mapping.values()
            )
        )
    )

    unmapped = tuple(
        sorted(
            tool_name
            for tool_name in tools
            if tool_name not in mapping
        )
    )

    uncertainties = tuple(
        "Available runtime tool has no semantic capability mapping: "
        + tool_name
        for tool_name in unmapped
    )

    return (
        capabilities,
        uncertainties,
    )


class TacticalAnalyzer:
    """
    Deterministically derive one TacticalSituation from existing evidence.

    Classification is label-driven, not keyword-driven. Arbitrary evidence text
    is kept descriptive and never becomes permission, authority, or a command.
    """

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        if (
            capability_registry is not None
            and not isinstance(
                capability_registry,
                CapabilityRegistry,
            )
        ):
            raise TypeError(
                "capability_registry must be CapabilityRegistry or None."
            )

        self._capability_registry = (
            capability_registry
        )

    def analyze(
        self,
        snapshot: WorldStateSnapshot,
        *,
        goal: str | None = None,
        constraints: Iterable[str] = (),
        uncertainties: Iterable[str] = (),
        available_tool_names: Iterable[str] = (),
    ) -> TacticalSituation:
        if not isinstance(
            snapshot,
            WorldStateSnapshot,
        ):
            raise TypeError(
                "snapshot must be WorldStateSnapshot."
            )

        if (
            snapshot.authority
            != TACTICAL_ANALYSIS_AUTHORITY_NONE
        ):
            raise ValueError(
                "world-state authority must remain NONE."
            )

        snapshot_goal = _bounded_text(
            snapshot.task_goal
        )

        explicit_goal = _bounded_text(
            goal
        )

        if (
            snapshot_goal
            and explicit_goal
            and snapshot_goal
            != explicit_goal
        ):
            raise ValueError(
                "explicit tactical goal does not match the world-state goal."
            )

        resolved_goal = (
            snapshot_goal
            or explicit_goal
        )

        if not resolved_goal:
            raise ValueError(
                "tactical analysis requires a grounded goal."
            )

        (
            task_observations,
            task_facts,
            task_uncertainties,
        ) = _structured_task_analysis(
            snapshot.task_state
        )

        (
            mission_observations,
            mission_facts,
            mission_uncertainties,
        ) = _structured_mission_analysis(
            snapshot.mission_state
        )

        observed_state = _dedupe(
            (
                *snapshot.system_state,
                *snapshot.desktop_state,
                *snapshot.realtime_state,
                *snapshot.relevant_memory,
                *task_observations,
                *mission_observations,
            )
        )

        known_facts = _dedupe(
            (
                *task_facts,
                *mission_facts,
            )
        )

        explicit_constraints = _text_tuple(
            constraints,
            field_name="constraints",
        )

        explicit_uncertainties = _text_tuple(
            uncertainties,
            field_name="uncertainties",
        )

        (
            capability_names,
            capability_uncertainties,
        ) = _available_capabilities(
            self._capability_registry,
            available_tool_names,
        )

        combined_uncertainties = _dedupe(
            (
                *task_uncertainties,
                *mission_uncertainties,
                *explicit_uncertainties,
                *capability_uncertainties,
            )
        )

        situation = TacticalSituation(
            goal=resolved_goal,
            observed_state=observed_state,
            known_facts=known_facts,
            uncertainties=combined_uncertainties,
            constraints=explicit_constraints,
            available_capabilities=(
                capability_names
            ),
            world_state=snapshot,
        )

        if (
            situation.authority
            != TACTICAL_ANALYSIS_AUTHORITY_NONE
        ):
            raise RuntimeError(
                "tactical analysis authority invariant failed."
            )

        return situation
