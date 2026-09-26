"""
KUMA-INTEGRATION-1D — verified execution feedback projection.

This module converts an already-existing KUMA execution/verification outcome
into bounded, zero-authority evidence for the next Raphael shadow cognition
state.

It does not execute, verify, retry, authorize, persist, notify, or mutate the
TaskState. KUMA's existing executor/verifier/task-state pipeline remains the
sole source of execution truth.

Pipeline:

    existing KUMA executor
        ↓
    existing KUMA verifier / failure boundary
        ↓
    already-updated TaskState where applicable
        +
    bounded execution-status metadata
        +
    evidence digests only
        ↓
    WorldModelBuilder
        ↓
    TacticalAnalyzer
        ↓
    fresh ShadowCognitionResult
    AUTHORITY:NONE
        ↓
    future shadow reasoning only

Critical boundaries:

- EXECUTION RESULT != VERIFIED FACT
- VERIFIED RESULT = EVIDENCE
- VERIFIED EVIDENCE != AUTHORITY
- FAILURE EVIDENCE != PERMISSION TO RETRY
- SUCCESS EVIDENCE != PERMISSION FOR NEXT ACTION
- FEEDBACK != MEMORY WRITE
- NEXT COGNITION CYCLE != BACKGROUND LOOP
- REALITY -> EVIDENCE -> COGNITION, never COGNITION -> CLAIMED REALITY
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
from typing import Any, Iterable

from app.agent.capability_registry import (
    create_default_capability_registry,
)
from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
)
from app.agent.shadow_cognition import (
    ShadowCognitionResult,
)
from app.agent.task_state import (
    TaskState,
)
from app.agent.tactical_analysis import (
    TacticalAnalyzer,
)
from app.agent.world_model import (
    WorldModelBuilder,
)


EXECUTION_FEEDBACK_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_TOOL_NAME_CHARS = 240
_MAX_TOOL_NAMES = 128
_MAX_MEMORY_CONTEXT_CHARS = 1200
_MAX_EVIDENCE_TEXT_CHARS = 8192
_MAX_VERIFICATION_TEXT_CHARS = 2048


class ExecutionFeedbackKind(str, Enum):
    EXECUTION_FAILED = "execution_failed"
    VERIFICATION_FAILED = "verification_failed"
    VERIFIED_SUCCESS = "verified_success"


def _tool_name(
    value: str,
) -> str:
    if type(value) is not str:
        raise TypeError(
            "tool_name must be a string."
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            "tool_name cannot be blank."
        )

    if len(normalized) > _MAX_TOOL_NAME_CHARS:
        raise ValueError(
            "tool_name exceeds the bounded feedback limit."
        )

    if any(
        character.isspace()
        for character
        in normalized
    ):
        raise ValueError(
            "tool_name cannot contain whitespace."
        )

    return normalized


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

    if len(raw) > _MAX_TOOL_NAMES:
        raise ValueError(
            "available_tool_names exceed the bounded feedback limit."
        )

    normalized = tuple(
        _tool_name(
            value
        )
        for value
        in raw
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


def _bounded_text(
    value: Any,
    *,
    limit: int,
) -> str:
    if value is None:
        return ""

    text = str(
        value
    )

    if len(
        text
    ) > limit:
        text = text[
            :limit
        ]

    return text


def _sha256_text(
    value: Any,
    *,
    limit: int,
) -> str:
    bounded = _bounded_text(
        value,
        limit=limit,
    )

    return hashlib.sha256(
        bounded.encode(
            "utf-8"
        )
    ).hexdigest()


def _kind_from_outcome(
    *,
    execution_success: bool,
    verified: bool,
) -> ExecutionFeedbackKind:
    if type(
        execution_success
    ) is not bool:
        raise TypeError(
            "execution_success must be bool."
        )

    if type(
        verified
    ) is not bool:
        raise TypeError(
            "verified must be bool."
        )

    if (
        not execution_success
        and verified
    ):
        raise ValueError(
            "failed execution cannot be verified success."
        )

    if not execution_success:
        return (
            ExecutionFeedbackKind.EXECUTION_FAILED
        )

    if not verified:
        return (
            ExecutionFeedbackKind.VERIFICATION_FAILED
        )

    return (
        ExecutionFeedbackKind.VERIFIED_SUCCESS
    )


@dataclass(
    frozen=True,
    slots=True,
)
class ExecutionFeedbackEvidence:
    """
    Bounded metadata describing one already-decided KUMA execution outcome.

    Raw tool results, failures, and verification reports are intentionally not
    retained. Their bounded SHA-256 digests are retained only to bind the
    cognition update to the evidence observed at the authoritative boundary.
    """

    kind: ExecutionFeedbackKind
    tool_name: str
    execution_success: bool
    verified: bool
    effect_started: bool
    evidence_digest: str
    verification_digest: str
    authority: str = field(
        default=EXECUTION_FEEDBACK_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.kind,
            ExecutionFeedbackKind,
        ):
            raise TypeError(
                "kind must be ExecutionFeedbackKind."
            )

        object.__setattr__(
            self,
            "tool_name",
            _tool_name(
                self.tool_name
            ),
        )

        if type(
            self.execution_success
        ) is not bool:
            raise TypeError(
                "execution_success must be bool."
            )

        if type(
            self.verified
        ) is not bool:
            raise TypeError(
                "verified must be bool."
            )

        if type(
            self.effect_started
        ) is not bool:
            raise TypeError(
                "effect_started must be bool."
            )

        expected_kind = (
            _kind_from_outcome(
                execution_success=(
                    self.execution_success
                ),
                verified=self.verified,
            )
        )

        if self.kind != expected_kind:
            raise ValueError(
                "feedback kind does not match execution/verification outcome."
            )

        for field_name in (
            "evidence_digest",
            "verification_digest",
        ):
            digest = getattr(
                self,
                field_name,
            )

            if (
                type(
                    digest
                ) is not str
                or len(
                    digest
                ) != 64
                or any(
                    character
                    not in "0123456789abcdef"
                    for character
                    in digest
                )
            ):
                raise ValueError(
                    f"{field_name} must be a lowercase SHA-256 digest."
                )

    def system_evidence_line(
        self,
    ) -> str:
        return (
            "execution_feedback: "
            f"kind={self.kind.value} "
            f"tool={self.tool_name} "
            f"execution_success="
            f"{str(self.execution_success).lower()} "
            f"verified={str(self.verified).lower()} "
            f"effect_started="
            f"{str(self.effect_started).lower()} "
            f"evidence_sha256={self.evidence_digest} "
            f"verification_sha256="
            f"{self.verification_digest} "
            "authority=NONE"
        )


@dataclass(
    frozen=True,
    slots=True,
)
class ExecutionFeedbackProjection:
    feedback: ExecutionFeedbackEvidence
    shadow_result: ShadowCognitionResult
    authority: str = field(
        default=EXECUTION_FEEDBACK_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.feedback,
            ExecutionFeedbackEvidence,
        ):
            raise TypeError(
                "feedback must be ExecutionFeedbackEvidence."
            )

        if not isinstance(
            self.shadow_result,
            ShadowCognitionResult,
        ):
            raise TypeError(
                "shadow_result must be ShadowCognitionResult."
            )

        if (
            self.feedback.authority
            != EXECUTION_FEEDBACK_AUTHORITY_NONE
            or self.shadow_result.authority
            != EXECUTION_FEEDBACK_AUTHORITY_NONE
            or self.shadow_result.snapshot.authority
            != EXECUTION_FEEDBACK_AUTHORITY_NONE
            or self.shadow_result.situation.authority
            != EXECUTION_FEEDBACK_AUTHORITY_NONE
        ):
            raise ValueError(
                "execution feedback projection must remain AUTHORITY:NONE."
            )


def project_execution_feedback(
    *,
    task_state: TaskState,
    available_tool_names: Iterable[str],
    memory_context: str,
    tool_name: str,
    execution_success: bool,
    verified: bool,
    effect_started: bool,
    evidence: Any,
    verification: Any,
    now: datetime | None = None,
) -> ExecutionFeedbackProjection:
    """
    Build a fresh zero-authority Raphael shadow state from an existing KUMA
    execution/verification outcome.

    This function does not mutate TaskState. The caller is responsible for
    invoking it only after the authoritative KUMA boundary has established the
    supplied outcome.
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

    normalized_tool = _tool_name(
        tool_name
    )

    if normalized_tool not in tools:
        raise ValueError(
            "tool_name must be present in available_tool_names."
        )

    if type(
        effect_started
    ) is not bool:
        raise TypeError(
            "effect_started must be bool."
        )

    kind = _kind_from_outcome(
        execution_success=execution_success,
        verified=verified,
    )

    feedback = ExecutionFeedbackEvidence(
        kind=kind,
        tool_name=normalized_tool,
        execution_success=(
            execution_success
        ),
        verified=verified,
        effect_started=effect_started,
        evidence_digest=(
            _sha256_text(
                evidence,
                limit=(
                    _MAX_EVIDENCE_TEXT_CHARS
                ),
            )
        ),
        verification_digest=(
            _sha256_text(
                verification,
                limit=(
                    _MAX_VERIFICATION_TEXT_CHARS
                ),
            )
        ),
    )

    snapshot = WorldModelBuilder().build(
        task_state=task_state,
        system_evidence=(
            feedback.system_evidence_line(),
        ),
        relevant_memory=(
            _memory_evidence(
                memory_context
            )
        ),
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

    shadow_result = ShadowCognitionResult(
        snapshot=snapshot,
        situation=situation,
    )

    return ExecutionFeedbackProjection(
        feedback=feedback,
        shadow_result=shadow_result,
    )
