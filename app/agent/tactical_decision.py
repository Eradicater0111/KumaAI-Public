"""
KUMA RAPHAEL-1E deterministic tactical decision engine.

This module compares already-grounded RAPHAEL-1D option/simulation pairs and
produces one immutable TacticalDecision.

Safety model:
- decision is recommendation only and always AUTHORITY:NONE;
- predicted outcomes remain prediction-only and unverified;
- constraints are never inferred from natural-language prose;
- caller-supplied structured exclusions are the only option-level hard blocks;
- material uncertainty prefers a grounded OBSERVE option when available;
- ranking is lexicographic, deterministic, and policy-transparent;
- no tool arguments, permission grants, confirmations, execution, provider
  reads, memory retrieval, model calls, or state mutation occur here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
    TacticalDecision,
    TacticalDisposition,
    TacticalOption,
    TacticalRisk,
    TacticalSituation,
)
from app.agent.permissions import (
    PermissionLevel,
)
from app.agent.tactical_options import (
    OptionKind,
    SimulatedTacticalOption,
)


TACTICAL_DECISION_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_OPTIONS = 12
_MAX_TEXT_CHARS = 800

_PERMISSION_ORDER = {
    PermissionLevel.SAFE: 0,
    PermissionLevel.USER_AUTHORIZED: 1,
    PermissionLevel.DANGEROUS: 2,
}

_RISK_ORDER = {
    TacticalRisk.LOW: 0,
    TacticalRisk.MODERATE: 1,
    TacticalRisk.HIGH: 2,
    TacticalRisk.CRITICAL: 3,
}

_BLOCKED_DECISION_CONFIDENCE = 0.75


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


def _bounded_tuple(
    values: Iterable[str],
    *,
    field_name: str,
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
        :_MAX_OPTIONS
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


@dataclass(
    frozen=True,
    slots=True,
)
class OptionExclusion:
    """
    Structured hard exclusion supplied by an upstream policy/constraint layer.

    The decision engine does not parse TacticalSituation.constraints prose to
    invent exclusions. An exclusion names one exact option_id and a reason.
    """

    option_id: str
    reason: str
    authority: str = field(
        default=TACTICAL_DECISION_AUTHORITY_NONE,
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
            "reason",
            _bounded_text(
                self.reason,
                field_name="reason",
            ),
        )


def _candidate_key(
    candidate: SimulatedTacticalOption,
) -> tuple[
    int,
    int,
    int,
    float,
    float,
    str,
]:
    option = candidate.option

    return (
        _PERMISSION_ORDER[
            option.required_permission
        ],
        _RISK_ORDER[
            option.risk
        ],
        0
        if option.reversible
        else 1,
        -float(
            option.confidence
        ),
        float(
            option.cost
        ),
        option.option_id,
    )


def _is_caution_only(
    candidate: SimulatedTacticalOption,
) -> bool:
    option = candidate.option

    return (
        option.confidence <= 0.25
        or option.risk
        in (
            TacticalRisk.HIGH,
            TacticalRisk.CRITICAL,
        )
        or not option.reversible
        or (
            option.required_permission
            == PermissionLevel.DANGEROUS
        )
    )


def _decision_reason_for_candidate(
    candidate: SimulatedTacticalOption,
    *,
    uncertainty_preferred_observation: bool,
) -> tuple[
    TacticalDisposition,
    str,
]:
    option = candidate.option

    if (
        candidate.kind
        == OptionKind.DEFER
    ):
        return (
            TacticalDisposition.DEFER,
            (
                "External action is deferred because the grounded "
                "candidate set does not justify proceeding now."
            ),
        )

    if uncertainty_preferred_observation:
        return (
            TacticalDisposition.ADVISE,
            (
                "Material uncertainty remains, so the deterministic "
                "policy prefers a grounded observation option before "
                "external action."
            ),
        )

    if _is_caution_only(
        candidate
    ):
        return (
            TacticalDisposition.ADVISE,
            (
                "The selected option is recommendation-only because "
                "its confidence, risk, reversibility, or permission "
                "burden requires additional caution."
            ),
        )

    return (
        TacticalDisposition.ACTION_CANDIDATE,
        (
            "The selected option is the best-supported grounded "
            "action candidate under the deterministic comparison "
            "policy. This does not grant permission to execute it."
        ),
    )


class TacticalDecisionEngine:
    """
    Deterministically compare grounded zero-authority tactical options.

    Policy order for otherwise eligible candidates:
    1. lower permission burden;
    2. lower tactical risk;
    3. reversible before irreversible;
    4. higher confidence;
    5. lower cost;
    6. lexical option_id as the final deterministic tie-break.

    Special rules:
    - if uncertainty remains and an OBSERVE option is available, compare only
      OBSERVE options first;
    - if all non-DEFER options are caution-only and DEFER exists, choose DEFER;
    - if every supplied option is structurally excluded, return BLOCKED;
    - raw constraint prose is never parsed into policy.
    """

    def _validate_candidates(
        self,
        situation: TacticalSituation,
        candidates: Iterable[
            SimulatedTacticalOption
        ],
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
            != TACTICAL_DECISION_AUTHORITY_NONE
        ):
            raise ValueError(
                "TacticalSituation authority must remain NONE."
            )

        if isinstance(
            candidates,
            (
                str,
                bytes,
            ),
        ):
            raise TypeError(
                "candidates must be an iterable of "
                "SimulatedTacticalOption values."
            )

        try:
            values = tuple(
                candidates
            )
        except TypeError as error:
            raise TypeError(
                "candidates must be iterable."
            ) from error

        if len(values) > _MAX_OPTIONS:
            raise ValueError(
                f"At most {_MAX_OPTIONS} tactical candidates are allowed."
            )

        ids = []

        for candidate in values:
            if not isinstance(
                candidate,
                SimulatedTacticalOption,
            ):
                raise TypeError(
                    "candidates must contain "
                    "SimulatedTacticalOption values."
                )

            option = candidate.option
            simulation = candidate.simulation

            if (
                candidate.authority
                != TACTICAL_DECISION_AUTHORITY_NONE
                or option.authority
                != TACTICAL_DECISION_AUTHORITY_NONE
                or simulation.authority
                != TACTICAL_DECISION_AUTHORITY_NONE
            ):
                raise ValueError(
                    "candidate authority must remain NONE."
                )

            if (
                simulation.prediction_only
                is not True
                or simulation.outcome_verified
                is not False
            ):
                raise ValueError(
                    "candidate simulation must remain prediction-only "
                    "and unverified."
                )

            if (
                simulation.option_id
                != option.option_id
            ):
                raise ValueError(
                    "candidate option/simulation ID mismatch."
                )

            if (
                simulation.predicted_outcome
                != option.expected_outcome
            ):
                raise ValueError(
                    "candidate predicted outcome no longer matches "
                    "the grounded TacticalOption."
                )

            if (
                simulation.confidence_score
                != option.confidence
            ):
                raise ValueError(
                    "candidate confidence no longer matches its "
                    "simulation envelope."
                )

            if (
                simulation.remaining_uncertainties
                != situation.uncertainties
            ):
                raise ValueError(
                    "candidate simulation uncertainty no longer matches "
                    "the TacticalSituation."
                )

            if (
                option.confidence
                not in (
                    0.25,
                    0.50,
                    0.75,
                )
            ):
                raise ValueError(
                    "candidate confidence is outside RAPHAEL-1D "
                    "coarse confidence bands."
                )

            if (
                option.cost
                not in (
                    0.0,
                    0.10,
                    0.25,
                    0.50,
                    0.75,
                )
            ):
                raise ValueError(
                    "candidate cost is outside RAPHAEL-1D "
                    "coarse cost bands."
                )

            if (
                option.required_permission
                == PermissionLevel.DANGEROUS
                and option.risk
                != TacticalRisk.CRITICAL
            ):
                raise ValueError(
                    "dangerous candidate risk was downgraded below "
                    "RAPHAEL-1D's CRITICAL invariant."
                )

            if (
                option.required_permission
                == PermissionLevel.USER_AUTHORIZED
                and _RISK_ORDER[
                    option.risk
                ]
                < _RISK_ORDER[
                    TacticalRisk.MODERATE
                ]
            ):
                raise ValueError(
                    "user-authorized candidate risk was downgraded below "
                    "RAPHAEL-1D's MODERATE permission floor."
                )

            if (
                not option.reversible
                and _RISK_ORDER[
                    option.risk
                ]
                < _RISK_ORDER[
                    TacticalRisk.HIGH
                ]
            ):
                raise ValueError(
                    "irreversible candidate risk was downgraded below "
                    "RAPHAEL-1D's HIGH floor."
                )

            if (
                candidate.kind
                == OptionKind.DEFER
            ):
                if (
                    candidate.tool_name is not None
                    or option.capability is not None
                ):
                    raise ValueError(
                        "DEFER candidate cannot carry a tool or capability."
                    )

                if (
                    option.required_permission
                    != PermissionLevel.SAFE
                    or option.risk
                    != TacticalRisk.LOW
                    or not option.reversible
                    or option.cost
                    != 0.0
                ):
                    raise ValueError(
                        "DEFER candidate no longer matches RAPHAEL-1D's "
                        "safe zero-cost no-action invariant."
                    )
            else:
                if candidate.tool_name is None:
                    raise ValueError(
                        "Action-bearing candidate requires a grounded "
                        "tool identity."
                    )

                if option.capability is None:
                    raise ValueError(
                        "Action-bearing candidate requires a grounded "
                        "capability."
                    )

                if (
                    option.capability
                    not in situation.available_capabilities
                ):
                    raise ValueError(
                        "Candidate capability is not currently available "
                        "in the TacticalSituation."
                    )

            ids.append(
                option.option_id
            )

        if (
            len(
                ids
            )
            != len(
                set(
                    ids
                )
            )
        ):
            raise ValueError(
                "Tactical candidate option IDs must be unique."
            )

        return values

    def _validate_exclusions(
        self,
        candidates: tuple[
            SimulatedTacticalOption,
            ...,
        ],
        exclusions: Iterable[
            OptionExclusion
        ],
    ) -> tuple[
        OptionExclusion,
        ...,
    ]:
        if isinstance(
            exclusions,
            (
                str,
                bytes,
            ),
        ):
            raise TypeError(
                "exclusions must be an iterable of OptionExclusion values."
            )

        try:
            values = tuple(
                exclusions
            )
        except TypeError as error:
            raise TypeError(
                "exclusions must be iterable."
            ) from error

        if len(values) > _MAX_OPTIONS:
            raise ValueError(
                f"At most {_MAX_OPTIONS} option exclusions are allowed."
            )

        candidate_ids = {
            candidate.option.option_id
            for candidate
            in candidates
        }

        seen = set()

        for exclusion in values:
            if not isinstance(
                exclusion,
                OptionExclusion,
            ):
                raise TypeError(
                    "exclusions must contain OptionExclusion values."
                )

            if (
                exclusion.authority
                != TACTICAL_DECISION_AUTHORITY_NONE
            ):
                raise ValueError(
                    "OptionExclusion authority must remain NONE."
                )

            if (
                exclusion.option_id
                not in candidate_ids
            ):
                raise ValueError(
                    "OptionExclusion references an unknown option_id: "
                    f"{exclusion.option_id!r}"
                )

            if (
                exclusion.option_id
                in seen
            ):
                raise ValueError(
                    "OptionExclusion option IDs must be unique."
                )

            seen.add(
                exclusion.option_id
            )

        return values

    def _blocked_decision(
        self,
        *,
        situation: TacticalSituation,
        candidates: tuple[
            SimulatedTacticalOption,
            ...,
        ],
        reason: str,
    ) -> TacticalDecision:
        return TacticalDecision(
            disposition=(
                TacticalDisposition.BLOCKED
            ),
            reason=reason,
            confidence=(
                _BLOCKED_DECISION_CONFIDENCE
            ),
            chosen_option=None,
            rejected_options=tuple(
                candidate.option
                for candidate
                in candidates
            ),
            remaining_uncertainties=(
                situation.uncertainties
            ),
        )

    def decide(
        self,
        situation: TacticalSituation,
        candidates: Iterable[
            SimulatedTacticalOption
        ],
        *,
        exclusions: Iterable[
            OptionExclusion
        ] = (),
    ) -> TacticalDecision:
        candidate_values = (
            self._validate_candidates(
                situation,
                candidates,
            )
        )

        exclusion_values = (
            self._validate_exclusions(
                candidate_values,
                exclusions,
            )
        )

        if not candidate_values:
            return self._blocked_decision(
                situation=situation,
                candidates=(),
                reason=(
                    "No grounded tactical options were supplied, so "
                    "Raphael cannot recommend a next tactical direction."
                ),
            )

        excluded_ids = {
            exclusion.option_id
            for exclusion
            in exclusion_values
        }

        eligible = tuple(
            candidate
            for candidate
            in candidate_values
            if (
                candidate.option.option_id
                not in excluded_ids
            )
        )

        if not eligible:
            exclusion_summary = "; ".join(
                (
                    exclusion.option_id
                    + ": "
                    + exclusion.reason
                )
                for exclusion
                in exclusion_values
            )

            return self._blocked_decision(
                situation=situation,
                candidates=(
                    candidate_values
                ),
                reason=(
                    "Every grounded tactical option was explicitly "
                    "excluded by structured constraints. "
                    + exclusion_summary
                ),
            )

        observe_candidates = tuple(
            candidate
            for candidate
            in eligible
            if (
                candidate.kind
                == OptionKind.OBSERVE
            )
        )

        defer_candidates = tuple(
            candidate
            for candidate
            in eligible
            if (
                candidate.kind
                == OptionKind.DEFER
            )
        )

        action_candidates = tuple(
            candidate
            for candidate
            in eligible
            if (
                candidate.kind
                != OptionKind.DEFER
            )
        )

        uncertainty_preferred_observation = bool(
            situation.uncertainties
            and observe_candidates
        )

        if uncertainty_preferred_observation:
            selection_pool = (
                observe_candidates
            )

        elif (
            defer_candidates
            and action_candidates
            and all(
                _is_caution_only(
                    candidate
                )
                for candidate
                in action_candidates
            )
        ):
            selection_pool = (
                defer_candidates
            )

        elif action_candidates:
            selection_pool = (
                action_candidates
            )

        elif defer_candidates:
            selection_pool = (
                defer_candidates
            )

        else:
            return self._blocked_decision(
                situation=situation,
                candidates=(
                    candidate_values
                ),
                reason=(
                    "No eligible grounded tactical option remains "
                    "after structured constraint filtering."
                ),
            )

        chosen = min(
            selection_pool,
            key=_candidate_key,
        )

        (
            disposition,
            reason,
        ) = _decision_reason_for_candidate(
            chosen,
            uncertainty_preferred_observation=(
                uncertainty_preferred_observation
            ),
        )

        rejected = tuple(
            candidate.option
            for candidate
            in candidate_values
            if (
                candidate.option.option_id
                != chosen.option.option_id
            )
        )

        decision = TacticalDecision(
            disposition=disposition,
            reason=reason,
            confidence=(
                chosen.option.confidence
            ),
            chosen_option=(
                chosen.option
            ),
            rejected_options=rejected,
            remaining_uncertainties=(
                situation.uncertainties
            ),
        )

        if (
            decision.authority
            != TACTICAL_DECISION_AUTHORITY_NONE
        ):
            raise RuntimeError(
                "tactical decision authority invariant failed."
            )

        return decision
