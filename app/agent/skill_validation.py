"""
KUMA RAPHAEL-1I symbolic skill sandbox validation and bounded evolution review.

RAPHAEL skills are capability-level procedure knowledge, not executable code.
Therefore 1I deliberately does NOT reuse KUMA's native repair-execution sandbox:
that sandbox exists to contain Python/code candidates, while a SkillDefinition
contains no executable payload.

Instead, this module provides a pure symbolic sandbox. It evaluates one
RAPHAEL-1H SkillSynthesisProposal against immutable caller-supplied scenarios:
- verified-source replay fixtures bound to the proposal's evidence digest; and
- synthetic fixtures used to probe capability/precondition/evidence coverage.

No real tool is called. No model is called. No subprocess is launched. No
permission is granted. No SkillRegistry supplied by a caller is mutated.

The optional evolution reviewer accepts an externally proposed evolved
SkillDefinition and permits only conservative, non-expansive changes. Passing
review produces another zero-authority proposal only.

Critical invariants:
- VALIDATED != AUTHORIZED
- VALIDATED != REGISTERED
- HIGH COVERAGE != PERMISSION
- EVOLVED != INSTALLED
- SYMBOLIC SANDBOX != REAL TOOL EXECUTION
- SYNTHETIC SCENARIO != VERIFIED REALITY
- VALIDATION EVIDENCE != EXECUTION EVIDENCE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Iterable

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
from app.agent.skill_synthesis import (
    SkillSynthesisDisposition,
    SkillSynthesisProposal,
)


SKILL_VALIDATION_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_TEXT_CHARS = 1200
_MAX_ITEMS = 96
_MAX_SCENARIOS = 32


class SkillScenarioKind(str, Enum):
    VERIFIED_REPLAY = "verified_replay"
    SYNTHETIC = "synthetic"


class SkillScenarioDisposition(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class SkillValidationDisposition(str, Enum):
    VALIDATED = "validated"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class SkillEvolutionDisposition(str, Enum):
    NO_CHANGE = "no_change"
    PROPOSED = "proposed"
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


def _sha256_hex(
    value: str,
) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(
            character
            in "0123456789abcdef"
            for character
            in value
        )
    )


def _digest_payload(
    payload,
) -> str:
    encoded = json.dumps(
        payload,
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


def _skill_payload(
    skill: SkillDefinition,
) -> dict:
    return {
        "skill_id": skill.skill_id,
        "description": skill.description,
        "required_capabilities": list(
            skill.required_capabilities
        ),
        "preconditions": list(
            skill.preconditions
        ),
        "expected_outcomes": list(
            skill.expected_outcomes
        ),
        "failure_modes": list(
            skill.failure_modes
        ),
        "verification_requirements": list(
            skill.verification_requirements
        ),
        "reversible": skill.reversible,
        "provenance": skill.provenance,
        "authority": skill.authority,
        "phases": [
            {
                "phase_id": phase.phase_id,
                "objective": phase.objective,
                "dependencies": list(
                    phase.dependencies
                ),
                "required_capabilities": list(
                    phase.required_capabilities
                ),
                "success_criteria": list(
                    phase.success_criteria
                ),
                "verification_requirements": list(
                    phase.verification_requirements
                ),
                "authority": phase.authority,
            }
            for phase
            in skill.phases
        ],
    }


def skill_definition_digest(
    skill: SkillDefinition,
) -> str:
    if not isinstance(
        skill,
        SkillDefinition,
    ):
        raise TypeError(
            "skill must be SkillDefinition."
        )

    return _digest_payload(
        _skill_payload(
            skill
        )
    )


@dataclass(
    frozen=True,
    slots=True,
)
class SkillValidationScenario:
    """
    Immutable symbolic sandbox fixture.

    VERIFIED_REPLAY is bound to one RAPHAEL-1H evidence digest. It represents a
    read-only replay description of already-verified source experience.

    SYNTHETIC is explicitly hypothetical. It may probe coverage/generalization
    but never becomes verified real-world evidence.

    context_constraints are descriptive conditions that may later support a
    *more restrictive* evolved proposal. They grant no authority.
    """

    scenario_id: str
    kind: SkillScenarioKind
    available_capabilities: tuple[str, ...]
    satisfied_preconditions: tuple[str, ...]
    observed_success_criteria: tuple[str, ...]
    satisfied_verification_requirements: tuple[str, ...]
    observed_outcomes: tuple[str, ...]
    context_constraints: tuple[str, ...] = ()
    source_evidence_digest: str = ""
    authority: str = field(
        default=SKILL_VALIDATION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "scenario_id",
            _text(
                self.scenario_id,
                field_name="scenario_id",
            ),
        )

        if not isinstance(
            self.kind,
            SkillScenarioKind,
        ):
            raise TypeError(
                "kind must be SkillScenarioKind."
            )

        for field_name in (
            "available_capabilities",
            "satisfied_preconditions",
            "observed_success_criteria",
            "satisfied_verification_requirements",
            "observed_outcomes",
            "context_constraints",
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

        if (
            not self.observed_success_criteria
            or not self.satisfied_verification_requirements
            or not self.observed_outcomes
        ):
            raise ValueError(
                "SkillValidationScenario requires success, verification, "
                "and outcome observations."
            )

        if (
            self.kind
            == SkillScenarioKind.VERIFIED_REPLAY
        ):
            if not _sha256_hex(
                self.source_evidence_digest
            ):
                raise ValueError(
                    "VERIFIED_REPLAY requires a lowercase SHA-256 "
                    "source_evidence_digest."
                )

        elif self.source_evidence_digest:
            raise ValueError(
                "SYNTHETIC scenarios cannot claim a verified source digest."
            )


def _scenario_payload(
    scenario: SkillValidationScenario,
) -> dict:
    return {
        "scenario_id": scenario.scenario_id,
        "kind": scenario.kind.value,
        "available_capabilities": list(
            scenario.available_capabilities
        ),
        "satisfied_preconditions": list(
            scenario.satisfied_preconditions
        ),
        "observed_success_criteria": list(
            scenario.observed_success_criteria
        ),
        "satisfied_verification_requirements": list(
            scenario.satisfied_verification_requirements
        ),
        "observed_outcomes": list(
            scenario.observed_outcomes
        ),
        "context_constraints": list(
            scenario.context_constraints
        ),
        "source_evidence_digest": (
            scenario.source_evidence_digest
        ),
        "authority": scenario.authority,
    }


@dataclass(
    frozen=True,
    slots=True,
)
class SkillScenarioEvidence:
    """
    Pure symbolic comparison result for one scenario.

    PASSED means only that the SkillDefinition's declared contract is covered
    by this fixture. It is not execution evidence and does not prove that any
    real tool or real-world objective will succeed.
    """

    scenario_id: str
    kind: SkillScenarioKind
    disposition: SkillScenarioDisposition
    missing_capabilities: tuple[str, ...] = ()
    unmet_preconditions: tuple[str, ...] = ()
    missing_success_criteria: tuple[str, ...] = ()
    missing_verification_requirements: tuple[str, ...] = ()
    missing_expected_outcomes: tuple[str, ...] = ()
    authority: str = field(
        default=SKILL_VALIDATION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "scenario_id",
            _text(
                self.scenario_id,
                field_name="scenario_id",
            ),
        )

        if not isinstance(
            self.kind,
            SkillScenarioKind,
        ):
            raise TypeError(
                "kind must be SkillScenarioKind."
            )

        if not isinstance(
            self.disposition,
            SkillScenarioDisposition,
        ):
            raise TypeError(
                "disposition must be SkillScenarioDisposition."
            )

        for field_name in (
            "missing_capabilities",
            "unmet_preconditions",
            "missing_success_criteria",
            "missing_verification_requirements",
            "missing_expected_outcomes",
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

        has_failure = any(
            (
                self.missing_capabilities,
                self.unmet_preconditions,
                self.missing_success_criteria,
                self.missing_verification_requirements,
                self.missing_expected_outcomes,
            )
        )

        if (
            self.disposition
            == SkillScenarioDisposition.PASSED
            and has_failure
        ):
            raise ValueError(
                "PASSED scenario evidence cannot contain failures."
            )

        if (
            self.disposition
            == SkillScenarioDisposition.FAILED
            and not has_failure
        ):
            raise ValueError(
                "FAILED scenario evidence requires at least one failure."
            )

    @property
    def passed(
        self,
    ) -> bool:
        return (
            self.disposition
            == SkillScenarioDisposition.PASSED
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SkillValidationEvidence:
    """
    Immutable zero-authority evidence from symbolic validation.

    VALIDATED requires:
    - the proposal remained bound to its original SkillDefinition;
    - every supplied scenario passed; and
    - coverage includes at least one verified replay plus one synthetic probe.

    Even VALIDATED does not authorize registration or execution.
    """

    disposition: SkillValidationDisposition
    reason: str
    proposal_evidence_digest: str
    skill_digest: str
    scenario_digest: str
    validation_digest: str
    scenario_results: tuple[
        SkillScenarioEvidence,
        ...,
    ]
    replay_covered: bool
    synthetic_covered: bool
    evolution_constraints: tuple[str, ...] = ()
    failure_observations: tuple[str, ...] = ()
    authority: str = field(
        default=SKILL_VALIDATION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.disposition,
            SkillValidationDisposition,
        ):
            raise TypeError(
                "disposition must be SkillValidationDisposition."
            )

        object.__setattr__(
            self,
            "reason",
            _text(
                self.reason,
                field_name="reason",
            ),
        )

        for field_name in (
            "proposal_evidence_digest",
            "skill_digest",
            "scenario_digest",
            "validation_digest",
        ):
            if not _sha256_hex(
                getattr(
                    self,
                    field_name,
                )
            ):
                raise ValueError(
                    f"{field_name} must be a lowercase SHA-256 hex digest."
                )

        if isinstance(
            self.scenario_results,
            (
                str,
                bytes,
            ),
        ):
            raise TypeError(
                "scenario_results must be an iterable of SkillScenarioEvidence."
            )

        try:
            results = tuple(
                self.scenario_results
            )
        except TypeError as error:
            raise TypeError(
                "scenario_results must be iterable."
            ) from error

        if not results:
            raise ValueError(
                "SkillValidationEvidence requires scenario results."
            )

        for result in results:
            if not isinstance(
                result,
                SkillScenarioEvidence,
            ):
                raise TypeError(
                    "scenario_results must contain SkillScenarioEvidence."
                )

            if (
                result.authority
                != SKILL_VALIDATION_AUTHORITY_NONE
            ):
                raise ValueError(
                    "Scenario evidence authority must remain NONE."
                )

        object.__setattr__(
            self,
            "scenario_results",
            results,
        )

        for field_name in (
            "replay_covered",
            "synthetic_covered",
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

        for field_name in (
            "evolution_constraints",
            "failure_observations",
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

        all_passed = all(
            result.passed
            for result
            in results
        )

        if (
            self.disposition
            == SkillValidationDisposition.VALIDATED
        ):
            if not all_passed:
                raise ValueError(
                    "VALIDATED requires every scenario to pass."
                )

            if (
                not self.replay_covered
                or not self.synthetic_covered
            ):
                raise ValueError(
                    "VALIDATED requires replay and synthetic coverage."
                )

        if (
            self.disposition
            == SkillValidationDisposition.REJECTED
            and all_passed
        ):
            raise ValueError(
                "REJECTED requires at least one failed scenario."
            )

        if (
            self.disposition
            == SkillValidationDisposition.INCONCLUSIVE
            and (
                not all_passed
                or (
                    self.replay_covered
                    and self.synthetic_covered
                )
            )
        ):
            raise ValueError(
                "INCONCLUSIVE is reserved for passing but incomplete "
                "scenario-kind coverage."
            )

    @property
    def all_passed(
        self,
    ) -> bool:
        return all(
            result.passed
            for result
            in self.scenario_results
        )


def _result_payload(
    result: SkillScenarioEvidence,
) -> dict:
    return {
        "scenario_id": result.scenario_id,
        "kind": result.kind.value,
        "disposition": result.disposition.value,
        "missing_capabilities": list(
            result.missing_capabilities
        ),
        "unmet_preconditions": list(
            result.unmet_preconditions
        ),
        "missing_success_criteria": list(
            result.missing_success_criteria
        ),
        "missing_verification_requirements": list(
            result.missing_verification_requirements
        ),
        "missing_expected_outcomes": list(
            result.missing_expected_outcomes
        ),
        "authority": result.authority,
    }


class SkillSandboxValidator:
    """
    Pure symbolic sandbox for RAPHAEL skill proposals.

    This class performs comparisons only. It does not:
    - execute a skill phase;
    - call a tool or model;
    - emulate a tool;
    - import the native repair sandbox;
    - create a subprocess/workspace;
    - mutate a SkillRegistry;
    - persist validation evidence.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
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

    def _validate_proposal(
        self,
        proposal: SkillSynthesisProposal,
    ) -> SkillDefinition:
        if not isinstance(
            proposal,
            SkillSynthesisProposal,
        ):
            raise TypeError(
                "proposal must be SkillSynthesisProposal."
            )

        if (
            proposal.authority
            != SKILL_VALIDATION_AUTHORITY_NONE
        ):
            raise ValueError(
                "SkillSynthesisProposal authority must remain NONE."
            )

        if (
            proposal.disposition
            != SkillSynthesisDisposition.PROPOSED
            or proposal.skill is None
        ):
            raise ValueError(
                "Symbolic validation requires a PROPOSED skill."
            )

        skill = proposal.skill

        if (
            skill.authority
            != SKILL_VALIDATION_AUTHORITY_NONE
        ):
            raise ValueError(
                "SkillDefinition authority must remain NONE."
            )

        if any(
            phase.authority
            != SKILL_VALIDATION_AUTHORITY_NONE
            for phase
            in skill.phases
        ):
            raise ValueError(
                "SkillPhase authority must remain NONE."
            )

        # Ephemeral 1G validation only. No caller registry is mutated.
        SkillRegistry(
            self._capability_registry,
            (
                skill,
            ),
        )

        return skill

    def validate(
        self,
        proposal: SkillSynthesisProposal,
        scenarios: Iterable[
            SkillValidationScenario
        ],
    ) -> SkillValidationEvidence:
        skill = self._validate_proposal(
            proposal
        )

        if isinstance(
            scenarios,
            (
                str,
                bytes,
            ),
        ):
            raise TypeError(
                "scenarios must be an iterable of SkillValidationScenario."
            )

        try:
            scenario_tuple = tuple(
                scenarios
            )
        except TypeError as error:
            raise TypeError(
                "scenarios must be iterable."
            ) from error

        if not scenario_tuple:
            raise ValueError(
                "Symbolic skill validation requires at least one scenario."
            )

        if len(
            scenario_tuple
        ) > _MAX_SCENARIOS:
            raise ValueError(
                "Symbolic skill validation exceeds the bounded scenario limit."
            )

        ids = []

        for scenario in scenario_tuple:
            if not isinstance(
                scenario,
                SkillValidationScenario,
            ):
                raise TypeError(
                    "scenarios must contain SkillValidationScenario values."
                )

            if (
                scenario.authority
                != SKILL_VALIDATION_AUTHORITY_NONE
            ):
                raise ValueError(
                    "SkillValidationScenario authority must remain NONE."
                )

            ids.append(
                scenario.scenario_id
            )

        if len(
            ids
        ) != len(
            set(
                ids
            )
        ):
            raise ValueError(
                "Skill validation scenario IDs must be unique."
            )

        known_capabilities = set(
            self._capability_registry.names()
        )

        results = []
        evolution_constraints = []
        failure_observations = []

        replay_covered = False
        synthetic_covered = False

        skill_criteria = tuple(
            criterion
            for phase
            in skill.phases
            for criterion
            in phase.success_criteria
        )

        skill_verification = tuple(
            dict.fromkeys(
                (
                    *skill.verification_requirements,
                    *(
                        requirement
                        for phase
                        in skill.phases
                        for requirement
                        in phase.verification_requirements
                    ),
                )
            )
        )

        for scenario in scenario_tuple:
            if (
                scenario.kind
                == SkillScenarioKind.VERIFIED_REPLAY
            ):
                replay_covered = True

                if (
                    scenario.source_evidence_digest
                    != proposal.evidence_digest
                ):
                    raise ValueError(
                        "VERIFIED_REPLAY source_evidence_digest does not "
                        "match the SkillSynthesisProposal evidence digest."
                    )

            else:
                synthetic_covered = True

            unknown_available = tuple(
                capability
                for capability
                in scenario.available_capabilities
                if capability
                not in known_capabilities
            )

            if unknown_available:
                raise ValueError(
                    "Scenario contains capability names absent from the "
                    "canonical CapabilityRegistry: "
                    + ", ".join(
                        unknown_available
                    )
                )

            available = set(
                scenario.available_capabilities
            )

            satisfied_preconditions = set(
                scenario.satisfied_preconditions
            )

            observed_criteria = set(
                scenario.observed_success_criteria
            )

            satisfied_verification = set(
                scenario.satisfied_verification_requirements
            )

            observed_outcomes = set(
                scenario.observed_outcomes
            )

            missing_capabilities = tuple(
                capability
                for capability
                in skill.required_capabilities
                if capability
                not in available
            )

            unmet_preconditions = tuple(
                precondition
                for precondition
                in skill.preconditions
                if precondition
                not in satisfied_preconditions
            )

            missing_success_criteria = tuple(
                criterion
                for criterion
                in skill_criteria
                if criterion
                not in observed_criteria
            )

            missing_verification_requirements = tuple(
                requirement
                for requirement
                in skill_verification
                if requirement
                not in satisfied_verification
            )

            missing_expected_outcomes = tuple(
                outcome
                for outcome
                in skill.expected_outcomes
                if outcome
                not in observed_outcomes
            )

            failed = any(
                (
                    missing_capabilities,
                    unmet_preconditions,
                    missing_success_criteria,
                    missing_verification_requirements,
                    missing_expected_outcomes,
                )
            )

            result = SkillScenarioEvidence(
                scenario_id=scenario.scenario_id,
                kind=scenario.kind,
                disposition=(
                    SkillScenarioDisposition.FAILED
                    if failed
                    else SkillScenarioDisposition.PASSED
                ),
                missing_capabilities=(
                    missing_capabilities
                ),
                unmet_preconditions=(
                    unmet_preconditions
                ),
                missing_success_criteria=(
                    missing_success_criteria
                ),
                missing_verification_requirements=(
                    missing_verification_requirements
                ),
                missing_expected_outcomes=(
                    missing_expected_outcomes
                ),
            )

            results.append(
                result
            )

            for constraint in scenario.context_constraints:
                if constraint not in evolution_constraints:
                    evolution_constraints.append(
                        constraint
                    )

            for capability in missing_capabilities:
                failure_observations.append(
                    "Scenario "
                    f"'{scenario.scenario_id}' lacked required "
                    f"capability '{capability}'."
                )

            for precondition in unmet_preconditions:
                failure_observations.append(
                    "Scenario "
                    f"'{scenario.scenario_id}' did not satisfy "
                    f"precondition '{precondition}'."
                )

            for criterion in missing_success_criteria:
                failure_observations.append(
                    "Scenario "
                    f"'{scenario.scenario_id}' did not provide "
                    f"success criterion '{criterion}'."
                )

            for requirement in missing_verification_requirements:
                failure_observations.append(
                    "Scenario "
                    f"'{scenario.scenario_id}' did not provide "
                    f"verification requirement '{requirement}'."
                )

            for outcome in missing_expected_outcomes:
                failure_observations.append(
                    "Scenario "
                    f"'{scenario.scenario_id}' did not provide "
                    f"expected outcome '{outcome}'."
                )

        result_tuple = tuple(
            results
        )

        all_passed = all(
            result.passed
            for result
            in result_tuple
        )

        if not all_passed:
            disposition = (
                SkillValidationDisposition.REJECTED
            )

            reason = (
                "One or more symbolic sandbox scenarios did not cover the "
                "skill contract. This is validation evidence only and grants "
                "no execution or registration authority."
            )

        elif (
            replay_covered
            and synthetic_covered
        ):
            disposition = (
                SkillValidationDisposition.VALIDATED
            )

            reason = (
                "All symbolic sandbox scenarios covered the skill contract "
                "with both verified-replay and synthetic probes. VALIDATED "
                "does not authorize registration or execution."
            )

        else:
            disposition = (
                SkillValidationDisposition.INCONCLUSIVE
            )

            reason = (
                "All supplied symbolic scenarios passed, but validation lacks "
                "both verified-replay and synthetic coverage. No registration "
                "or execution authority is created."
            )

        scenario_payloads = [
            _scenario_payload(
                scenario
            )
            for scenario
            in scenario_tuple
        ]

        scenario_digest = (
            _digest_payload(
                scenario_payloads
            )
        )

        skill_digest = (
            skill_definition_digest(
                skill
            )
        )

        deduplicated_failures = tuple(
            dict.fromkeys(
                failure_observations
            )
        )

        validation_payload = {
            "disposition": disposition.value,
            "proposal_evidence_digest": (
                proposal.evidence_digest
            ),
            "skill_digest": skill_digest,
            "scenario_digest": scenario_digest,
            "scenario_results": [
                _result_payload(
                    result
                )
                for result
                in result_tuple
            ],
            "replay_covered": replay_covered,
            "synthetic_covered": synthetic_covered,
            "evolution_constraints": (
                evolution_constraints
            ),
            "failure_observations": list(
                deduplicated_failures
            ),
        }

        validation_digest = (
            _digest_payload(
                validation_payload
            )
        )

        return SkillValidationEvidence(
            disposition=disposition,
            reason=reason,
            proposal_evidence_digest=(
                proposal.evidence_digest
            ),
            skill_digest=skill_digest,
            scenario_digest=scenario_digest,
            validation_digest=(
                validation_digest
            ),
            scenario_results=(
                result_tuple
            ),
            replay_covered=replay_covered,
            synthetic_covered=synthetic_covered,
            evolution_constraints=tuple(
                evolution_constraints
            ),
            failure_observations=(
                deduplicated_failures
            ),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SkillEvolutionProposal:
    """
    Zero-authority result of conservative evolution review.

    PROPOSED means only that an externally supplied evolved SkillDefinition is
    structurally valid, bound to current validation evidence, and does not
    expand the original skill's capability/outcome/verification authority.

    Nothing is installed or registered automatically.
    """

    disposition: SkillEvolutionDisposition
    reason: str
    original_skill_digest: str
    validation_digest: str
    evolved_skill: SkillDefinition | None = None
    authority: str = field(
        default=SKILL_VALIDATION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.disposition,
            SkillEvolutionDisposition,
        ):
            raise TypeError(
                "disposition must be SkillEvolutionDisposition."
            )

        object.__setattr__(
            self,
            "reason",
            _text(
                self.reason,
                field_name="reason",
            ),
        )

        for field_name in (
            "original_skill_digest",
            "validation_digest",
        ):
            if not _sha256_hex(
                getattr(
                    self,
                    field_name,
                )
            ):
                raise ValueError(
                    f"{field_name} must be a lowercase SHA-256 hex digest."
                )

        if (
            self.disposition
            == SkillEvolutionDisposition.PROPOSED
        ):
            if not isinstance(
                self.evolved_skill,
                SkillDefinition,
            ):
                raise ValueError(
                    "PROPOSED evolution requires a SkillDefinition."
                )

            if (
                self.evolved_skill.authority
                != SKILL_VALIDATION_AUTHORITY_NONE
            ):
                raise ValueError(
                    "Evolved SkillDefinition authority must remain NONE."
                )

        elif self.evolved_skill is not None:
            raise ValueError(
                "Only PROPOSED evolution may carry an evolved skill."
            )


class SkillEvolutionReviewer:
    """
    Conservative review gate for externally proposed skill evolution.

    This reviewer does not generate a new skill. It accepts an untrusted
    candidate and permits only non-expansive changes:
    - same skill ID and same phase IDs/order;
    - no new semantic capabilities;
    - no new success criteria, verification claims, or expected outcomes;
    - existing dependencies may not be removed;
    - irreversible may never be upgraded to reversible;
    - new preconditions must come from scenario context constraints;
    - new failure modes must come from deterministic validation observations.

    A passing review is still only a proposal.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
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

    def _rejected(
        self,
        *,
        original_digest: str,
        validation: SkillValidationEvidence,
        reason: str,
    ) -> SkillEvolutionProposal:
        return SkillEvolutionProposal(
            disposition=(
                SkillEvolutionDisposition.REJECTED
            ),
            reason=reason,
            original_skill_digest=(
                original_digest
            ),
            validation_digest=(
                validation.validation_digest
            ),
        )

    def review(
        self,
        original: SkillSynthesisProposal,
        validation: SkillValidationEvidence,
        candidate: SkillDefinition | None = None,
    ) -> SkillEvolutionProposal:
        if not isinstance(
            original,
            SkillSynthesisProposal,
        ):
            raise TypeError(
                "original must be SkillSynthesisProposal."
            )

        if not isinstance(
            validation,
            SkillValidationEvidence,
        ):
            raise TypeError(
                "validation must be SkillValidationEvidence."
            )

        if (
            original.disposition
            != SkillSynthesisDisposition.PROPOSED
            or original.skill is None
        ):
            raise ValueError(
                "Skill evolution requires an original PROPOSED skill."
            )

        original_skill = (
            original.skill
        )

        original_digest = (
            skill_definition_digest(
                original_skill
            )
        )

        if (
            original.authority
            != SKILL_VALIDATION_AUTHORITY_NONE
            or original_skill.authority
            != SKILL_VALIDATION_AUTHORITY_NONE
            or validation.authority
            != SKILL_VALIDATION_AUTHORITY_NONE
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Original proposal or validation authority no longer "
                    "remains NONE."
                ),
            )

        if (
            validation.proposal_evidence_digest
            != original.evidence_digest
            or validation.skill_digest
            != original_digest
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Validation evidence is not bound to the current original "
                    "proposal and SkillDefinition."
                ),
            )

        if candidate is None:
            if (
                validation.disposition
                == SkillValidationDisposition.VALIDATED
            ):
                return SkillEvolutionProposal(
                    disposition=(
                        SkillEvolutionDisposition.NO_CHANGE
                    ),
                    reason=(
                        "The current skill passed replay and synthetic "
                        "validation. No evolution candidate was supplied."
                    ),
                    original_skill_digest=(
                        original_digest
                    ),
                    validation_digest=(
                        validation.validation_digest
                    ),
                )

            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Validation did not fully validate the skill and no "
                    "bounded evolution candidate was supplied."
                ),
            )

        if not isinstance(
            candidate,
            SkillDefinition,
        ):
            raise TypeError(
                "candidate must be SkillDefinition or None."
            )

        if (
            validation.disposition
            == SkillValidationDisposition.VALIDATED
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "A fully validated skill cannot be silently changed by "
                    "the evolution reviewer."
                ),
            )

        if (
            candidate.authority
            != SKILL_VALIDATION_AUTHORITY_NONE
            or any(
                phase.authority
                != SKILL_VALIDATION_AUTHORITY_NONE
                for phase
                in candidate.phases
            )
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolved candidate authority must remain NONE."
                ),
            )

        try:
            SkillRegistry(
                self._capability_registry,
                (
                    candidate,
                ),
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolved candidate failed 1G validation: "
                    f"{error}"
                ),
            )

        if (
            candidate.skill_id
            != original_skill.skill_id
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolution cannot change skill_id."
                ),
            )

        if (
            candidate.phase_ids
            != original_skill.phase_ids
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolution cannot add, remove, or reorder phases."
                ),
            )

        original_capabilities = set(
            original_skill.required_capabilities
        )

        if not set(
            candidate.required_capabilities
        ).issubset(
            original_capabilities
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolution cannot add semantic capabilities."
                ),
            )

        if not set(
            candidate.expected_outcomes
        ).issubset(
            set(
                original_skill.expected_outcomes
            )
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolution cannot invent or expand expected outcomes."
                ),
            )

        if not set(
            candidate.verification_requirements
        ).issubset(
            set(
                original_skill.verification_requirements
            )
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolution cannot invent skill verification requirements."
                ),
            )

        original_preconditions = set(
            original_skill.preconditions
        )

        candidate_preconditions = set(
            candidate.preconditions
        )

        if not original_preconditions.issubset(
            candidate_preconditions
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolution cannot remove original preconditions."
                ),
            )

        new_preconditions = (
            candidate_preconditions
            - original_preconditions
        )

        if not new_preconditions.issubset(
            set(
                validation.evolution_constraints
            )
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "New evolution preconditions must come from symbolic "
                    "scenario context constraints."
                ),
            )

        original_failure_modes = set(
            original_skill.failure_modes
        )

        candidate_failure_modes = set(
            candidate.failure_modes
        )

        if not original_failure_modes.issubset(
            candidate_failure_modes
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolution cannot remove original failure modes."
                ),
            )

        new_failure_modes = (
            candidate_failure_modes
            - original_failure_modes
        )

        if not new_failure_modes.issubset(
            set(
                validation.failure_observations
            )
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "New failure modes must come from deterministic symbolic "
                    "validation observations."
                ),
            )

        if (
            original_skill.reversible is False
            and candidate.reversible is True
        ):
            return self._rejected(
                original_digest=original_digest,
                validation=validation,
                reason=(
                    "Evolution cannot upgrade an irreversible skill to "
                    "reversible."
                ),
            )

        for original_phase, candidate_phase in zip(
            original_skill.phases,
            candidate.phases,
            strict=True,
        ):
            if not set(
                candidate_phase.required_capabilities
            ).issubset(
                set(
                    original_phase.required_capabilities
                )
            ):
                return self._rejected(
                    original_digest=original_digest,
                    validation=validation,
                    reason=(
                        "Evolution cannot add phase capabilities."
                    ),
                )

            if not set(
                candidate_phase.success_criteria
            ).issubset(
                set(
                    original_phase.success_criteria
                )
            ):
                return self._rejected(
                    original_digest=original_digest,
                    validation=validation,
                    reason=(
                        "Evolution cannot invent phase success criteria."
                    ),
                )

            if not set(
                candidate_phase.verification_requirements
            ).issubset(
                set(
                    original_phase.verification_requirements
                )
            ):
                return self._rejected(
                    original_digest=original_digest,
                    validation=validation,
                    reason=(
                        "Evolution cannot invent phase verification "
                        "requirements."
                    ),
                )

            if not set(
                original_phase.dependencies
            ).issubset(
                set(
                    candidate_phase.dependencies
                )
            ):
                return self._rejected(
                    original_digest=original_digest,
                    validation=validation,
                    reason=(
                        "Evolution cannot remove original phase dependencies."
                    ),
                )

        return SkillEvolutionProposal(
            disposition=(
                SkillEvolutionDisposition.PROPOSED
            ),
            reason=(
                "The evolved SkillDefinition is structurally valid and "
                "conservatively bounded by the original proposal plus current "
                "symbolic validation evidence. It remains unregistered and "
                "grants no execution authority."
            ),
            original_skill_digest=(
                original_digest
            ),
            validation_digest=(
                validation.validation_digest
            ),
            evolved_skill=candidate,
        )
