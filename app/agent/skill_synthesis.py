"""
KUMA RAPHAEL-1H dynamic skill synthesis.

This layer converts a deliberately bounded envelope of already-verified
experience into an untrusted, zero-authority SkillDefinition proposal.

It does NOT read TaskState or MissionState directly. Runtime owners must first
project trusted verification results into VerifiedExperience. This prevents the
synthesizer from receiving mutable execution state, tool registries, receipts,
permissions, GUI authority, or unrelated history.

The model is an injected text-only reasoning callback. This module exposes no
tools to it. Model output is parsed through an exact JSON schema, capability
references are revalidated against the canonical CapabilityRegistry, every
proposed phase must cite verified experience steps, and concrete success /
verification claims must come from cited verified evidence.

The result is proposal knowledge only:
- no SkillRegistry is mutated;
- no tool is registered;
- no permission or approval is granted;
- no executable code is generated or installed;
- no persistence occurs;
- no action is executed.

Critical invariants:
- PREDICTION != EXPERIENCE
- TOOL SUCCESS != VERIFIED EXPERIENCE
- ONE VERIFIED ACTION != REUSABLE SKILL
- MODEL OUTPUT != REGISTERED SKILL
- SKILL PROPOSAL != AUTHORITY
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Callable, Iterable

from app.agent.capability_registry import (
    CapabilityRegistry,
)
from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
)
from app.agent.skill_registry import (
    SkillDefinition,
    SkillPhase,
    SkillRegistry,
)


SKILL_SYNTHESIS_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_TEXT_CHARS = 1200
_MAX_ITEMS = 64
_MAX_STEPS = 24
_MIN_VERIFIED_STEPS = 2


class ExperienceSource(str, Enum):
    TASK_VERIFICATION = "task_verification"
    MISSION_VERIFICATION = "mission_verification"
    OBJECTIVE_VERIFICATION = "objective_verification"
    VERIFIED_SYSTEM = "verified_system"


class SkillSynthesisDisposition(str, Enum):
    PROPOSED = "proposed"
    INSUFFICIENT = "insufficient"
    REJECTED = "rejected"


def _text(
    value,
    *,
    field_name: str,
) -> str:
    if type(value) is not str:
        raise TypeError(
            f"{field_name} must be a string."
        )

    normalized = " ".join(
        value.split()
    )

    if not normalized:
        raise ValueError(
            f"{field_name} cannot be empty."
        )

    if len(normalized) > _MAX_TEXT_CHARS:
        raise ValueError(
            f"{field_name} exceeds the bounded text limit."
        )

    return normalized


def _text_tuple(
    values: Iterable[str],
    *,
    field_name: str,
    allow_empty: bool = True,
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

    if len(raw) > _MAX_ITEMS:
        raise ValueError(
            f"{field_name} exceeds the bounded item limit."
        )

    result = []
    seen = set()

    for item in raw:
        normalized = _text(
            item,
            field_name=field_name,
        )

        if normalized in seen:
            continue

        seen.add(
            normalized
        )
        result.append(
            normalized
        )

    if (
        not allow_empty
        and not result
    ):
        raise ValueError(
            f"{field_name} cannot be empty."
        )

    return tuple(
        result
    )


@dataclass(
    frozen=True,
    slots=True,
)
class VerifiedExperienceStep:
    """
    One successful, verified, effect-known experience step.

    Failure/recovery knowledge belongs on VerifiedExperience separately. A
    failed, unverified, or effect-unknown action cannot masquerade as a
    successful reusable procedure step.
    """

    step_id: str
    objective: str
    capabilities_used: tuple[str, ...]
    success_criteria: tuple[str, ...]
    verification_requirements: tuple[str, ...]
    verified_outcome: str
    verification_evidence: str
    source: ExperienceSource
    reversible: bool
    effect_started: bool
    success: bool = True
    verified: bool = True
    effect_known: bool = True
    authority: str = field(
        default=SKILL_SYNTHESIS_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "step_id",
            _text(
                self.step_id,
                field_name="step_id",
            ),
        )

        object.__setattr__(
            self,
            "objective",
            _text(
                self.objective,
                field_name="objective",
            ),
        )

        for field_name in (
            "capabilities_used",
            "success_criteria",
            "verification_requirements",
        ):
            object.__setattr__(
                self,
                field_name,
                _text_tuple(
                    getattr(
                        self,
                        field_name,
                    ),
                    field_name=field_name,
                    allow_empty=(
                        field_name
                        == "capabilities_used"
                    ),
                ),
            )

        object.__setattr__(
            self,
            "verified_outcome",
            _text(
                self.verified_outcome,
                field_name="verified_outcome",
            ),
        )

        object.__setattr__(
            self,
            "verification_evidence",
            _text(
                self.verification_evidence,
                field_name="verification_evidence",
            ),
        )

        if not isinstance(
            self.source,
            ExperienceSource,
        ):
            raise TypeError(
                "source must be ExperienceSource."
            )

        for field_name in (
            "reversible",
            "effect_started",
            "success",
            "verified",
            "effect_known",
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

        if not self.success:
            raise ValueError(
                "VerifiedExperienceStep requires successful execution."
            )

        if not self.verified:
            raise ValueError(
                "VerifiedExperienceStep requires verified outcome evidence."
            )

        if not self.effect_known:
            raise ValueError(
                "VerifiedExperienceStep requires known effect state."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class VerifiedExperience:
    """
    Bounded synthesis input projected from trusted verification boundaries.

    At least two distinct verified steps are required. This makes a single
    successful action insufficient to become reusable skill knowledge.
    """

    goal: str
    steps: tuple[
        VerifiedExperienceStep,
        ...,
    ]
    failures_recoveries: tuple[str, ...] = ()
    remaining_uncertainties: tuple[str, ...] = ()
    authority: str = field(
        default=SKILL_SYNTHESIS_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "goal",
            _text(
                self.goal,
                field_name="goal",
            ),
        )

        if isinstance(
            self.steps,
            (
                str,
                bytes,
            ),
        ):
            raise TypeError(
                "steps must be an iterable of VerifiedExperienceStep values."
            )

        try:
            steps = tuple(
                self.steps
            )
        except TypeError as error:
            raise TypeError(
                "steps must be iterable."
            ) from error

        if len(
            steps
        ) < _MIN_VERIFIED_STEPS:
            raise ValueError(
                "VerifiedExperience requires at least two verified steps."
            )

        if len(
            steps
        ) > _MAX_STEPS:
            raise ValueError(
                "VerifiedExperience exceeds the bounded step limit."
            )

        ids = []

        for step in steps:
            if not isinstance(
                step,
                VerifiedExperienceStep,
            ):
                raise TypeError(
                    "steps must contain VerifiedExperienceStep values."
                )

            if (
                step.authority
                != SKILL_SYNTHESIS_AUTHORITY_NONE
            ):
                raise ValueError(
                    "VerifiedExperienceStep authority must remain NONE."
                )

            ids.append(
                step.step_id
            )

        if len(
            ids
        ) != len(
            set(
                ids
            )
        ):
            raise ValueError(
                "VerifiedExperience step IDs must be unique."
            )

        object.__setattr__(
            self,
            "steps",
            steps,
        )

        for field_name in (
            "failures_recoveries",
            "remaining_uncertainties",
        ):
            object.__setattr__(
                self,
                field_name,
                _text_tuple(
                    getattr(
                        self,
                        field_name,
                    ),
                    field_name=field_name,
                ),
            )

    @property
    def step_ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            step.step_id
            for step
            in self.steps
        )

    @property
    def capabilities_used(
        self,
    ) -> tuple[str, ...]:
        result = []
        seen = set()

        for step in self.steps:
            for capability in step.capabilities_used:
                if capability in seen:
                    continue

                seen.add(
                    capability
                )
                result.append(
                    capability
                )

        return tuple(
            result
        )

    @property
    def reversible(
        self,
    ) -> bool:
        return all(
            step.reversible
            for step
            in self.steps
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SkillSynthesisProposal:
    """
    Immutable zero-authority synthesis result.

    PROPOSED means only that an untrusted model draft survived exact parsing,
    evidence binding, and 1G structural/capability validation. It is NOT
    registered, installed, approved, executable, or authorized.
    """

    disposition: SkillSynthesisDisposition
    reason: str
    evidence_digest: str
    evidence_step_ids: tuple[str, ...]
    evidence_sufficient: bool
    remaining_uncertainties: tuple[str, ...] = ()
    skill: SkillDefinition | None = None
    authority: str = field(
        default=SKILL_SYNTHESIS_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.disposition,
            SkillSynthesisDisposition,
        ):
            raise TypeError(
                "disposition must be SkillSynthesisDisposition."
            )

        object.__setattr__(
            self,
            "reason",
            _text(
                self.reason,
                field_name="reason",
            ),
        )

        if (
            not isinstance(
                self.evidence_digest,
                str,
            )
            or len(
                self.evidence_digest
            ) != 64
            or any(
                character
                not in "0123456789abcdef"
                for character
                in self.evidence_digest
            )
        ):
            raise ValueError(
                "evidence_digest must be a lowercase SHA-256 hex digest."
            )

        object.__setattr__(
            self,
            "evidence_step_ids",
            _text_tuple(
                self.evidence_step_ids,
                field_name="evidence_step_ids",
                allow_empty=False,
            ),
        )

        if type(
            self.evidence_sufficient
        ) is not bool:
            raise TypeError(
                "evidence_sufficient must be bool."
            )

        object.__setattr__(
            self,
            "remaining_uncertainties",
            _text_tuple(
                self.remaining_uncertainties,
                field_name="remaining_uncertainties",
            ),
        )

        if (
            self.disposition
            == SkillSynthesisDisposition.PROPOSED
        ):
            if not self.evidence_sufficient:
                raise ValueError(
                    "PROPOSED requires sufficient evidence."
                )

            if not isinstance(
                self.skill,
                SkillDefinition,
            ):
                raise ValueError(
                    "PROPOSED requires a SkillDefinition."
                )

            if (
                self.skill.authority
                != SKILL_SYNTHESIS_AUTHORITY_NONE
            ):
                raise ValueError(
                    "Proposed skill authority must remain NONE."
                )

        elif self.skill is not None:
            raise ValueError(
                "Only PROPOSED may carry a SkillDefinition."
            )

        if (
            self.disposition
            == SkillSynthesisDisposition.INSUFFICIENT
            and self.evidence_sufficient
        ):
            raise ValueError(
                "INSUFFICIENT cannot claim sufficient evidence."
            )


def _experience_payload(
    experience: VerifiedExperience,
) -> dict[str, Any]:
    return {
        "goal": experience.goal,
        "steps": [
            {
                "step_id": step.step_id,
                "objective": step.objective,
                "capabilities_used": list(
                    step.capabilities_used
                ),
                "success_criteria": list(
                    step.success_criteria
                ),
                "verification_requirements": list(
                    step.verification_requirements
                ),
                "verified_outcome": step.verified_outcome,
                "verification_evidence": step.verification_evidence,
                "source": step.source.value,
                "reversible": step.reversible,
                "effect_started": step.effect_started,
                "success": step.success,
                "verified": step.verified,
                "effect_known": step.effect_known,
            }
            for step
            in experience.steps
        ],
        "failures_recoveries": list(
            experience.failures_recoveries
        ),
        "remaining_uncertainties": list(
            experience.remaining_uncertainties
        ),
    }


def _evidence_digest(
    experience: VerifiedExperience,
) -> str:
    encoded = json.dumps(
        _experience_payload(
            experience
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        encoded
    ).hexdigest()


def _response_text(
    response: Any,
) -> str:
    if isinstance(
        response,
        str,
    ):
        return response.strip()

    message = getattr(
        response,
        "message",
        response,
    )

    content = getattr(
        message,
        "content",
        message,
    )

    return str(
        content
        or ""
    ).strip()


def _strict_keys(
    data: dict[str, Any],
    expected: set[str],
    *,
    field_name: str,
) -> None:
    actual = set(
        data
    )

    if actual != expected:
        missing = sorted(
            expected
            - actual
        )

        extra = sorted(
            actual
            - expected
        )

        parts = []

        if missing:
            parts.append(
                "missing="
                + repr(
                    missing
                )
            )

        if extra:
            parts.append(
                "extra="
                + repr(
                    extra
                )
            )

        raise ValueError(
            f"{field_name} keys must match the exact schema: "
            + ", ".join(
                parts
            )
        )


def _json_string_list(
    value: Any,
    *,
    field_name: str,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"{field_name} must be a JSON list."
        )

    return _text_tuple(
        value,
        field_name=field_name,
        allow_empty=allow_empty,
    )


class SkillSynthesizer:
    """
    Tool-less, zero-authority skill proposal engine.

    model_call receives only a messages list. The bridge itself has no tool,
    executor, registry-mutation, persistence, or provider surface.
    """

    _TOP_KEYS = {
        "skill_id",
        "description",
        "required_capabilities",
        "preconditions",
        "expected_outcomes",
        "failure_modes",
        "verification_requirements",
        "remaining_uncertainties",
        "phases",
    }

    _PHASE_KEYS = {
        "phase_id",
        "objective",
        "dependencies",
        "required_capabilities",
        "success_criteria",
        "verification_requirements",
        "evidence_step_ids",
    }

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        model_call: Callable[
            [
                list[
                    dict[
                        str,
                        str,
                    ]
                ]
            ],
            Any,
        ],
    ) -> None:
        if not isinstance(
            capability_registry,
            CapabilityRegistry,
        ):
            raise TypeError(
                "capability_registry must be CapabilityRegistry."
            )

        if not callable(
            model_call
        ):
            raise TypeError(
                "model_call must be callable."
            )

        self._capability_registry = (
            capability_registry
        )

        self._model_call = (
            model_call
        )

    def _reject(
        self,
        experience: VerifiedExperience,
        reason: str,
        *,
        sufficient: bool,
        disposition: SkillSynthesisDisposition = (
            SkillSynthesisDisposition.REJECTED
        ),
        uncertainties: tuple[str, ...] | None = None,
    ) -> SkillSynthesisProposal:
        return SkillSynthesisProposal(
            disposition=disposition,
            reason=reason,
            evidence_digest=(
                _evidence_digest(
                    experience
                )
            ),
            evidence_step_ids=(
                experience.step_ids
            ),
            evidence_sufficient=sufficient,
            remaining_uncertainties=(
                experience.remaining_uncertainties
                if uncertainties is None
                else uncertainties
            ),
        )

    def _validate_experience_capabilities(
        self,
        experience: VerifiedExperience,
    ) -> str | None:
        known = set(
            self._capability_registry.names()
        )

        unknown = tuple(
            capability
            for capability
            in experience.capabilities_used
            if capability
            not in known
        )

        if unknown:
            return (
                "Verified experience references capabilities absent from "
                "the current canonical CapabilityRegistry: "
                + ", ".join(
                    unknown
                )
            )

        return None

    @staticmethod
    def _messages(
        experience: VerifiedExperience,
        *,
        capability_names: tuple[str, ...],
    ) -> list[
        dict[
            str,
            str,
        ]
    ]:
        schema = {
            "skill_id": "string",
            "description": "string",
            "required_capabilities": [
                "capability_name"
            ],
            "preconditions": [
                "string"
            ],
            "expected_outcomes": [
                "EXACT verified_outcome from supplied evidence"
            ],
            "failure_modes": [
                "string"
            ],
            "verification_requirements": [
                "EXACT verification requirement from supplied evidence"
            ],
            "remaining_uncertainties": [
                "string"
            ],
            "phases": [
                {
                    "phase_id": "string",
                    "objective": "string",
                    "dependencies": [
                        "phase_id"
                    ],
                    "required_capabilities": [
                        "capability_name"
                    ],
                    "success_criteria": [
                        "EXACT success criterion from cited evidence"
                    ],
                    "verification_requirements": [
                        "EXACT verification requirement from cited evidence"
                    ],
                    "evidence_step_ids": [
                        "verified step_id"
                    ],
                }
            ],
        }

        system = (
            "You are KUMA RAPHAEL's zero-authority skill synthesis reasoner. "
            "You may propose reusable capability-level procedure knowledge "
            "ONLY from the supplied verified experience. Do not invent tools, "
            "permissions, authority, execution results, capabilities, code, "
            "or evidence. Do not request or execute tools. Do not claim the "
            "proposal is installed or registered. Each phase MUST cite one or "
            "more supplied evidence_step_ids. A phase may use only capabilities "
            "present in its cited verified steps. success_criteria and "
            "verification_requirements MUST be copied exactly from cited "
            "verified evidence. Skill-level expected_outcomes and verification "
            "requirements MUST be copied exactly from supplied verified "
            "evidence. Return JSON only with EXACTLY the specified keys."
        )

        user_payload = {
            "canonical_capabilities": list(
                capability_names
            ),
            "verified_experience": (
                _experience_payload(
                    experience
                )
            ),
            "required_output_schema": schema,
        }

        return [
            {
                "role": "system",
                "content": system,
            },
            {
                "role": "user",
                "content": json.dumps(
                    user_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ]

    def _parse_candidate(
        self,
        *,
        experience: VerifiedExperience,
        response: Any,
    ) -> tuple[
        SkillDefinition,
        tuple[str, ...],
    ]:
        text = _response_text(
            response
        )

        if not text:
            raise ValueError(
                "Skill synthesis response was empty."
            )

        try:
            data = json.loads(
                text
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                "Skill synthesis response was not valid JSON."
            ) from error

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "Skill synthesis response must be a JSON object."
            )

        _strict_keys(
            data,
            self._TOP_KEYS,
            field_name="skill synthesis",
        )

        experience_by_id = {
            step.step_id: step
            for step
            in experience.steps
        }

        experienced_capabilities = set(
            experience.capabilities_used
        )

        required_capabilities = (
            _json_string_list(
                data[
                    "required_capabilities"
                ],
                field_name="required_capabilities",
            )
        )

        invented_capabilities = tuple(
            capability
            for capability
            in required_capabilities
            if capability
            not in experienced_capabilities
        )

        if invented_capabilities:
            raise ValueError(
                "Proposed skill expands beyond verified experience "
                "capabilities: "
                + ", ".join(
                    invented_capabilities
                )
            )

        raw_phases = data[
            "phases"
        ]

        if not isinstance(
            raw_phases,
            list,
        ):
            raise ValueError(
                "phases must be a JSON list."
            )

        if not raw_phases:
            raise ValueError(
                "phases cannot be empty."
            )

        if len(
            raw_phases
        ) > _MAX_STEPS:
            raise ValueError(
                "phases exceeds the bounded synthesis limit."
            )

        phases = []
        used_evidence_ids = []
        phase_capability_union = set()

        for index, raw_phase in enumerate(
            raw_phases,
            start=1,
        ):
            if not isinstance(
                raw_phase,
                dict,
            ):
                raise ValueError(
                    f"phase {index} must be a JSON object."
                )

            _strict_keys(
                raw_phase,
                self._PHASE_KEYS,
                field_name=(
                    f"phase {index}"
                ),
            )

            evidence_step_ids = (
                _json_string_list(
                    raw_phase[
                        "evidence_step_ids"
                    ],
                    field_name=(
                        f"phase {index} evidence_step_ids"
                    ),
                    allow_empty=False,
                )
            )

            unknown_ids = tuple(
                step_id
                for step_id
                in evidence_step_ids
                if step_id
                not in experience_by_id
            )

            if unknown_ids:
                raise ValueError(
                    "Proposed phase references unknown verified evidence "
                    "step IDs: "
                    + ", ".join(
                        unknown_ids
                    )
                )

            cited_steps = tuple(
                experience_by_id[
                    step_id
                ]
                for step_id
                in evidence_step_ids
            )

            cited_capabilities = {
                capability
                for step
                in cited_steps
                for capability
                in step.capabilities_used
            }

            phase_capabilities = (
                _json_string_list(
                    raw_phase[
                        "required_capabilities"
                    ],
                    field_name=(
                        f"phase {index} required_capabilities"
                    ),
                )
            )

            unsupported_phase_capabilities = tuple(
                capability
                for capability
                in phase_capabilities
                if capability
                not in cited_capabilities
            )

            if unsupported_phase_capabilities:
                raise ValueError(
                    "Proposed phase capability is not supported by its "
                    "cited verified steps: "
                    + ", ".join(
                        unsupported_phase_capabilities
                    )
                )

            cited_success_criteria = {
                criterion
                for step
                in cited_steps
                for criterion
                in step.success_criteria
            }

            phase_success_criteria = (
                _json_string_list(
                    raw_phase[
                        "success_criteria"
                    ],
                    field_name=(
                        f"phase {index} success_criteria"
                    ),
                    allow_empty=False,
                )
            )

            invented_criteria = tuple(
                criterion
                for criterion
                in phase_success_criteria
                if criterion
                not in cited_success_criteria
            )

            if invented_criteria:
                raise ValueError(
                    "Proposed phase success criteria are not copied from "
                    "cited verified evidence."
                )

            cited_requirements = {
                requirement
                for step
                in cited_steps
                for requirement
                in step.verification_requirements
            }

            phase_requirements = (
                _json_string_list(
                    raw_phase[
                        "verification_requirements"
                    ],
                    field_name=(
                        f"phase {index} verification_requirements"
                    ),
                    allow_empty=False,
                )
            )

            invented_requirements = tuple(
                requirement
                for requirement
                in phase_requirements
                if requirement
                not in cited_requirements
            )

            if invented_requirements:
                raise ValueError(
                    "Proposed phase verification requirements are not "
                    "copied from cited verified evidence."
                )

            phase = SkillPhase(
                phase_id=_text(
                    raw_phase[
                        "phase_id"
                    ],
                    field_name=(
                        f"phase {index} phase_id"
                    ),
                ),
                objective=_text(
                    raw_phase[
                        "objective"
                    ],
                    field_name=(
                        f"phase {index} objective"
                    ),
                ),
                dependencies=(
                    _json_string_list(
                        raw_phase[
                            "dependencies"
                        ],
                        field_name=(
                            f"phase {index} dependencies"
                        ),
                    )
                ),
                required_capabilities=(
                    phase_capabilities
                ),
                success_criteria=(
                    phase_success_criteria
                ),
                verification_requirements=(
                    phase_requirements
                ),
            )

            phases.append(
                phase
            )

            phase_capability_union.update(
                phase_capabilities
            )

            for step_id in evidence_step_ids:
                if step_id not in used_evidence_ids:
                    used_evidence_ids.append(
                        step_id
                    )

        if set(
            required_capabilities
        ) != phase_capability_union:
            raise ValueError(
                "Skill required_capabilities must exactly equal the union "
                "of proposed phase capabilities."
            )

        experienced_outcomes = {
            step.verified_outcome
            for step
            in experience.steps
        }

        expected_outcomes = (
            _json_string_list(
                data[
                    "expected_outcomes"
                ],
                field_name="expected_outcomes",
                allow_empty=False,
            )
        )

        invented_outcomes = tuple(
            outcome
            for outcome
            in expected_outcomes
            if outcome
            not in experienced_outcomes
        )

        if invented_outcomes:
            raise ValueError(
                "Proposed expected outcomes are not copied from verified "
                "experience."
            )

        experienced_requirements = {
            requirement
            for step
            in experience.steps
            for requirement
            in step.verification_requirements
        }

        skill_requirements = (
            _json_string_list(
                data[
                    "verification_requirements"
                ],
                field_name="verification_requirements",
                allow_empty=False,
            )
        )

        invented_skill_requirements = tuple(
            requirement
            for requirement
            in skill_requirements
            if requirement
            not in experienced_requirements
        )

        if invented_skill_requirements:
            raise ValueError(
                "Proposed skill verification requirements are not copied "
                "from verified experience."
            )

        skill = SkillDefinition(
            skill_id=_text(
                data[
                    "skill_id"
                ],
                field_name="skill_id",
            ),
            description=_text(
                data[
                    "description"
                ],
                field_name="description",
            ),
            phases=tuple(
                phases
            ),
            required_capabilities=(
                required_capabilities
            ),
            preconditions=(
                _json_string_list(
                    data[
                        "preconditions"
                    ],
                    field_name="preconditions",
                )
            ),
            expected_outcomes=(
                expected_outcomes
            ),
            failure_modes=(
                _json_string_list(
                    data[
                        "failure_modes"
                    ],
                    field_name="failure_modes",
                )
            ),
            verification_requirements=(
                skill_requirements
            ),
            reversible=(
                experience.reversible
            ),
            provenance=(
                "raphael-1h-model-proposal:"
                + _evidence_digest(
                    experience
                )[:16]
            ),
        )

        # Ephemeral validation only. This does not mutate any caller registry.
        SkillRegistry(
            self._capability_registry,
            (
                skill,
            ),
        )

        remaining_uncertainties = (
            _json_string_list(
                data[
                    "remaining_uncertainties"
                ],
                field_name="remaining_uncertainties",
            )
        )

        return (
            skill,
            remaining_uncertainties,
        )

    def synthesize(
        self,
        experience: VerifiedExperience,
    ) -> SkillSynthesisProposal:
        if not isinstance(
            experience,
            VerifiedExperience,
        ):
            raise TypeError(
                "experience must be VerifiedExperience."
            )

        if (
            experience.authority
            != SKILL_SYNTHESIS_AUTHORITY_NONE
        ):
            return self._reject(
                experience,
                "VerifiedExperience authority must remain NONE.",
                sufficient=False,
                disposition=(
                    SkillSynthesisDisposition.INSUFFICIENT
                ),
            )

        if any(
            step.authority
            != SKILL_SYNTHESIS_AUTHORITY_NONE
            for step
            in experience.steps
        ):
            return self._reject(
                experience,
                "VerifiedExperienceStep authority must remain NONE.",
                sufficient=False,
                disposition=(
                    SkillSynthesisDisposition.INSUFFICIENT
                ),
            )

        if experience.remaining_uncertainties:
            return self._reject(
                experience,
                "Verified experience retains unresolved uncertainty; "
                "skill synthesis fails closed.",
                sufficient=False,
                disposition=(
                    SkillSynthesisDisposition.INSUFFICIENT
                ),
            )

        capability_error = (
            self._validate_experience_capabilities(
                experience
            )
        )

        if capability_error:
            return self._reject(
                experience,
                capability_error,
                sufficient=False,
                disposition=(
                    SkillSynthesisDisposition.INSUFFICIENT
                ),
            )

        capability_names = tuple(
            sorted(
                self._capability_registry.names()
            )
        )

        messages = self._messages(
            experience,
            capability_names=(
                capability_names
            ),
        )

        try:
            response = self._model_call(
                messages
            )
        except Exception as error:
            return self._reject(
                experience,
                "Skill synthesis model call failed: "
                f"{error}",
                sufficient=True,
            )

        try:
            skill, uncertainties = (
                self._parse_candidate(
                    experience=experience,
                    response=response,
                )
            )
        except (
            TypeError,
            ValueError,
            KeyError,
        ) as error:
            return self._reject(
                experience,
                "Skill synthesis proposal failed validation: "
                f"{error}",
                sufficient=True,
            )

        return SkillSynthesisProposal(
            disposition=(
                SkillSynthesisDisposition.PROPOSED
            ),
            reason=(
                "A zero-authority SkillDefinition proposal was derived "
                "from bounded verified experience and survived exact schema, "
                "evidence-binding, and canonical capability validation. "
                "It remains unregistered and grants no execution authority."
            ),
            evidence_digest=(
                _evidence_digest(
                    experience
                )
            ),
            evidence_step_ids=(
                experience.step_ids
            ),
            evidence_sufficient=True,
            remaining_uncertainties=(
                uncertainties
            ),
            skill=skill,
        )
