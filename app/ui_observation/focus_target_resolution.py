"""Pure semantic candidate resolution for KUMA 8D2.

This module answers only:

    Does one exact semantic target selector independently resolve to one
    element in this complete bounded structured UI observation?

It deliberately does NOT inspect native focus identity and does not prefer
``focused=True`` elements.

Focus may later verify a uniquely resolved semantic target. Focus may never
choose a target from an ambiguous semantic candidate set.

This module performs no native AX access, collection, permission decision,
keyboard action, target authorization, or physical execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ui_observation.contracts import (
    StructuredUIObservation,
    UIElementObservation,
)
import app.ui_observation.target_resolution as target_resolution
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)


CANDIDATE_STATUS_RESOLVED = (
    "resolved"
)

CANDIDATE_STATUS_AMBIGUOUS = (
    "ambiguous"
)

CANDIDATE_STATUS_UNKNOWN = (
    "unknown"
)

VALID_CANDIDATE_STATUSES = frozenset({
    CANDIDATE_STATUS_RESOLVED,
    CANDIDATE_STATUS_AMBIGUOUS,
    CANDIDATE_STATUS_UNKNOWN,
})

AMBIGUOUS_CODE = (
    "multiple_candidates"
)

UNKNOWN_CODES = frozenset({
    "invalid_observation",
    "invalid_selector",
    "observation_unavailable",
    "observation_incomplete",
    "no_semantic_match",
    "candidate_eligibility_unknown",
    "no_eligible_candidate",
})


@dataclass(frozen=True)
class ResolvedFocusTargetCandidate:
    """One independently unique semantic candidate.

    This is semantic evidence only.

    It does not prove that this element currently owns native keyboard focus.
    """

    observation: StructuredUIObservation
    selector: StructuredUITargetSelector
    element: UIElementObservation

    def __post_init__(
        self,
    ):
        if (
            type(self.observation)
            is not StructuredUIObservation
        ):
            raise ValueError(
                "Exact structured UI observation is required."
            )

        if (
            type(self.selector)
            is not StructuredUITargetSelector
        ):
            raise ValueError(
                "Exact structured UI selector is required."
            )

        if (
            type(self.element)
            is not UIElementObservation
        ):
            raise ValueError(
                "Exact UI element observation is required."
            )

        if not any(
            item is self.element
            for item in self.observation.elements
        ):
            raise ValueError(
                "Resolved candidate must be an exact element "
                "object from its observation."
            )

        if (
            self.observation.status
            == "unavailable"
            or target_resolution
            ._uniqueness_is_blocked(
                self.observation,
                self.selector,
            )
        ):
            raise ValueError(
                "Resolved candidate semantic uniqueness "
                "is not established."
            )

        eligible = []

        uncertainty = False

        for item in self.observation.elements:
            semantic_state = (
                target_resolution
                ._semantic_possibility(
                    item,
                    self.selector,
                )
            )

            if semantic_state is None:
                uncertainty = True
                continue

            if semantic_state is not True:
                continue

            if not (
                target_resolution
                ._semantic_match(
                    item,
                    self.selector,
                )
            ):
                uncertainty = True
                continue

            eligibility = (
                target_resolution
                ._eligibility(
                    item,
                    self.selector,
                )
            )

            if eligibility is None:
                uncertainty = True

            elif eligibility is True:
                eligible.append(
                    item
                )

        if (
            uncertainty
            or len(
                eligible
            )
            != 1
            or eligible[
                0
            ]
            is not self.element
        ):
            raise ValueError(
                "Resolved candidate must be the exact "
                "independently unique eligible semantic target."
            )

    @property
    def path(
        self,
    ):
        """Snapshot-local join key only; never stable identity."""

        return (
            self.element.path
        )

    @property
    def application_pid(
        self,
    ):
        app = (
            self.observation.active_application
        )

        return (
            None
            if app is None
            else app.pid
        )

    @property
    def application_bundle_id(
        self,
    ):
        app = (
            self.observation.active_application
        )

        return (
            None
            if app is None
            else app.bundle_id
        )


@dataclass(frozen=True)
class FocusTargetCandidateResolutionResult:
    """Outcome of independent semantic target resolution."""

    status: str
    resolution: (
        ResolvedFocusTargetCandidate | None
    ) = None
    candidate_count: int = 0
    diagnostics: tuple[str, ...] = ()

    def __post_init__(
        self,
    ):
        if (
            type(self.status) is not str
            or self.status
            not in VALID_CANDIDATE_STATUSES
        ):
            raise ValueError(
                "Invalid focus-target candidate status."
            )

        if (
            type(self.candidate_count)
            is not int
            or self.candidate_count < 0
        ):
            raise ValueError(
                "Candidate count must be a nonnegative integer."
            )

        if (
            type(self.diagnostics) is not tuple
            or any(
                type(code) is not str
                for code in self.diagnostics
            )
            or len(
                set(
                    self.diagnostics
                )
            )
            != len(
                self.diagnostics
            )
        ):
            raise ValueError(
                "Candidate diagnostics must be immutable "
                "and unique."
            )

        if (
            self.status
            == CANDIDATE_STATUS_RESOLVED
        ):
            if (
                type(self.resolution)
                is not ResolvedFocusTargetCandidate
            ):
                raise ValueError(
                    "Resolved status requires exact candidate evidence."
                )

            if (
                self.candidate_count != 1
                or self.diagnostics != ()
            ):
                raise ValueError(
                    "Resolved status requires exactly one "
                    "candidate and no rejection diagnostic."
                )

            return

        if self.resolution is not None:
            raise ValueError(
                "Unresolved status cannot contain "
                "resolved candidate evidence."
            )

        if (
            self.status
            == CANDIDATE_STATUS_AMBIGUOUS
        ):
            if (
                self.candidate_count < 2
                or self.diagnostics
                != (
                    AMBIGUOUS_CODE,
                )
            ):
                raise ValueError(
                    "Ambiguous status requires multiple "
                    "known semantic candidates."
                )

            return

        if (
            len(
                self.diagnostics
            )
            != 1
            or self.diagnostics[0]
            not in UNKNOWN_CODES
        ):
            raise ValueError(
                "Unknown status requires one structured diagnostic."
            )

    @property
    def resolved(
        self,
    ):
        return (
            self.status
            == CANDIDATE_STATUS_RESOLVED
            and self.resolution
            is not None
        )


def resolve_focus_target_candidate(
    observation,
    selector,
):
    """Resolve the intended semantic target independently of focus.

    This intentionally mirrors the semantic/eligibility/uniqueness portion of
    Phase-7 target resolution by using the existing selector-semantics helpers.

    It omits screen binding and timing because those belong to later 8D2
    provenance composition.

    Crucially, ``UIElementObservation.focused`` and ``selected`` never affect
    candidate choice.
    """

    def unknown(
        code,
        candidate_count=0,
    ):
        return (
            FocusTargetCandidateResolutionResult(
                status=(
                    CANDIDATE_STATUS_UNKNOWN
                ),
                candidate_count=(
                    candidate_count
                ),
                diagnostics=(
                    code,
                ),
            )
        )

    if (
        type(observation)
        is not StructuredUIObservation
    ):
        return unknown(
            "invalid_observation"
        )

    if (
        type(selector)
        is not StructuredUITargetSelector
    ):
        return unknown(
            "invalid_selector"
        )

    if (
        observation.status
        == "unavailable"
    ):
        return unknown(
            "observation_unavailable"
        )

    uniqueness_blocked = (
        target_resolution
        ._uniqueness_is_blocked(
            observation,
            selector,
        )
    )

    semantic = [
        element
        for element
        in observation.elements
        if (
            target_resolution
            ._semantic_match(
                element,
                selector,
            )
        )
    ]

    if not semantic:
        return unknown(
            (
                "observation_incomplete"
                if uniqueness_blocked
                else "no_semantic_match"
            )
        )

    eligible = []
    uncertain = []

    for element in semantic:
        state = (
            target_resolution
            ._eligibility(
                element,
                selector,
            )
        )

        if state is True:
            eligible.append(
                element
            )

        elif state is None:
            uncertain.append(
                element
            )

    if len(
        eligible
    ) >= 2:
        return (
            FocusTargetCandidateResolutionResult(
                status=(
                    CANDIDATE_STATUS_AMBIGUOUS
                ),
                candidate_count=len(
                    eligible
                ),
                diagnostics=(
                    AMBIGUOUS_CODE,
                ),
            )
        )

    if uncertain:
        return unknown(
            "candidate_eligibility_unknown",
            candidate_count=(
                len(
                    eligible
                )
                + len(
                    uncertain
                )
            ),
        )

    if uniqueness_blocked:
        return unknown(
            "observation_incomplete",
            candidate_count=len(
                eligible
            ),
        )

    if not eligible:
        return unknown(
            "no_eligible_candidate"
        )

    resolution = (
        ResolvedFocusTargetCandidate(
            observation=observation,
            selector=selector,
            element=eligible[0],
        )
    )

    return (
        FocusTargetCandidateResolutionResult(
            status=(
                CANDIDATE_STATUS_RESOLVED
            ),
            resolution=resolution,
            candidate_count=1,
            diagnostics=(),
        )
    )
