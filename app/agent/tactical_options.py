"""
KUMA RAPHAEL-1D grounded tactical options and outcome simulation.

This module turns caller-supplied, grounded strategy seeds into immutable
TacticalOption values plus prediction-only simulation envelopes.

Safety model:
- options are proposals, never actions;
- permission values classify what later execution would require;
- confidence/cost use coarse bands rather than fake precision;
- tool identity must be currently supplied, canonically permission-classified,
  and owned by a currently available semantic capability;
- predicted outcomes never become verified facts;
- this module never selects a winning option, grants authority, calls tools,
  queries providers, or mutates KUMA state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from app.agent.capability_registry import (
    Capability,
    CapabilityRegistry,
)
from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
    TacticalOption,
    TacticalRisk,
    TacticalSituation,
)
from app.agent.permissions import (
    PermissionLevel,
    require_explicit_permission,
)


TACTICAL_OPTION_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_ITEMS = 12
_MAX_TEXT_CHARS = 800


class OptionKind(str, Enum):
    OBSERVE = "observe"
    ACT = "act"
    RECOVER = "recover"
    DEFER = "defer"


class ConfidenceBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostBand(str, Enum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_CONFIDENCE_SCORE = {
    ConfidenceBand.LOW: 0.25,
    ConfidenceBand.MEDIUM: 0.50,
    ConfidenceBand.HIGH: 0.75,
}

_COST_SCORE = {
    CostBand.MINIMAL: 0.10,
    CostBand.LOW: 0.25,
    CostBand.MEDIUM: 0.50,
    CostBand.HIGH: 0.75,
}

_RISK_ORDER = {
    TacticalRisk.LOW: 0,
    TacticalRisk.MODERATE: 1,
    TacticalRisk.HIGH: 2,
    TacticalRisk.CRITICAL: 3,
}

_PERMISSION_RISK = {
    PermissionLevel.SAFE: TacticalRisk.LOW,
    PermissionLevel.USER_AUTHORIZED: TacticalRisk.MODERATE,
    PermissionLevel.DANGEROUS: TacticalRisk.CRITICAL,
}

_CAPABILITY_RISK = {
    "low": TacticalRisk.LOW,
    "normal": TacticalRisk.LOW,
    "sensitive": TacticalRisk.HIGH,
    "high": TacticalRisk.HIGH,
    "critical": TacticalRisk.CRITICAL,
}


def _bounded_text(
    value,
    *,
    field_name: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
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

    if len(normalized) <= _MAX_TEXT_CHARS:
        return normalized

    return (
        normalized[
            : _MAX_TEXT_CHARS - 3
        ]
        + "..."
    )


def _optional_text(
    value,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    return _bounded_text(
        value,
        field_name=field_name,
    )


def _bounded_tuple(
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

    result = []
    seen = set()

    for item in raw[
        :limit
    ]:
        text = _bounded_text(
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


def _max_risk(
    *risks: TacticalRisk,
) -> TacticalRisk:
    return max(
        risks,
        key=lambda risk: (
            _RISK_ORDER[
                risk
            ]
        ),
    )


def _capability_risk(
    capability: Capability,
) -> TacticalRisk:
    level = " ".join(
        str(
            capability.risk_level
            or ""
        ).split()
    ).lower()

    try:
        return _CAPABILITY_RISK[
            level
        ]
    except KeyError as error:
        raise ValueError(
            "Capability risk metadata is unsupported; "
            "tactical risk cannot be inferred safely: "
            f"{capability.name!r} -> {level!r}"
        ) from error


def _derived_risk(
    *,
    permission: PermissionLevel,
    capability: Capability,
    reversible: bool,
) -> TacticalRisk:
    risk = _max_risk(
        _PERMISSION_RISK[
            permission
        ],
        _capability_risk(
            capability
        ),
    )

    if not reversible:
        risk = _max_risk(
            risk,
            TacticalRisk.HIGH,
        )

    return risk


@dataclass(
    frozen=True,
    slots=True,
)
class TacticalOptionSeed:
    """
    Grounded input proposal for RAPHAEL-1D.

    A seed is not executable. The caller must supply the proposed objective,
    rationale, predicted outcome, coarse confidence/cost bands, and simulation
    support. Tool arguments are intentionally absent from this contract.
    """

    option_id: str
    kind: OptionKind
    objective: str
    rationale: str
    expected_outcome: str
    confidence_band: ConfidenceBand
    reversible: bool
    tool_name: str | None = None
    capability: str | None = None
    cost_band: CostBand = CostBand.MEDIUM
    assumptions: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    recovery_notes: tuple[str, ...] = ()
    verification_requirements: tuple[str, ...] = ()
    authority: str = field(
        default=TACTICAL_OPTION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.kind,
            OptionKind,
        ):
            raise TypeError(
                "kind must be OptionKind."
            )

        if not isinstance(
            self.confidence_band,
            ConfidenceBand,
        ):
            raise TypeError(
                "confidence_band must be ConfidenceBand."
            )

        if not isinstance(
            self.cost_band,
            CostBand,
        ):
            raise TypeError(
                "cost_band must be CostBand."
            )

        if type(
            self.reversible
        ) is not bool:
            raise TypeError(
                "reversible must be bool."
            )

        for name in (
            "option_id",
            "objective",
            "rationale",
            "expected_outcome",
        ):
            object.__setattr__(
                self,
                name,
                _bounded_text(
                    getattr(
                        self,
                        name,
                    ),
                    field_name=name,
                ),
            )

        object.__setattr__(
            self,
            "tool_name",
            _optional_text(
                self.tool_name,
                field_name="tool_name",
            ),
        )

        object.__setattr__(
            self,
            "capability",
            _optional_text(
                self.capability,
                field_name="capability",
            ),
        )

        for name in (
            "assumptions",
            "failure_modes",
            "recovery_notes",
            "verification_requirements",
        ):
            object.__setattr__(
                self,
                name,
                _bounded_tuple(
                    getattr(
                        self,
                        name,
                    ),
                    field_name=name,
                ),
            )

        if (
            self.kind
            == OptionKind.DEFER
        ):
            if (
                self.tool_name is not None
                or self.capability is not None
            ):
                raise ValueError(
                    "DEFER seed cannot name a tool or capability."
                )

            if not self.reversible:
                raise ValueError(
                    "DEFER seed must be reversible because it proposes "
                    "no external action."
                )

            return

        if (
            self.tool_name is None
            or self.capability is None
        ):
            raise ValueError(
                "OBSERVE, ACT, and RECOVER seeds require both "
                "tool_name and capability."
            )

        if not self.verification_requirements:
            raise ValueError(
                "Action-bearing option seeds require at least one "
                "verification requirement."
            )

        if (
            self.kind
            in (
                OptionKind.ACT,
                OptionKind.RECOVER,
            )
            and not self.failure_modes
        ):
            raise ValueError(
                "ACT and RECOVER seeds require at least one "
                "explicit failure mode."
            )

        if (
            not self.reversible
            and not self.recovery_notes
        ):
            raise ValueError(
                "Irreversible option seeds require an explicit "
                "recovery or containment note."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class OutcomeSimulation:
    """
    Prediction-only result associated with one TacticalOption.

    The simulation records what the seed predicts, what assumptions it depends
    on, what uncertainty remains, how it may fail, and what must be verified.
    Nothing in this object is evidence that the predicted outcome occurred.
    """

    option_id: str
    predicted_outcome: str
    confidence_band: ConfidenceBand
    confidence_score: float
    assumptions: tuple[str, ...]
    remaining_uncertainties: tuple[str, ...]
    failure_modes: tuple[str, ...]
    recovery_notes: tuple[str, ...]
    verification_requirements: tuple[str, ...]
    outcome_verified: bool = field(
        default=False,
        init=False,
    )
    prediction_only: bool = field(
        default=True,
        init=False,
    )
    authority: str = field(
        default=TACTICAL_OPTION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "option_id",
            _bounded_text(
                self.option_id,
                field_name="option_id",
            ),
        )

        object.__setattr__(
            self,
            "predicted_outcome",
            _bounded_text(
                self.predicted_outcome,
                field_name="predicted_outcome",
            ),
        )

        if not isinstance(
            self.confidence_band,
            ConfidenceBand,
        ):
            raise TypeError(
                "confidence_band must be ConfidenceBand."
            )

        expected_score = (
            _CONFIDENCE_SCORE[
                self.confidence_band
            ]
        )

        if (
            type(
                self.confidence_score
            )
            not in (
                int,
                float,
            )
            or isinstance(
                self.confidence_score,
                bool,
            )
        ):
            raise TypeError(
                "confidence_score must be numeric."
            )

        if (
            float(
                self.confidence_score
            )
            != expected_score
        ):
            raise ValueError(
                "confidence_score must be the canonical score "
                "for confidence_band."
            )

        object.__setattr__(
            self,
            "confidence_score",
            expected_score,
        )

        for name in (
            "assumptions",
            "remaining_uncertainties",
            "failure_modes",
            "recovery_notes",
            "verification_requirements",
        ):
            object.__setattr__(
                self,
                name,
                _bounded_tuple(
                    getattr(
                        self,
                        name,
                    ),
                    field_name=name,
                ),
            )


@dataclass(
    frozen=True,
    slots=True,
)
class SimulatedTacticalOption:
    """
    One zero-authority TacticalOption paired with its prediction envelope.
    """

    kind: OptionKind
    option: TacticalOption
    simulation: OutcomeSimulation
    tool_name: str | None = None
    authority: str = field(
        default=TACTICAL_OPTION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.kind,
            OptionKind,
        ):
            raise TypeError(
                "kind must be OptionKind."
            )

        if not isinstance(
            self.option,
            TacticalOption,
        ):
            raise TypeError(
                "option must be TacticalOption."
            )

        if not isinstance(
            self.simulation,
            OutcomeSimulation,
        ):
            raise TypeError(
                "simulation must be OutcomeSimulation."
            )

        tool_name = _optional_text(
            self.tool_name,
            field_name="tool_name",
        )

        object.__setattr__(
            self,
            "tool_name",
            tool_name,
        )

        if (
            self.option.option_id
            != self.simulation.option_id
        ):
            raise ValueError(
                "option and simulation IDs must match."
            )

        if (
            self.option.confidence
            != self.simulation.confidence_score
        ):
            raise ValueError(
                "option and simulation confidence must match."
            )

        if (
            self.option.authority
            != TACTICAL_OPTION_AUTHORITY_NONE
            or self.simulation.authority
            != TACTICAL_OPTION_AUTHORITY_NONE
        ):
            raise ValueError(
                "nested tactical values must remain AUTHORITY:NONE."
            )


class OutcomeSimulator:
    """
    Build a bounded prediction envelope from a grounded seed.

    This does not execute or emulate the tool. It only carries forward the
    explicitly proposed outcome and its uncertainty/failure/verification data.
    """

    def simulate(
        self,
        *,
        situation: TacticalSituation,
        seed: TacticalOptionSeed,
        option: TacticalOption,
    ) -> OutcomeSimulation:
        if not isinstance(
            situation,
            TacticalSituation,
        ):
            raise TypeError(
                "situation must be TacticalSituation."
            )

        if not isinstance(
            seed,
            TacticalOptionSeed,
        ):
            raise TypeError(
                "seed must be TacticalOptionSeed."
            )

        if not isinstance(
            option,
            TacticalOption,
        ):
            raise TypeError(
                "option must be TacticalOption."
            )

        if (
            situation.authority
            != TACTICAL_OPTION_AUTHORITY_NONE
            or seed.authority
            != TACTICAL_OPTION_AUTHORITY_NONE
            or option.authority
            != TACTICAL_OPTION_AUTHORITY_NONE
        ):
            raise ValueError(
                "simulation inputs must remain AUTHORITY:NONE."
            )

        if (
            seed.option_id
            != option.option_id
        ):
            raise ValueError(
                "seed and option IDs must match."
            )

        confidence_score = (
            _CONFIDENCE_SCORE[
                seed.confidence_band
            ]
        )

        return OutcomeSimulation(
            option_id=seed.option_id,
            predicted_outcome=(
                seed.expected_outcome
            ),
            confidence_band=(
                seed.confidence_band
            ),
            confidence_score=(
                confidence_score
            ),
            assumptions=(
                seed.assumptions
            ),
            remaining_uncertainties=(
                situation.uncertainties
            ),
            failure_modes=(
                seed.failure_modes
            ),
            recovery_notes=(
                seed.recovery_notes
            ),
            verification_requirements=(
                seed.verification_requirements
            ),
        )


class TacticalOptionGenerator:
    """
    Validate grounded strategy seeds against current KUMA capability/permission
    metadata and produce prediction-only tactical options.

    The generator never ranks or selects among options. RAPHAEL-1E owns
    later decision logic.
    """

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        simulator: OutcomeSimulator | None = None,
    ) -> None:
        if not isinstance(
            capability_registry,
            CapabilityRegistry,
        ):
            raise TypeError(
                "capability_registry must be CapabilityRegistry."
            )

        if (
            simulator is not None
            and not isinstance(
                simulator,
                OutcomeSimulator,
            )
        ):
            raise TypeError(
                "simulator must be OutcomeSimulator or None."
            )

        self._capability_registry = (
            capability_registry
        )

        self._simulator = (
            simulator
            if simulator is not None
            else OutcomeSimulator()
        )

    def _available_tools(
        self,
        values: Iterable[str],
    ) -> frozenset[str]:
        return frozenset(
            _bounded_tuple(
                values,
                field_name="available_tool_names",
                limit=64,
            )
        )

    def _resolve_capability(
        self,
        *,
        situation: TacticalSituation,
        seed: TacticalOptionSeed,
        available_tools: frozenset[str],
    ) -> tuple[
        Capability,
        PermissionLevel,
    ]:
        assert (
            seed.tool_name is not None
            and seed.capability is not None
        )

        if (
            seed.tool_name
            not in available_tools
        ):
            raise ValueError(
                "Option seed names a tool that is not in the "
                "caller-supplied current runtime tool set: "
                f"{seed.tool_name!r}"
            )

        if (
            seed.capability
            not in situation.available_capabilities
        ):
            raise ValueError(
                "Option seed names a capability that is not present "
                "in the TacticalSituation: "
                f"{seed.capability!r}"
            )

        capability = (
            self._capability_registry.get(
                seed.capability
            )
        )

        if capability is None:
            raise ValueError(
                "Option seed capability is absent from the supplied "
                "CapabilityRegistry."
            )

        owners = tuple(
            sorted(
                item.name
                for item
                in self._capability_registry.all()
                if (
                    seed.tool_name
                    in item.tools
                )
            )
        )

        if owners != (
            seed.capability,
        ):
            raise ValueError(
                "Tool-to-capability ownership is missing or ambiguous: "
                f"{seed.tool_name!r} -> {owners!r}"
            )

        try:
            permission = (
                require_explicit_permission(
                    seed.tool_name
                )
            )
        except ValueError as error:
            raise ValueError(
                "Option seed tool lacks canonical permission metadata."
            ) from error

        return (
            capability,
            permission,
        )

    def _build_option(
        self,
        *,
        situation: TacticalSituation,
        seed: TacticalOptionSeed,
        available_tools: frozenset[str],
    ) -> TacticalOption:
        if (
            seed.kind
            == OptionKind.DEFER
        ):
            return TacticalOption(
                option_id=seed.option_id,
                objective=seed.objective,
                rationale=seed.rationale,
                expected_outcome=(
                    seed.expected_outcome
                ),
                confidence=(
                    _CONFIDENCE_SCORE[
                        seed.confidence_band
                    ]
                ),
                risk=TacticalRisk.LOW,
                required_permission=(
                    PermissionLevel.SAFE
                ),
                reversible=True,
                capability=None,
                cost=0.0,
            )

        (
            capability,
            permission,
        ) = self._resolve_capability(
            situation=situation,
            seed=seed,
            available_tools=available_tools,
        )

        risk = _derived_risk(
            permission=permission,
            capability=capability,
            reversible=seed.reversible,
        )

        return TacticalOption(
            option_id=seed.option_id,
            objective=seed.objective,
            rationale=seed.rationale,
            expected_outcome=(
                seed.expected_outcome
            ),
            confidence=(
                _CONFIDENCE_SCORE[
                    seed.confidence_band
                ]
            ),
            risk=risk,
            required_permission=permission,
            reversible=seed.reversible,
            capability=(
                seed.capability
            ),
            cost=(
                _COST_SCORE[
                    seed.cost_band
                ]
            ),
        )

    def generate(
        self,
        situation: TacticalSituation,
        seeds: Iterable[
            TacticalOptionSeed
        ],
        *,
        available_tool_names: Iterable[str] = (),
    ) -> tuple[
        SimulatedTacticalOption,
        ...,
    ]:
        if not isinstance(
            situation,
            TacticalSituation,
        ):
            raise TypeError(
                "situation must be TacticalSituation."
            )

        if (
            situation.authority
            != TACTICAL_OPTION_AUTHORITY_NONE
        ):
            raise ValueError(
                "TacticalSituation authority must remain NONE."
            )

        if isinstance(
            seeds,
            (
                str,
                bytes,
            ),
        ):
            raise TypeError(
                "seeds must be an iterable of TacticalOptionSeed."
            )

        try:
            seed_values = tuple(
                seeds
            )
        except TypeError as error:
            raise TypeError(
                "seeds must be iterable."
            ) from error

        if not seed_values:
            return ()

        if len(seed_values) > _MAX_ITEMS:
            raise ValueError(
                f"At most {_MAX_ITEMS} tactical option seeds are allowed."
            )

        for seed in seed_values:
            if not isinstance(
                seed,
                TacticalOptionSeed,
            ):
                raise TypeError(
                    "seeds must contain TacticalOptionSeed values."
                )

        option_ids = tuple(
            seed.option_id
            for seed
            in seed_values
        )

        if (
            len(
                option_ids
            )
            != len(
                set(
                    option_ids
                )
            )
        ):
            raise ValueError(
                "Tactical option IDs must be unique."
            )

        available_tools = (
            self._available_tools(
                available_tool_names
            )
        )

        results = []

        for seed in seed_values:
            option = self._build_option(
                situation=situation,
                seed=seed,
                available_tools=available_tools,
            )

            simulation = (
                self._simulator.simulate(
                    situation=situation,
                    seed=seed,
                    option=option,
                )
            )

            results.append(
                SimulatedTacticalOption(
                    kind=seed.kind,
                    option=option,
                    simulation=simulation,
                    tool_name=(
                        seed.tool_name
                    ),
                )
            )

        return tuple(
            results
        )
