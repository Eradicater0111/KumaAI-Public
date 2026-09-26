"""
KUMA-INTEGRATION-1B — shadow evaluation of model-proposed tool actions.

This module evaluates one already-normalized, already-known runtime tool
proposal through the frozen RAPHAEL V1 option/simulation/decision stack.

It is observational only:

    existing KUMA model proposal
        ↓
    normalized tool name + arguments
        ↓
    existing 1A TacticalSituation
        ↓
    canonical capability grounding
        ↓
    TacticalOptionSeed
        ↓
    TacticalOptionGenerator + OutcomeSimulator
        ↓
    TacticalDecisionEngine
        ↓
    ShadowActionEvaluation
    AUTHORITY:NONE
        ↓
    STOP

Critical boundaries:

- SHADOW DECISION != AUTHORITY
- AGREEMENT != PERMISSION
- DISAGREEMENT != BLOCK
- HIGH CONFIDENCE != EXECUTION
- MODEL TOOL CALL != VERIFIED ACTION
- RAPHAEL ACTION_CANDIDATE != KUMA AUTHORIZATION
- ARGUMENT DIGEST != ARGUMENT AUTHORIZATION

This module never calls the executor, confirmation callback, execution bridge,
model, realtime runtime, desktop sensors, memory retrieval, or persistence.
The live KumaAgent hook is deliberately placed after existing request
grounding / dangerous-request checks / unknown-tool checks / argument contract
validation, but before BUILD ACTION, planning, permission/confirmation, and
execution. Existing KUMA safety remains the sole authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Iterable, Mapping

from app.agent.capability_registry import (
    create_default_capability_registry,
)
from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
    TacticalDecision,
    TacticalSituation,
)
from app.agent.permissions import (
    PermissionLevel,
    require_explicit_permission,
)
from app.agent.tactical_decision import (
    TacticalDecisionEngine,
)
from app.agent.tactical_options import (
    ConfidenceBand,
    CostBand,
    OptionKind,
    SimulatedTacticalOption,
    TacticalOptionGenerator,
    TacticalOptionSeed,
)


SHADOW_ACTION_AUTHORITY_NONE = COGNITIVE_AUTHORITY_NONE

_MAX_TOOL_NAME_CHARS = 240
_MAX_TOOL_NAMES = 128
_MAX_ARGUMENT_DEPTH = 12
_MAX_ARGUMENT_ITEMS = 512


class ShadowActionStatus(str, Enum):
    EVALUATED = "evaluated"
    UNAVAILABLE = "unavailable"


def _tool_name(value: str) -> str:
    if type(value) is not str:
        raise TypeError("tool_name must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError("tool_name cannot be blank.")
    if len(normalized) > _MAX_TOOL_NAME_CHARS:
        raise ValueError("tool_name exceeds the bounded shadow limit.")
    return normalized


def _available_tools(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(
            "available_tool_names must be an iterable of strings."
        )
    try:
        raw = tuple(values)
    except TypeError as error:
        raise TypeError(
            "available_tool_names must be iterable."
        ) from error
    if len(raw) > _MAX_TOOL_NAMES:
        raise ValueError(
            "available_tool_names exceed the bounded shadow limit."
        )
    result = []
    for value in raw:
        result.append(_tool_name(value))
    return tuple(sorted(set(result)))


def _canonical_argument_value(
    value: Any,
    *,
    depth: int = 0,
    item_budget: list[int] | None = None,
):
    if item_budget is None:
        item_budget = [_MAX_ARGUMENT_ITEMS]
    if depth > _MAX_ARGUMENT_DEPTH:
        raise ValueError(
            "arguments exceed the bounded nesting depth."
        )
    item_budget[0] -= 1
    if item_budget[0] < 0:
        raise ValueError(
            "arguments exceed the bounded item count."
        )
    if value is None:
        return None
    if type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(
                "arguments cannot contain non-finite floats."
            )
        return value
    if isinstance(value, (list, tuple)):
        return [
            _canonical_argument_value(
                item,
                depth=depth + 1,
                item_budget=item_budget,
            )
            for item in value
        ]
    if isinstance(value, Mapping):
        raw_items = tuple(value.items())
        for key, _ in raw_items:
            if type(key) is not str:
                raise TypeError(
                    "argument mappings must have string keys."
                )
        return {
            key: _canonical_argument_value(
                nested,
                depth=depth + 1,
                item_budget=item_budget,
            )
            for key, nested in sorted(
                raw_items,
                key=lambda item: item[0],
            )
        }
    raise TypeError(
        "arguments contain unsupported value type: "
        f"{type(value).__name__}"
    )


def arguments_digest(arguments: Mapping[str, Any]) -> str:
    if not isinstance(arguments, Mapping):
        raise TypeError("arguments must be a mapping.")
    canonical = _canonical_argument_value(arguments)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ShadowActionEvaluation:
    """Zero-authority shadow assessment of one KUMA model proposal."""

    status: ShadowActionStatus
    tool_name: str
    arguments_digest: str
    reason: str
    capability: str | None = None
    candidate: SimulatedTacticalOption | None = None
    decision: TacticalDecision | None = None
    authority: str = field(
        default=SHADOW_ACTION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tool_name",
            _tool_name(self.tool_name),
        )
        if not isinstance(self.status, ShadowActionStatus):
            raise TypeError(
                "status must be ShadowActionStatus."
            )
        if (
            type(self.arguments_digest) is not str
            or len(self.arguments_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.arguments_digest
            )
        ):
            raise ValueError(
                "arguments_digest must be a lowercase SHA-256 digest."
            )
        if type(self.reason) is not str:
            raise TypeError("reason must be a string.")
        normalized_reason = " ".join(self.reason.split())
        if not normalized_reason:
            raise ValueError("reason cannot be blank.")
        object.__setattr__(
            self,
            "reason",
            normalized_reason,
        )
        if (
            self.capability is not None
            and (
                type(self.capability) is not str
                or not self.capability.strip()
            )
        ):
            raise ValueError(
                "capability must be a nonblank string or None."
            )
        if self.capability is not None:
            object.__setattr__(
                self,
                "capability",
                self.capability.strip(),
            )
        if (
            self.candidate is not None
            and not isinstance(
                self.candidate,
                SimulatedTacticalOption,
            )
        ):
            raise TypeError(
                "candidate must be SimulatedTacticalOption or None."
            )
        if (
            self.decision is not None
            and not isinstance(
                self.decision,
                TacticalDecision,
            )
        ):
            raise TypeError(
                "decision must be TacticalDecision or None."
            )
        if (
            self.candidate is not None
            and self.candidate.authority
            != SHADOW_ACTION_AUTHORITY_NONE
        ):
            raise ValueError(
                "shadow candidate authority must remain NONE."
            )
        if (
            self.decision is not None
            and self.decision.authority
            != SHADOW_ACTION_AUTHORITY_NONE
        ):
            raise ValueError(
                "shadow decision authority must remain NONE."
            )
        if self.status == ShadowActionStatus.EVALUATED:
            if (
                self.capability is None
                or self.candidate is None
                or self.decision is None
            ):
                raise ValueError(
                    "EVALUATED shadow action requires capability, candidate, "
                    "and decision."
                )
            if self.candidate.tool_name != self.tool_name:
                raise ValueError(
                    "shadow candidate tool must match the proposal."
                )
            if (
                self.candidate.option.capability
                != self.capability
            ):
                raise ValueError(
                    "shadow candidate capability must match the evaluation."
                )
        else:
            if (
                self.candidate is not None
                or self.decision is not None
            ):
                raise ValueError(
                    "UNAVAILABLE shadow action cannot carry candidate/decision."
                )


def _reversible_from_permission(
    permission: PermissionLevel,
) -> bool:
    """
    Current SAFE KUMA tools are observational/read-only operations.
    Non-SAFE proposals are conservatively treated as not reversible here.
    """
    return permission == PermissionLevel.SAFE


def evaluate_shadow_action(
    *,
    situation: TacticalSituation,
    tool_name: str,
    arguments: Mapping[str, Any],
    available_tool_names: Iterable[str],
) -> ShadowActionEvaluation:
    """
    Shadow-evaluate one already-normalized KUMA model tool proposal.

    Existing KUMA request grounding and argument validation remain upstream and
    authoritative. This evaluator does not authorize, reject, block, execute,
    confirm, or mutate the live action.
    """
    if not isinstance(situation, TacticalSituation):
        raise TypeError(
            "situation must be TacticalSituation."
        )
    if (
        situation.authority
        != SHADOW_ACTION_AUTHORITY_NONE
    ):
        raise ValueError(
            "TacticalSituation authority must remain NONE."
        )

    normalized_tool = _tool_name(tool_name)
    tools = _available_tools(available_tool_names)
    digest = arguments_digest(arguments)

    if normalized_tool not in tools:
        return ShadowActionEvaluation(
            status=ShadowActionStatus.UNAVAILABLE,
            tool_name=normalized_tool,
            arguments_digest=digest,
            reason=(
                "The proposed tool is not present in the caller-supplied "
                "runtime tool set."
            ),
        )

    capability_registry = (
        create_default_capability_registry()
    )
    capability = (
        capability_registry.capability_for_tool(
            normalized_tool
        )
    )

    if capability is None:
        return ShadowActionEvaluation(
            status=ShadowActionStatus.UNAVAILABLE,
            tool_name=normalized_tool,
            arguments_digest=digest,
            reason=(
                "The registered runtime tool has no canonical semantic "
                "capability mapping for Raphael shadow evaluation."
            ),
        )

    permission = require_explicit_permission(
        normalized_tool
    )
    reversible = _reversible_from_permission(
        permission
    )

    option_id = (
        "shadow-model-proposal-"
        + hashlib.sha256(
            (
                normalized_tool
                + ":"
                + digest
            ).encode("utf-8")
        ).hexdigest()[:24]
    )

    recovery_notes = ()
    if not reversible:
        recovery_notes = (
            "Shadow evaluation assumes no recovery capability; existing "
            "KUMA recovery and verification remain authoritative.",
        )

    seed = TacticalOptionSeed(
        option_id=option_id,
        kind=OptionKind.ACT,
        objective=(
            "Evaluate the already-grounded KUMA model proposal for "
            f"registered tool '{normalized_tool}'."
        ),
        rationale=(
            "KUMA's existing runtime produced and validated this proposal; "
            "Raphael is observing it independently without granting authority."
        ),
        expected_outcome=(
            "If later authorized and executed by existing KUMA, the registered "
            "tool may produce a runtime result that still requires existing "
            "KUMA verification."
        ),
        confidence_band=ConfidenceBand.LOW,
        reversible=reversible,
        tool_name=normalized_tool,
        capability=capability,
        cost_band=CostBand.MEDIUM,
        assumptions=(
            "The shadow evaluator has not executed the proposed tool.",
        ),
        failure_modes=(
            "A later authoritative KUMA execution may fail or return "
            "insufficient evidence.",
        ),
        recovery_notes=recovery_notes,
        verification_requirements=(
            "Existing KUMA verification must establish any real-world "
            "outcome after execution.",
        ),
    )

    candidates = TacticalOptionGenerator(
        capability_registry=(
            capability_registry
        )
    ).generate(
        situation,
        (seed,),
        available_tool_names=tools,
    )

    if len(candidates) != 1:
        raise ValueError(
            "shadow action evaluation expected exactly one grounded candidate."
        )

    candidate = candidates[0]

    decision = TacticalDecisionEngine().decide(
        situation,
        candidates,
    )

    return ShadowActionEvaluation(
        status=ShadowActionStatus.EVALUATED,
        tool_name=normalized_tool,
        arguments_digest=digest,
        reason=(
            "Raphael independently evaluated the existing KUMA model proposal. "
            "The result is diagnostic only and cannot alter KUMA authority."
        ),
        capability=capability,
        candidate=candidate,
        decision=decision,
    )
