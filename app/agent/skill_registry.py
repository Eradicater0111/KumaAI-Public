"""
KUMA RAPHAEL-1G zero-authority skill contracts and registry.

A Capability describes a semantic ability already known to KUMA.
A SkillDefinition describes reusable tactical procedure knowledge composed from
those capability names.

This module deliberately does NOT:
- register runtime tools;
- choose tools;
- classify permissions;
- authorize actions;
- execute actions;
- call models, providers, sensors, memory, or the network;
- persist skills;
- generate or modify Python code;
- synthesize new skills.

RAPHAEL-1H may later propose new immutable SkillDefinition values, but this
registry remains a structural and capability-validating knowledge layer only.

Critical invariants:
- SKILL != TOOL
- SKILL != EXECUTABLE CODE
- SKILL != PERMISSION
- SKILL != AUTHORIZATION
- SKILL REGISTRATION != TOOL REGISTRATION
- SKILL MATCH != TACTICAL DECISION
- SKILL DEFINITION != DYNAMIC SYNTHESIS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.agent.capability_registry import (
    CapabilityRegistry,
)
from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
)


SKILL_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_TEXT_CHARS = 800
_MAX_ITEMS = 64
_MAX_PHASES = 24


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

    if len(raw) > limit:
        raise ValueError(
            f"{field_name} exceeds the bounded item limit."
        )

    result = []
    seen = set()

    for item in raw:
        text = _text(
            item,
            field_name=field_name,
        )

        if text in seen:
            continue

        seen.add(
            text
        )
        result.append(
            text
        )

    return tuple(
        result
    )


@dataclass(
    frozen=True,
    slots=True,
)
class SkillPhase:
    """
    Immutable reusable phase template.

    This intentionally reuses GoalStep's structural ideas -- objective,
    dependencies, success criteria, required semantic capabilities, and
    verification requirements -- without reusing GoalStep itself.

    GoalStep is mutable mission execution state and can contain planned tools
    and runtime GUI authority metadata. SkillPhase contains none of those.
    """

    phase_id: str
    objective: str
    dependencies: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    verification_requirements: tuple[str, ...] = ()
    authority: str = field(
        default=SKILL_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "phase_id",
            _text(
                self.phase_id,
                field_name="phase_id",
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
            "dependencies",
            "required_capabilities",
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
                ),
            )

        if not self.success_criteria:
            raise ValueError(
                "SkillPhase requires at least one success criterion."
            )

        if not self.verification_requirements:
            raise ValueError(
                "SkillPhase requires at least one verification requirement."
            )

        if (
            self.phase_id
            in self.dependencies
        ):
            raise ValueError(
                "SkillPhase cannot depend on itself."
            )


def _validate_phase_graph(
    phases: tuple[
        SkillPhase,
        ...,
    ],
) -> None:
    ids = tuple(
        phase.phase_id
        for phase
        in phases
    )

    if len(
        ids
    ) != len(
        set(
            ids
        )
    ):
        raise ValueError(
            "SkillDefinition phase IDs must be unique."
        )

    id_set = set(
        ids
    )

    for phase in phases:
        unknown = tuple(
            dependency
            for dependency
            in phase.dependencies
            if dependency
            not in id_set
        )

        if unknown:
            raise ValueError(
                "SkillPhase references unknown dependency: "
                + ", ".join(
                    unknown
                )
            )

    dependencies = {
        phase.phase_id: set(
            phase.dependencies
        )
        for phase
        in phases
    }

    resolved = set()

    while len(
        resolved
    ) < len(
        phases
    ):
        ready = tuple(
            phase_id
            for phase_id, required
            in dependencies.items()
            if (
                phase_id
                not in resolved
                and required.issubset(
                    resolved
                )
            )
        )

        if not ready:
            raise ValueError(
                "SkillDefinition phase dependencies contain a cycle."
            )

        resolved.update(
            ready
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SkillDefinition:
    """
    Immutable zero-authority reusable tactical procedure.

    required_capabilities contains canonical semantic capability names only.
    It intentionally contains no tool names, tool arguments, permission class,
    runtime authority, generated code, or executable callback.

    provenance is descriptive metadata only and grants no trust or authority.
    reversible is also descriptive procedure metadata; downstream tactical
    option generation must still derive concrete option risk/reversibility.
    """

    skill_id: str
    description: str
    phases: tuple[SkillPhase, ...]
    required_capabilities: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    expected_outcomes: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    verification_requirements: tuple[str, ...] = ()
    reversible: bool = True
    provenance: str = "static"
    authority: str = field(
        default=SKILL_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "skill_id",
            _text(
                self.skill_id,
                field_name="skill_id",
            ),
        )

        object.__setattr__(
            self,
            "description",
            _text(
                self.description,
                field_name="description",
            ),
        )

        if isinstance(
            self.phases,
            (
                str,
                bytes,
            ),
        ):
            raise TypeError(
                "phases must be an iterable of SkillPhase values."
            )

        try:
            phases = tuple(
                self.phases
            )
        except TypeError as error:
            raise TypeError(
                "phases must be iterable."
            ) from error

        if not phases:
            raise ValueError(
                "SkillDefinition requires at least one phase."
            )

        if len(
            phases
        ) > _MAX_PHASES:
            raise ValueError(
                "SkillDefinition exceeds the bounded phase limit."
            )

        for phase in phases:
            if not isinstance(
                phase,
                SkillPhase,
            ):
                raise TypeError(
                    "phases must contain SkillPhase values."
                )

            if (
                phase.authority
                != SKILL_AUTHORITY_NONE
            ):
                raise ValueError(
                    "SkillPhase authority must remain NONE."
                )

        _validate_phase_graph(
            phases
        )

        object.__setattr__(
            self,
            "phases",
            phases,
        )

        for field_name in (
            "required_capabilities",
            "preconditions",
            "expected_outcomes",
            "failure_modes",
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
                ),
            )

        if not self.expected_outcomes:
            raise ValueError(
                "SkillDefinition requires at least one expected outcome."
            )

        if not self.verification_requirements:
            raise ValueError(
                "SkillDefinition requires at least one verification requirement."
            )

        if type(
            self.reversible
        ) is not bool:
            raise TypeError(
                "reversible must be bool."
            )

        object.__setattr__(
            self,
            "provenance",
            _text(
                self.provenance,
                field_name="provenance",
            ),
        )

        declared = set(
            self.required_capabilities
        )

        for phase in phases:
            undeclared = tuple(
                capability
                for capability
                in phase.required_capabilities
                if capability
                not in declared
            )

            if undeclared:
                raise ValueError(
                    "SkillPhase uses capability not declared by "
                    "SkillDefinition: "
                    + ", ".join(
                        undeclared
                    )
                )

    @property
    def phase_ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            phase.phase_id
            for phase
            in self.phases
        )

    def get_phase(
        self,
        phase_id: str,
    ) -> SkillPhase | None:
        normalized = _text(
            phase_id,
            field_name="phase_id",
        )

        for phase in self.phases:
            if (
                phase.phase_id
                == normalized
            ):
                return phase

        return None


@dataclass(
    frozen=True,
    slots=True,
)
class SkillMatch:
    """
    Capability-eligibility result only.

    eligible=True means only that the caller-supplied available semantic
    capabilities cover the skill's declared requirements.
    It is not a tactical decision, permission, authorization, or execution.
    """

    skill: SkillDefinition
    eligible: bool
    missing_capabilities: tuple[str, ...] = ()
    authority: str = field(
        default=SKILL_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.skill,
            SkillDefinition,
        ):
            raise TypeError(
                "skill must be SkillDefinition."
            )

        if type(
            self.eligible
        ) is not bool:
            raise TypeError(
                "eligible must be bool."
            )

        object.__setattr__(
            self,
            "missing_capabilities",
            _text_tuple(
                self.missing_capabilities,
                field_name="missing_capabilities",
            ),
        )

        expected = bool(
            not self.missing_capabilities
        )

        if (
            self.eligible
            != expected
        ):
            raise ValueError(
                "eligible must exactly reflect missing_capabilities."
            )


class SkillRegistry:
    """
    In-memory zero-authority registry for immutable SkillDefinition values.

    The supplied CapabilityRegistry remains canonical. This registry stores
    capability names, not Capability snapshots, so capability truth is always
    revalidated against the current canonical registry.

    register() changes only this in-memory knowledge index. It does not
    register tools, modify permissions, persist data, or alter KUMA runtime
    authority.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        skills: Iterable[
            SkillDefinition
        ] = (),
    ) -> None:
        if not isinstance(
            capability_registry,
            CapabilityRegistry,
        ):
            raise TypeError(
                "capability_registry must be CapabilityRegistry."
            )

        self._capability_registry = (
            capability_registry
        )

        self._skills: dict[
            str,
            SkillDefinition,
        ] = {}

        if isinstance(
            skills,
            (
                str,
                bytes,
            ),
        ):
            raise TypeError(
                "skills must be an iterable of SkillDefinition values."
            )

        try:
            initial = tuple(
                skills
            )
        except TypeError as error:
            raise TypeError(
                "skills must be iterable."
            ) from error

        for skill in initial:
            self.register(
                skill
            )

    def _known_capabilities(
        self,
    ) -> set[str]:
        return set(
            self._capability_registry.names()
        )

    def _validate_skill_capabilities(
        self,
        skill: SkillDefinition,
    ) -> None:
        known = (
            self._known_capabilities()
        )

        unknown = tuple(
            capability
            for capability
            in skill.required_capabilities
            if capability
            not in known
        )

        if unknown:
            raise ValueError(
                "SkillDefinition requires unknown capabilities: "
                + ", ".join(
                    unknown
                )
            )

        for phase in skill.phases:
            phase_unknown = tuple(
                capability
                for capability
                in phase.required_capabilities
                if capability
                not in known
            )

            if phase_unknown:
                raise ValueError(
                    "SkillPhase requires unknown capabilities: "
                    + ", ".join(
                        phase_unknown
                    )
                )

    def register(
        self,
        skill: SkillDefinition,
    ) -> None:
        if not isinstance(
            skill,
            SkillDefinition,
        ):
            raise TypeError(
                "skill must be SkillDefinition."
            )

        if (
            skill.authority
            != SKILL_AUTHORITY_NONE
        ):
            raise ValueError(
                "SkillDefinition authority must remain NONE."
            )

        if any(
            phase.authority
            != SKILL_AUTHORITY_NONE
            for phase
            in skill.phases
        ):
            raise ValueError(
                "SkillPhase authority must remain NONE."
            )

        if (
            skill.skill_id
            in self._skills
        ):
            raise ValueError(
                "SkillRegistry already contains skill_id: "
                f"{skill.skill_id!r}"
            )

        self._validate_skill_capabilities(
            skill
        )

        self._skills[
            skill.skill_id
        ] = skill

    def has(
        self,
        skill_id: str,
    ) -> bool:
        normalized = _text(
            skill_id,
            field_name="skill_id",
        )

        return (
            normalized
            in self._skills
        )

    def get(
        self,
        skill_id: str,
    ) -> SkillDefinition | None:
        normalized = _text(
            skill_id,
            field_name="skill_id",
        )

        return self._skills.get(
            normalized
        )

    def ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                self._skills
            )
        )

    def all(
        self,
    ) -> tuple[
        SkillDefinition,
        ...,
    ]:
        return tuple(
            self._skills[
                skill_id
            ]
            for skill_id
            in self.ids()
        )

    def assess(
        self,
        skill_id: str,
        *,
        available_capabilities: Iterable[str],
    ) -> SkillMatch:
        skill = self.get(
            skill_id
        )

        if skill is None:
            raise KeyError(
                f"Unknown skill_id: {skill_id!r}"
            )

        available = _text_tuple(
            available_capabilities,
            field_name="available_capabilities",
        )

        known = (
            self._known_capabilities()
        )

        unknown_available = tuple(
            capability
            for capability
            in available
            if capability
            not in known
        )

        if unknown_available:
            raise ValueError(
                "available_capabilities contains unknown capability names: "
                + ", ".join(
                    unknown_available
                )
            )

        available_set = set(
            available
        )

        missing = tuple(
            capability
            for capability
            in skill.required_capabilities
            if capability
            not in available_set
        )

        return SkillMatch(
            skill=skill,
            eligible=(
                not missing
            ),
            missing_capabilities=missing,
        )

    def matching(
        self,
        *,
        available_capabilities: Iterable[str],
    ) -> tuple[
        SkillDefinition,
        ...,
    ]:
        available = _text_tuple(
            available_capabilities,
            field_name="available_capabilities",
        )

        known = (
            self._known_capabilities()
        )

        unknown_available = tuple(
            capability
            for capability
            in available
            if capability
            not in known
        )

        if unknown_available:
            raise ValueError(
                "available_capabilities contains unknown capability names: "
                + ", ".join(
                    unknown_available
                )
            )

        available_set = set(
            available
        )

        return tuple(
            skill
            for skill
            in self.all()
            if set(
                skill.required_capabilities
            ).issubset(
                available_set
            )
        )
