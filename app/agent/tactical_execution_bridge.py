"""
KUMA RAPHAEL-1F authority-aware execution handoff bridge.

This module does NOT execute tools.

It validates one zero-authority RAPHAEL tactical ACTION_CANDIDATE against:
- the exact chosen 1E decision,
- the matching 1D simulated candidate,
- current semantic capability ownership,
- the caller-supplied current runtime tool set,
- canonical permission metadata,
- the CURRENT user request through KUMA's existing grounding predicate.

If all generic checks pass, it can prepare an immutable handoff that may be
forwarded into KUMA's existing safety/execution/verification pipeline.

Physical GUI tools are deliberately NOT given a generic handoff. They are
classified as requiring KUMA's existing exact runtime GUI authority/provenance
pipeline.

Critical invariants:
- RAPHAEL recommendation != authorization
- ACTION_CANDIDATE != execution
- request grounding != dangerous approval
- dangerous classification remains dangerous
- predicted outcome != verified result
- handoff preparation never calls a tool or executor
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from app.agent.capability_registry import (
    CapabilityRegistry,
)
from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
    TacticalDecision,
    TacticalDisposition,
    TacticalRisk,
    TacticalSituation,
)
from app.agent.permissions import (
    PermissionLevel,
    require_explicit_permission,
)
from app.agent.tactical_options import (
    OptionKind,
    SimulatedTacticalOption,
)


TACTICAL_EXECUTION_BRIDGE_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_TEXT_CHARS = 4000
_MAX_ARGUMENT_KEYS = 32
_MAX_CONTAINER_ITEMS = 64
_MAX_ARGUMENT_DEPTH = 6
_MAX_AVAILABLE_TOOLS = 128

_PHYSICAL_GUI_TOOLS = frozenset(
    {
        "move_mouse",
        "move_mouse_vision",
        "click",
        "click_vision",
        "hold_mouse",
        "hold_mouse_vision",
        "release_mouse",
        "type_text",
        "press_key",
        "scroll",
    }
)


class HandoffDisposition(str, Enum):
    FORWARD_TO_KUMA = "forward_to_kuma"
    GUI_AUTHORITY_REQUIRED = "gui_authority_required"
    REJECTED = "rejected"


def _text(
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

    if len(normalized) > _MAX_TEXT_CHARS:
        raise ValueError(
            f"{field_name} exceeds the bounded text limit."
        )

    return normalized


def _request_text(
    value,
) -> str:
    """
    Preserve the CURRENT request exactly apart from surrounding whitespace.

    The bridge must never rewrite internal request text before KUMA performs
    its own grounding check.
    """

    if not isinstance(
        value,
        str,
    ):
        raise TypeError(
            "current_request must be a string."
        )

    stripped = value.strip()

    if not stripped:
        raise ValueError(
            "current_request cannot be empty."
        )

    if len(stripped) > _MAX_TEXT_CHARS:
        raise ValueError(
            "current_request exceeds the bounded text limit."
        )

    return stripped


def _argument_key(
    value,
) -> str:
    """
    Validate an argument key without rewriting its identity.
    """

    if not isinstance(
        value,
        str,
    ):
        raise TypeError(
            "tool argument mapping keys must be strings."
        )

    if not value.strip():
        raise ValueError(
            "tool argument mapping keys cannot be empty."
        )

    if len(value) > _MAX_TEXT_CHARS:
        raise ValueError(
            "tool argument key exceeds the bounded text limit."
        )

    return value


def _available_tools(
    values: Iterable[str],
) -> frozenset[str]:
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

    if len(raw) > _MAX_AVAILABLE_TOOLS:
        raise ValueError(
            "available_tool_names exceeds the bounded runtime tool limit."
        )

    normalized = []

    for value in raw:
        normalized.append(
            _text(
                value,
                field_name="available_tool_name",
            )
        )

    return frozenset(
        normalized
    )


def _freeze_value(
    value: Any,
    *,
    depth: int = 0,
):
    if depth > _MAX_ARGUMENT_DEPTH:
        raise ValueError(
            "tool arguments exceed the maximum nesting depth."
        )

    if value is None:
        return None

    if type(value) in (
        bool,
        int,
        float,
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        if len(value) > _MAX_TEXT_CHARS:
            raise ValueError(
                "tool argument string exceeds the bounded text limit."
            )

        return value

    if isinstance(
        value,
        Mapping,
    ):
        if len(value) > _MAX_CONTAINER_ITEMS:
            raise ValueError(
                "tool argument mapping exceeds the bounded item limit."
            )

        frozen = {}

        for key, nested in value.items():
            exact_key = _argument_key(
                key
            )

            if exact_key in frozen:
                raise ValueError(
                    "tool argument mapping contains duplicate keys."
                )

            frozen[
                exact_key
            ] = _freeze_value(
                nested,
                depth=depth + 1,
            )

        return MappingProxyType(
            frozen
        )

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        if len(value) > _MAX_CONTAINER_ITEMS:
            raise ValueError(
                "tool argument sequence exceeds the bounded item limit."
            )

        return tuple(
            _freeze_value(
                nested,
                depth=depth + 1,
            )
            for nested
            in value
        )

    raise TypeError(
        "tool arguments may contain only JSON-like scalar, mapping, "
        "list, or tuple values."
    )


def _freeze_arguments(
    arguments: Mapping[str, Any],
) -> MappingProxyType:
    if not isinstance(
        arguments,
        Mapping,
    ):
        raise TypeError(
            "arguments must be a mapping."
        )

    if len(arguments) > _MAX_ARGUMENT_KEYS:
        raise ValueError(
            "arguments exceeds the bounded top-level key limit."
        )

    frozen = _freeze_value(
        arguments
    )

    if not isinstance(
        frozen,
        MappingProxyType,
    ):
        raise RuntimeError(
            "argument freezing invariant failed."
        )

    return frozen


def _thaw_value(
    value,
):
    if isinstance(
        value,
        Mapping,
    ):
        return {
            key: _thaw_value(
                nested
            )
            for key, nested
            in value.items()
        }

    if isinstance(
        value,
        tuple,
    ):
        return [
            _thaw_value(
                nested
            )
            for nested
            in value
        ]

    return value


def _canonical_json(
    value,
) -> str:
    return json.dumps(
        _thaw_value(
            value
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        allow_nan=False,
    )


def _digest_text(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


def _arguments_digest(
    arguments: MappingProxyType,
) -> str:
    return _digest_text(
        _canonical_json(
            arguments
        )
    )


@dataclass(
    frozen=True,
    slots=True,
)
class RaphaelExecutionHandoff:
    """
    Immutable zero-authority handoff into KUMA's existing action pipeline.

    This object is NOT permission, approval, execution, or verification.
    """

    option_id: str
    tool_name: str
    capability: str
    required_permission: PermissionLevel
    requires_confirmation: bool
    request_digest: str
    arguments_digest: str
    arguments: MappingProxyType
    authority: str = field(
        default=TACTICAL_EXECUTION_BRIDGE_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "option_id",
            _text(
                self.option_id,
                field_name="option_id",
            ),
        )

        object.__setattr__(
            self,
            "tool_name",
            _text(
                self.tool_name,
                field_name="tool_name",
            ),
        )

        object.__setattr__(
            self,
            "capability",
            _text(
                self.capability,
                field_name="capability",
            ),
        )

        if not isinstance(
            self.required_permission,
            PermissionLevel,
        ):
            raise TypeError(
                "required_permission must be PermissionLevel."
            )

        if type(
            self.requires_confirmation
        ) is not bool:
            raise TypeError(
                "requires_confirmation must be bool."
            )

        expected_confirmation = (
            self.required_permission
            == PermissionLevel.DANGEROUS
        )

        if (
            self.requires_confirmation
            != expected_confirmation
        ):
            raise ValueError(
                "requires_confirmation must exactly match the "
                "canonical dangerous permission class."
            )

        for field_name in (
            "request_digest",
            "arguments_digest",
        ):
            value = getattr(
                self,
                field_name,
            )

            if (
                not isinstance(
                    value,
                    str,
                )
                or len(value) != 64
                or any(
                    character
                    not in "0123456789abcdef"
                    for character
                    in value
                )
            ):
                raise ValueError(
                    f"{field_name} must be a lowercase SHA-256 hex digest."
                )

        if not isinstance(
            self.arguments,
            MappingProxyType,
        ):
            raise TypeError(
                "arguments must be an immutable MappingProxyType."
            )

        if (
            _arguments_digest(
                self.arguments
            )
            != self.arguments_digest
        ):
            raise ValueError(
                "arguments_digest does not match the immutable arguments."
            )

    def arguments_copy(
        self,
    ) -> dict[str, Any]:
        """
        Return a fresh mutable copy for KUMA's downstream pipeline.

        Returning the copy performs no execution and grants no authority.
        """

        return _thaw_value(
            self.arguments
        )

    def matches_current_request(
        self,
        current_request: str,
    ) -> bool:
        """
        Bind this handoff to the same normalized current request.

        This is replay detection only; a match is not authorization.
        """

        try:
            normalized = _request_text(
                current_request
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        return (
            _digest_text(
                normalized
            )
            == self.request_digest
        )


@dataclass(
    frozen=True,
    slots=True,
)
class HandoffAssessment:
    """
    Zero-authority bridge assessment.

    Only FORWARD_TO_KUMA carries a generic execution handoff.
    GUI_AUTHORITY_REQUIRED deliberately carries no handoff.
    """

    disposition: HandoffDisposition
    reason: str
    handoff: RaphaelExecutionHandoff | None = None
    authority: str = field(
        default=TACTICAL_EXECUTION_BRIDGE_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.disposition,
            HandoffDisposition,
        ):
            raise TypeError(
                "disposition must be HandoffDisposition."
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
            self.disposition
            == HandoffDisposition.FORWARD_TO_KUMA
        ):
            if not isinstance(
                self.handoff,
                RaphaelExecutionHandoff,
            ):
                raise ValueError(
                    "FORWARD_TO_KUMA requires an execution handoff."
                )

        elif self.handoff is not None:
            raise ValueError(
                "Non-forward bridge assessments cannot carry a handoff."
            )


class RaphaelExecutionBridge:
    """
    Prepare, but never execute, one Raphael ACTION_CANDIDATE.

    current_request_authorizer must be KUMA's existing pure current-request
    grounding predicate, or a test double with the same contract:

        (current_request, tool_name, arguments) -> bool

    The callback may establish only that the CURRENT request grounds the
    proposed tool call. It must not be treated as dangerous approval.
    """

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        current_request_authorizer: Callable[
            [
                str,
                str,
                dict[str, Any],
            ],
            bool,
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
            current_request_authorizer
        ):
            raise TypeError(
                "current_request_authorizer must be callable."
            )

        self._capability_registry = (
            capability_registry
        )

        self._current_request_authorizer = (
            current_request_authorizer
        )

    @staticmethod
    def _reject(
        reason: str,
    ) -> HandoffAssessment:
        return HandoffAssessment(
            disposition=(
                HandoffDisposition.REJECTED
            ),
            reason=reason,
        )

    def prepare(
        self,
        *,
        situation: TacticalSituation,
        decision: TacticalDecision,
        candidate: SimulatedTacticalOption,
        current_request: str,
        arguments: Mapping[str, Any],
        available_tool_names: Iterable[str],
    ) -> HandoffAssessment:
        if not isinstance(
            situation,
            TacticalSituation,
        ):
            raise TypeError(
                "situation must be TacticalSituation."
            )

        if not isinstance(
            decision,
            TacticalDecision,
        ):
            raise TypeError(
                "decision must be TacticalDecision."
            )

        if not isinstance(
            candidate,
            SimulatedTacticalOption,
        ):
            raise TypeError(
                "candidate must be SimulatedTacticalOption."
            )

        if (
            situation.authority
            != TACTICAL_EXECUTION_BRIDGE_AUTHORITY_NONE
            or decision.authority
            != TACTICAL_EXECUTION_BRIDGE_AUTHORITY_NONE
            or candidate.authority
            != TACTICAL_EXECUTION_BRIDGE_AUTHORITY_NONE
            or candidate.option.authority
            != TACTICAL_EXECUTION_BRIDGE_AUTHORITY_NONE
            or candidate.simulation.authority
            != TACTICAL_EXECUTION_BRIDGE_AUTHORITY_NONE
        ):
            return self._reject(
                "Raphael authority invariant failed; all tactical inputs "
                "must remain AUTHORITY:NONE."
            )

        if (
            decision.disposition
            != TacticalDisposition.ACTION_CANDIDATE
        ):
            return self._reject(
                "Only ACTION_CANDIDATE decisions may enter the "
                "execution handoff boundary."
            )

        if decision.chosen_option is None:
            return self._reject(
                "ACTION_CANDIDATE decision has no chosen option."
            )

        if (
            decision.chosen_option
            != candidate.option
        ):
            return self._reject(
                "The supplied candidate does not exactly match the "
                "TacticalDecision chosen option."
            )

        if (
            decision.remaining_uncertainties
            != situation.uncertainties
        ):
            return self._reject(
                "Decision uncertainty no longer matches the "
                "TacticalSituation."
            )

        simulation = (
            candidate.simulation
        )

        if (
            simulation.prediction_only
            is not True
            or simulation.outcome_verified
            is not False
        ):
            return self._reject(
                "Candidate simulation must remain prediction-only "
                "and unverified."
            )

        if (
            simulation.remaining_uncertainties
            != situation.uncertainties
        ):
            return self._reject(
                "Candidate simulation uncertainty no longer matches "
                "the TacticalSituation."
            )

        if (
            simulation.option_id
            != candidate.option.option_id
            or simulation.predicted_outcome
            != candidate.option.expected_outcome
            or simulation.confidence_score
            != candidate.option.confidence
        ):
            return self._reject(
                "Candidate option and simulation envelope no longer match."
            )

        if (
            candidate.kind
            == OptionKind.DEFER
        ):
            return self._reject(
                "DEFER candidates can never enter the execution bridge."
            )

        tool_name = (
            candidate.tool_name
        )

        capability_name = (
            candidate.option.capability
        )

        if (
            tool_name is None
            or capability_name is None
        ):
            return self._reject(
                "Execution handoff requires both a grounded tool "
                "identity and semantic capability."
            )

        tool_name = _text(
            tool_name,
            field_name="tool_name",
        )

        capability_name = _text(
            capability_name,
            field_name="capability",
        )

        available_tools = (
            _available_tools(
                available_tool_names
            )
        )

        if (
            tool_name
            not in available_tools
        ):
            return self._reject(
                "Chosen tool is no longer present in the caller-supplied "
                "current runtime tool set."
            )

        if (
            capability_name
            not in situation.available_capabilities
        ):
            return self._reject(
                "Chosen capability is no longer present in the "
                "TacticalSituation."
            )

        capability = (
            self._capability_registry.get(
                capability_name
            )
        )

        if capability is None:
            return self._reject(
                "Chosen capability is absent from the current "
                "CapabilityRegistry."
            )

        owners = tuple(
            sorted(
                item.name
                for item
                in self._capability_registry.all()
                if tool_name
                in item.tools
            )
        )

        if owners != (
            capability_name,
        ):
            return self._reject(
                "Current tool-to-capability ownership is missing or "
                "ambiguous."
            )

        try:
            permission = (
                require_explicit_permission(
                    tool_name
                )
            )
        except ValueError:
            return self._reject(
                "Chosen tool no longer has canonical permission metadata."
            )

        if (
            permission
            != candidate.option.required_permission
            or permission
            != decision.required_permission
        ):
            return self._reject(
                "Canonical permission classification no longer matches "
                "the tactical option and decision."
            )

        if (
            permission
            == PermissionLevel.DANGEROUS
            and candidate.option.risk
            != TacticalRisk.CRITICAL
        ):
            return self._reject(
                "Dangerous tactical option was downgraded below "
                "CRITICAL risk."
            )

        if (
            permission
            == PermissionLevel.USER_AUTHORIZED
            and candidate.option.risk
            == TacticalRisk.LOW
        ):
            return self._reject(
                "USER_AUTHORIZED tactical option was downgraded below "
                "its permission risk floor."
            )

        if (
            not candidate.option.reversible
            and candidate.option.risk
            in (
                TacticalRisk.LOW,
                TacticalRisk.MODERATE,
            )
        ):
            return self._reject(
                "Irreversible tactical option was downgraded below "
                "HIGH risk."
            )

        normalized_request = _request_text(
            current_request
        )

        frozen_arguments = (
            _freeze_arguments(
                arguments
            )
        )

        mutable_arguments = (
            _thaw_value(
                frozen_arguments
            )
        )

        try:
            grounded = (
                self._current_request_authorizer(
                    normalized_request,
                    tool_name,
                    mutable_arguments,
                )
            )
        except Exception:
            return self._reject(
                "Current-request grounding check failed closed."
            )

        if type(
            grounded
        ) is not bool:
            return self._reject(
                "Current-request grounding check returned a non-boolean "
                "result and failed closed."
            )

        if not grounded:
            return self._reject(
                "Chosen tool call is not grounded in the CURRENT "
                "user request."
            )

        if (
            tool_name
            in _PHYSICAL_GUI_TOOLS
        ):
            return HandoffAssessment(
                disposition=(
                    HandoffDisposition.GUI_AUTHORITY_REQUIRED
                ),
                reason=(
                    "Current-request grounding passed, but physical GUI "
                    "execution requires KUMA's existing exact runtime GUI "
                    "authority/provenance pipeline. Raphael cannot attest "
                    "or bypass that authority."
                ),
            )

        handoff = RaphaelExecutionHandoff(
            option_id=(
                candidate.option.option_id
            ),
            tool_name=tool_name,
            capability=capability_name,
            required_permission=permission,
            requires_confirmation=(
                permission
                == PermissionLevel.DANGEROUS
            ),
            request_digest=(
                _digest_text(
                    normalized_request
                )
            ),
            arguments_digest=(
                _arguments_digest(
                    frozen_arguments
                )
            ),
            arguments=frozen_arguments,
        )

        return HandoffAssessment(
            disposition=(
                HandoffDisposition.FORWARD_TO_KUMA
            ),
            reason=(
                "The tactical candidate passed zero-authority bridge "
                "validation and current-request grounding. It may be "
                "forwarded only into KUMA's existing safety pipeline; "
                "this assessment grants no execution authority."
            ),
            handoff=handoff,
        )
