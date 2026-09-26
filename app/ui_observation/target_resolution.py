"""Conservative semantic target resolution over exact structured UI evidence.

This module resolves a normalized semantic selector against one exact immutable
StructuredUIObservation that is already joined to trusted screen provenance.
It performs no collection, model calls, store lookup, coordinate conversion,
permission check, target attestation, AX action, or GUI execution.

A resolved target is evidence only. It does not set ``semantic_target_verified``
and cannot authorize a click or any other action.
"""

from dataclasses import dataclass, field
import math
import time

from app.desktop.contracts import MAX_TEXT, positive_int
from app.ui_observation.contracts import (
    MAX_UI_TEXT,
    StructuredUIObservation,
    UIElementObservation,
)
from app.ui_observation.screen_binding import StructuredUIScreenBinding


TARGET_STATUS_RESOLVED = "resolved"
TARGET_STATUS_AMBIGUOUS = "ambiguous"
TARGET_STATUS_UNKNOWN = "unknown"
VALID_TARGET_STATUSES = frozenset({
    TARGET_STATUS_RESOLVED,
    TARGET_STATUS_AMBIGUOUS,
    TARGET_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "clock_unavailable",
    "invalid_binding",
    "invalid_observation",
    "invalid_selector",
    "source_observation_mismatch",
    "source_binding_from_future",
    "source_binding_expired",
    "no_semantic_match",
    "observation_incomplete",
    "candidate_eligibility_unknown",
    "no_eligible_candidate",
})

AMBIGUOUS_CODE = "multiple_candidates"

# These diagnostics mean the collected tree may omit another semantic match.
# A single observed candidate therefore cannot prove uniqueness.
UNIQUENESS_BLOCKING_DIAGNOSTICS = frozenset({
    "node_read_failed",
    "children_unavailable",
    "children_truncated",
    "depth_truncated",
    "nodes_truncated",
})

SOURCE_MATCH_DIAGNOSTICS = frozenset({
    "desktop_context_partial",
    "structured_ui_partial",
})


def _timestamp(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )



def _bounded_text(value):
    return (
        value is None
        or (
            type(value) is str
            and 0 < len(value) <= MAX_UI_TEXT
            and bool(value.strip())
        )
    )


def _bundle(value):
    return (
        type(value) is str
        and 0 < len(value) <= MAX_TEXT
        and bool(value.strip())
    )


def _normalized_text(value):
    return value.strip().casefold()


@dataclass(frozen=True)
class StructuredUITargetSelector:
    """Exact normalized semantic constraints supplied by a trusted caller.

    ``text`` matches the complete stripped/case-folded AX title or description.
    No substring, fuzzy, model, or instruction interpretation occurs here.
    Paths and coordinates deliberately are not selector inputs.
    """

    role: str | None = None
    subrole: str | None = None
    text: str | None = field(default=None, repr=False)
    require_enabled: bool = False
    require_positive_area: bool = False

    def __post_init__(self):
        for value in (self.role, self.subrole, self.text):
            if not _bounded_text(value):
                raise ValueError("Target selector text must be bounded and nonblank.")
        if self.role is None and self.subrole is None and self.text is None:
            raise ValueError("Target selector requires at least one semantic constraint.")
        if (
            type(self.require_enabled) is not bool
            or type(self.require_positive_area) is not bool
        ):
            raise ValueError("Target selector requirements must be booleans.")


@dataclass(frozen=True)
class ResolvedStructuredUITarget:
    """One exact snapshot-local UI element selected by conservative evidence."""

    binding: StructuredUIScreenBinding
    observation: StructuredUIObservation
    selector: StructuredUITargetSelector
    element: UIElementObservation
    resolved_at_monotonic: float
    expires_at_monotonic: float

    def __post_init__(self):
        if type(self.binding) is not StructuredUIScreenBinding:
            raise ValueError("A trusted structured-UI/screen binding is required.")
        if type(self.observation) is not StructuredUIObservation:
            raise ValueError("A structured UI observation is required.")
        if type(self.selector) is not StructuredUITargetSelector:
            raise ValueError("A normalized target selector is required.")
        if type(self.element) is not UIElementObservation:
            raise ValueError("A structured UI element is required.")
        if not _source_matches(self.observation, self.binding):
            raise ValueError("Resolved target sources do not match exactly.")
        if self.element not in self.observation.elements:
            raise ValueError("Resolved element is not part of the exact UI observation.")

        semantic = [
            item
            for item in self.observation.elements
            if _semantic_match(item, self.selector)
        ]
        eligible = []
        uncertain = []
        for item in semantic:
            state = _eligibility(item, self.selector)
            if state is True:
                eligible.append(item)
            elif state is None:
                uncertain.append(item)
        if (
            len(eligible) != 1
            or uncertain
            or eligible[0] != self.element
            or _uniqueness_is_blocked(self.observation, self.selector)
        ):
            raise ValueError("Resolved element uniqueness is not established.")

        if not all(_timestamp(value) for value in (
            self.resolved_at_monotonic,
            self.expires_at_monotonic,
        )):
            raise ValueError("Resolved target times must be finite and nonnegative.")
        if not (
            self.binding.linked_at_monotonic
            <= self.resolved_at_monotonic
            < self.expires_at_monotonic
        ):
            raise ValueError("Resolved target timing is invalid.")
        if self.expires_at_monotonic != self.binding.expires_at_monotonic:
            raise ValueError("Resolved target cannot outlive its source binding.")

    @property
    def ui_observation_id(self):
        return self.binding.ui_observation_id

    @property
    def screen_observation_id(self):
        return self.binding.screen_observation_id

    @property
    def application_pid(self):
        return self.binding.application_pid

    @property
    def application_bundle_id(self):
        return self.binding.application_bundle_id

    @property
    def path(self):
        return self.element.path

    def is_fresh(self, now):
        """Check recorded lifetime only; never recollect or grant authority."""
        return (
            _timestamp(now)
            and self.resolved_at_monotonic <= now < self.expires_at_monotonic
        )


@dataclass(frozen=True)
class StructuredUITargetResolutionResult:
    status: str
    resolution: ResolvedStructuredUITarget | None = None
    candidate_count: int = 0
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.status) is not str or self.status not in VALID_TARGET_STATUSES:
            raise ValueError("Invalid structured UI target resolution status.")
        if type(self.candidate_count) is not int or self.candidate_count < 0:
            raise ValueError("Candidate count must be a nonnegative integer.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Resolution diagnostics must be immutable and unique.")

        if self.status == TARGET_STATUS_RESOLVED:
            if type(self.resolution) is not ResolvedStructuredUITarget:
                raise ValueError("Resolved status requires exact target evidence.")
            if self.candidate_count != 1:
                raise ValueError("Resolved status requires exactly one candidate.")
            if any(code not in SOURCE_MATCH_DIAGNOSTICS for code in self.diagnostics):
                raise ValueError("Resolved diagnostics may preserve source partiality only.")
            expected = _source_diagnostics(self.resolution.binding)
            if self.diagnostics != expected:
                raise ValueError("Resolved diagnostics must preserve source integrity.")
            return

        if self.resolution is not None:
            raise ValueError("Unresolved status cannot contain resolved target evidence.")

        if self.status == TARGET_STATUS_AMBIGUOUS:
            if self.candidate_count < 2 or self.diagnostics != (AMBIGUOUS_CODE,):
                raise ValueError("Ambiguous status requires multiple known candidates.")
            return

        if len(self.diagnostics) != 1 or self.diagnostics[0] not in UNKNOWN_CODES:
            raise ValueError("Unknown status requires one structured diagnostic.")

    @property
    def resolved(self):
        return self.status == TARGET_STATUS_RESOLVED and self.resolution is not None



def _source_diagnostics(binding):
    diagnostics = []
    ui_binding = binding.ui_binding
    if "partial" in (
        ui_binding.desktop_before_status,
        ui_binding.desktop_after_status,
    ):
        diagnostics.append("desktop_context_partial")
    if ui_binding.ui_status == "partial":
        diagnostics.append("structured_ui_partial")
    return tuple(diagnostics)


def _source_matches(observation, binding):
    if (
        type(observation) is not StructuredUIObservation
        or type(binding) is not StructuredUIScreenBinding
    ):
        return False
    app = observation.active_application
    ui_binding = binding.ui_binding
    return (
        observation.status != "unavailable"
        and observation.observation_id == binding.ui_observation_id
        and observation.captured_at_monotonic == ui_binding.ui_captured_at
        and observation.status == ui_binding.ui_status
        and observation.diagnostics == ui_binding.ui_diagnostics
        and app is not None
        and positive_int(app.pid)
        and app.pid == binding.application_pid
        and _bundle(app.bundle_id)
        and app.bundle_id == binding.application_bundle_id
    )


def _semantic_possibility(element, selector):
    """Return True for a known match, False for a mismatch, or None if unknown."""

    states = []

    if selector.role is not None:
        if element.role is None:
            states.append(None)
        else:
            states.append(element.role == selector.role)

    if selector.subrole is not None:
        if element.subrole is None:
            states.append(None)
        else:
            states.append(element.subrole == selector.subrole)

    if selector.text is not None:
        wanted = _normalized_text(selector.text)
        if type(element.title) is str:
            states.append(_normalized_text(element.title) == wanted)
        elif type(element.description) is str:
            states.append(_normalized_text(element.description) == wanted)
        else:
            # The native provider uses None only when AX reports the optional
            # title/description attribute as unsupported or having no value.
            # Hard attribute-read failures reject the node and surface through
            # structured observation diagnostics instead. Therefore a
            # successfully observed element with neither text attribute is a
            # definite non-match for an exact text selector, not a possible
            # hidden text match.
            states.append(False)

    if any(state is False for state in states):
        return False
    if any(state is None for state in states):
        return None
    return True


def _semantic_match(element, selector):
    return _semantic_possibility(element, selector) is True


def _eligibility(element, selector):
    """Return True, False, or None when required evidence is unknown."""

    unknown = False

    if selector.require_enabled:
        if element.enabled is False:
            return False
        if element.enabled is None:
            unknown = True

    if selector.require_positive_area:
        position_known = (
            element.position_x is not None
            and element.position_y is not None
        )
        size_known = element.width is not None and element.height is not None
        if size_known and (element.width == 0 or element.height == 0):
            return False
        if not position_known or not size_known:
            unknown = True
        elif element.width <= 0 or element.height <= 0:
            return False

    return None if unknown else True


def _uniqueness_is_blocked(observation, selector):
    if set(observation.diagnostics) & UNIQUENESS_BLOCKING_DIAGNOSTICS:
        return True

    # Unknown semantic fields such as role/subrole remain conservative. Optional
    # text that AX explicitly reports as unsupported/no-value is handled as a
    # definite text non-match above; hard read failures are already represented
    # by observation diagnostics and block uniqueness separately.
    return any(
        _semantic_possibility(element, selector) is None
        for element in observation.elements
    )


def resolve_structured_ui_target(
    observation,
    binding,
    selector,
    *,
    clock=time.monotonic,
):
    """Resolve one normalized semantic selector against exact bounded UI evidence.

    Multiple known eligible matches are ``ambiguous``. Missing, stale, partially
    unknowable, or structurally incomplete evidence is ``unknown``. A single
    candidate is ``resolved`` only when its uniqueness and requested evidence
    requirements can be established without guessing.
    """

    if not callable(clock):
        raise TypeError("clock must be callable.")

    def unknown(code, candidate_count=0):
        return StructuredUITargetResolutionResult(
            status=TARGET_STATUS_UNKNOWN,
            candidate_count=candidate_count,
            diagnostics=(code,),
        )

    try:
        now = clock()
    except Exception:
        return unknown("clock_unavailable")
    if not _timestamp(now):
        return unknown("clock_unavailable")

    if type(binding) is not StructuredUIScreenBinding:
        return unknown("invalid_binding")
    if type(observation) is not StructuredUIObservation:
        return unknown("invalid_observation")
    if type(selector) is not StructuredUITargetSelector:
        return unknown("invalid_selector")
    if not _source_matches(observation, binding):
        return unknown("source_observation_mismatch")

    if now < binding.linked_at_monotonic:
        return unknown("source_binding_from_future")
    if now >= binding.expires_at_monotonic:
        return unknown("source_binding_expired")

    uniqueness_blocked = _uniqueness_is_blocked(observation, selector)

    semantic = [
        element
        for element in observation.elements
        if _semantic_match(element, selector)
    ]
    if not semantic:
        return unknown(
            "observation_incomplete"
            if uniqueness_blocked
            else "no_semantic_match"
        )

    eligible = []
    uncertain = []
    for element in semantic:
        state = _eligibility(element, selector)
        if state is True:
            eligible.append(element)
        elif state is None:
            uncertain.append(element)

    if len(eligible) >= 2:
        return StructuredUITargetResolutionResult(
            status=TARGET_STATUS_AMBIGUOUS,
            candidate_count=len(eligible),
            diagnostics=(AMBIGUOUS_CODE,),
        )

    if uncertain:
        return unknown(
            "candidate_eligibility_unknown",
            candidate_count=len(eligible) + len(uncertain),
        )

    if uniqueness_blocked:
        return unknown("observation_incomplete", candidate_count=len(eligible))

    if not eligible:
        return unknown("no_eligible_candidate")

    resolution = ResolvedStructuredUITarget(
        binding=binding,
        observation=observation,
        selector=selector,
        element=eligible[0],
        resolved_at_monotonic=now,
        expires_at_monotonic=binding.expires_at_monotonic,
    )
    return StructuredUITargetResolutionResult(
        status=TARGET_STATUS_RESOLVED,
        resolution=resolution,
        candidate_count=1,
        diagnostics=_source_diagnostics(binding),
    )
