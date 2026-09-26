"""Process-local provenance for runtime-issued GUI step authority.

KUMA's GoalStep.gui_authority fields are plain data. Their string values
cannot by themselves prove that a GoalStep passed the trusted runtime
authorization boundary.

This module records the exact in-process GoalPlan and GoalStep objects after
runtime GUI action-class authorization has succeeded.

Downstream code must trust only the exact provenance object currently held by
this store. Equal-value reconstructed plans, steps, decisions, or provenance
objects are not substitutes.

This module performs no tool execution, no GUI action, no keyboard input,
no focus collection, and no permission decision.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
)
import math
import threading
import time

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
)
from app.agent.gui_target_intent import (
    StructuredUITargetIntent,
)
from app.agent.gui_intent_authority import (
    GUI_AUTHORITY_CONFIRMED,
    GUI_AUTHORITY_EXPLICIT,
    MISSION_GUI_ACTION_TOOLS,
    GuiPlanAuthorityDecision,
    authorize_plan_gui_actions,
    validate_runtime_gui_authority,
)


class RuntimeGuiStepAuthorityProvenanceError(
    ValueError
):
    pass


def _timestamp(
    value,
):
    return (
        type(value)
        in (
            int,
            float,
        )
        and math.isfinite(
            value
        )
        and value >= 0
    )


def _human_goal(
    value,
):
    return (
        type(value)
        is str
        and bool(
            value.strip()
        )
    )


def _step_id(
    value,
):
    return (
        type(value)
        is str
        and bool(
            value.strip()
        )
    )


def _semantic_target_intent_snapshot(
    step,
):
    """Return one immutable semantic snapshot of plain step target data.

    This snapshot is not target authority.

    It only freezes the semantic target description present on the exact
    runtime GoalStep when GUI action-class authority provenance is issued.
    Later trust layers must independently prove that this semantic target is
    human-goal-bound, visually valid, and actually focused.
    """

    if type(step) is not GoalStep:
        raise RuntimeGuiStepAuthorityProvenanceError(
            "Exact GoalStep is required for "
            "semantic target snapshot."
        )

    raw = (
        step.gui_target_intent
    )

    if raw is None:
        return None

    if type(raw) is not dict:
        raise RuntimeGuiStepAuthorityProvenanceError(
            "GUI target intent must be a strict "
            "semantic dictionary."
        )

    try:
        snapshot = (
            StructuredUITargetIntent
            .from_dict(
                raw
            )
        )
    except Exception:
        raise RuntimeGuiStepAuthorityProvenanceError(
            "GUI target intent is invalid."
        ) from None

    return snapshot


def _plan_steps(
    plan,
):
    if type(plan) is not GoalPlan:
        raise RuntimeGuiStepAuthorityProvenanceError(
            "Exact GoalPlan is required."
        )

    if type(plan.steps) is not list:
        raise RuntimeGuiStepAuthorityProvenanceError(
            "GoalPlan steps must be the exact runtime list."
        )

    steps = tuple(
        plan.steps
    )

    if any(
        type(step)
        is not GoalStep
        for step in steps
    ):
        raise RuntimeGuiStepAuthorityProvenanceError(
            "GoalPlan contains an invalid step."
        )

    return steps


def _validated_authority_shape(
    plan,
    human_goal,
    decision,
):
    if type(plan) is not GoalPlan:
        raise RuntimeGuiStepAuthorityProvenanceError(
            "Exact GoalPlan is required."
        )

    if not _human_goal(
        human_goal
    ):
        raise RuntimeGuiStepAuthorityProvenanceError(
            "Original human goal is required."
        )

    if (
        type(plan.goal)
        is not str
        or plan.goal
        != human_goal
    ):
        raise RuntimeGuiStepAuthorityProvenanceError(
            "GoalPlan does not match the exact human goal."
        )

    if (
        type(decision)
        is not GuiPlanAuthorityDecision
        or decision.allowed
        is not True
    ):
        raise RuntimeGuiStepAuthorityProvenanceError(
            "Allowed runtime GUI authority decision is required."
        )

    steps = _plan_steps(
        plan
    )

    ids = []

    explicit = []
    confirmed = []
    gui_steps = []

    for step in steps:
        _semantic_target_intent_snapshot(
            step
        )

        if not _step_id(
            step.id
        ):
            raise RuntimeGuiStepAuthorityProvenanceError(
                "Every runtime GoalStep requires an exact ID."
            )

        ids.append(
            step.id
        )

        planned_tool = (
            step.planned_tool
        )

        if type(planned_tool) is not str:
            raise RuntimeGuiStepAuthorityProvenanceError(
                "GoalStep planned_tool must be a string."
            )

        planned_tool = (
            planned_tool.strip()
        )

        try:
            valid, _reason = (
                validate_runtime_gui_authority(
                    planned_tool,
                    step.gui_authority,
                )
            )
        except Exception:
            valid = False

        if not valid:
            raise RuntimeGuiStepAuthorityProvenanceError(
                "GoalStep does not carry valid "
                "runtime GUI authority state."
            )

        if (
            planned_tool
            not in MISSION_GUI_ACTION_TOOLS
        ):
            if step.gui_authority_goal not in {
                None,
                "",
            }:
                raise RuntimeGuiStepAuthorityProvenanceError(
                    "Non-GUI step cannot carry "
                    "a GUI authority goal."
                )

            continue

        if (
            type(step.gui_authority_goal)
            is not str
            or step.gui_authority_goal
            != human_goal
        ):
            raise RuntimeGuiStepAuthorityProvenanceError(
                "GUI step authority goal does not "
                "match the exact human goal."
            )

        gui_steps.append(
            step
        )

        if (
            step.gui_authority
            == GUI_AUTHORITY_EXPLICIT
        ):
            explicit.append(
                step.id
            )

        elif (
            step.gui_authority
            == GUI_AUTHORITY_CONFIRMED
        ):
            confirmed.append(
                step.id
            )

        else:
            raise RuntimeGuiStepAuthorityProvenanceError(
                "GUI step authority class is invalid."
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
        raise RuntimeGuiStepAuthorityProvenanceError(
            "Runtime GoalPlan contains duplicate step IDs."
        )

    if (
        type(decision.explicit_steps)
        is not tuple
        or type(decision.confirmed_steps)
        is not tuple
        or decision.explicit_steps
        != tuple(
            explicit
        )
        or decision.confirmed_steps
        != tuple(
            confirmed
        )
    ):
        raise RuntimeGuiStepAuthorityProvenanceError(
            "Runtime authority decision does not "
            "match the exact authorized plan."
        )

    return (
        steps,
        tuple(
            gui_steps
        ),
    )


@dataclass(frozen=True)
class RuntimeGuiStepAuthorityProvenance:
    """Exact runtime-issued authority provenance for one GUI GoalStep."""

    plan: GoalPlan = field(
        repr=False
    )

    step: GoalStep = field(
        repr=False
    )

    authority_decision: (
        GuiPlanAuthorityDecision
    ) = field(
        repr=False
    )

    human_goal: str = field(
        repr=False
    )

    plan_goal: str = field(
        repr=False
    )

    step_id: str

    planned_tool: str

    gui_authority: str = field(
        repr=False
    )

    gui_authority_goal: str = field(
        repr=False
    )

    issued_at_monotonic: float

    semantic_target_intent_snapshot: (
        StructuredUITargetIntent
        | None
    ) = field(
        default=None,
        repr=False,
    )

    def __post_init__(
        self,
    ):
        if (
            type(self.plan)
            is not GoalPlan
        ):
            raise ValueError(
                "Exact runtime GoalPlan is required."
            )

        if (
            type(self.step)
            is not GoalStep
        ):
            raise ValueError(
                "Exact runtime GoalStep is required."
            )

        if (
            type(self.authority_decision)
            is not GuiPlanAuthorityDecision
            or self.authority_decision.allowed
            is not True
        ):
            raise ValueError(
                "Exact allowed authority decision is required."
            )

        if not _human_goal(
            self.human_goal
        ):
            raise ValueError(
                "Exact human goal is required."
            )

        if (
            type(self.plan_goal)
            is not str
            or self.plan_goal
            != self.human_goal
        ):
            raise ValueError(
                "Plan-goal snapshot is invalid."
            )

        if not _step_id(
            self.step_id
        ):
            raise ValueError(
                "Exact step ID is required."
            )

        if (
            type(self.planned_tool)
            is not str
            or self.planned_tool
            not in MISSION_GUI_ACTION_TOOLS
        ):
            raise ValueError(
                "Provenance requires a GUI action step."
            )

        if (
            type(self.gui_authority)
            is not str
            or self.gui_authority
            not in {
                GUI_AUTHORITY_EXPLICIT,
                GUI_AUTHORITY_CONFIRMED,
            }
        ):
            raise ValueError(
                "Runtime GUI authority snapshot is invalid."
            )

        if (
            type(self.gui_authority_goal)
            is not str
            or self.gui_authority_goal
            != self.human_goal
        ):
            raise ValueError(
                "Runtime GUI authority goal snapshot is invalid."
            )

        if not _timestamp(
            self.issued_at_monotonic
        ):
            raise ValueError(
                "Runtime authority issue time is invalid."
            )

        try:
            current_target_snapshot = (
                _semantic_target_intent_snapshot(
                    self.step
                )
            )
        except Exception as error:
            raise ValueError(
                "Runtime semantic target snapshot "
                "is invalid."
            ) from error

        if (
            current_target_snapshot
            != self.semantic_target_intent_snapshot
        ):
            raise ValueError(
                "Runtime semantic target snapshot "
                "does not match the exact source step."
            )

        if not any(
            item is self.step
            for item in self.plan.steps
        ):
            raise ValueError(
                "Runtime GoalStep is not an exact "
                "member of its GoalPlan."
            )

        if (
            self.plan.goal
            != self.plan_goal
            or self.step.id
            != self.step_id
            or self.step.planned_tool
            != self.planned_tool
            or self.step.gui_authority
            != self.gui_authority
            or self.step.gui_authority_goal
            != self.gui_authority_goal
        ):
            raise ValueError(
                "Runtime authority provenance does not "
                "match its exact source objects."
            )

        try:
            valid, _reason = (
                validate_runtime_gui_authority(
                    self.planned_tool,
                    self.gui_authority,
                )
            )
        except Exception:
            valid = False

        if not valid:
            raise ValueError(
                "Runtime GUI authority snapshot is invalid."
            )

        expected_ids = (
            self.authority_decision
            .explicit_steps
            if (
                self.gui_authority
                == GUI_AUTHORITY_EXPLICIT
            )
            else self.authority_decision
            .confirmed_steps
        )

        if (
            self.step_id
            not in expected_ids
        ):
            raise ValueError(
                "Authority decision does not contain "
                "this exact GUI step."
            )

    def is_current(
        self,
    ):
        try:
            if (
                self.plan.goal
                != self.plan_goal
                or self.plan_goal
                != self.human_goal
            ):
                return False

            if not any(
                item is self.step
                for item in self.plan.steps
            ):
                return False

            if (
                self.step.id
                != self.step_id
                or self.step.planned_tool
                != self.planned_tool
                or self.step.gui_authority
                != self.gui_authority
                or self.step.gui_authority_goal
                != self.gui_authority_goal
            ):
                return False

            current_target_snapshot = (
                _semantic_target_intent_snapshot(
                    self.step
                )
            )

            if (
                current_target_snapshot
                != self.semantic_target_intent_snapshot
            ):
                return False

            valid, _reason = (
                validate_runtime_gui_authority(
                    self.planned_tool,
                    self.gui_authority,
                )
            )

            if not valid:
                return False

            expected_ids = (
                self.authority_decision
                .explicit_steps
                if (
                    self.gui_authority
                    == GUI_AUTHORITY_EXPLICIT
                )
                else self.authority_decision
                .confirmed_steps
            )

            return (
                self.step_id
                in expected_ids
            )

        except Exception:
            return False


@dataclass(frozen=True)
class RuntimeGuiPlanAuthorityProvenance:
    """Exact process-local authority graph for one runtime GoalPlan."""

    plan: GoalPlan = field(
        repr=False
    )

    authority_decision: (
        GuiPlanAuthorityDecision
    ) = field(
        repr=False
    )

    human_goal: str = field(
        repr=False
    )

    step_provenances: tuple[
        RuntimeGuiStepAuthorityProvenance,
        ...
    ] = field(
        repr=False
    )

    issued_at_monotonic: float

    def __post_init__(
        self,
    ):
        (
            _steps,
            gui_steps,
        ) = _validated_authority_shape(
            self.plan,
            self.human_goal,
            self.authority_decision,
        )

        if not _timestamp(
            self.issued_at_monotonic
        ):
            raise ValueError(
                "Runtime plan authority issue time is invalid."
            )

        if (
            type(self.step_provenances)
            is not tuple
            or any(
                type(item)
                is not RuntimeGuiStepAuthorityProvenance
                for item
                in self.step_provenances
            )
        ):
            raise ValueError(
                "Exact step provenance tuple is required."
            )

        if (
            len(
                self.step_provenances
            )
            != len(
                gui_steps
            )
        ):
            raise ValueError(
                "Runtime plan authority provenance "
                "does not cover every GUI step."
            )

        for step in gui_steps:
            matches = [
                item
                for item
                in self.step_provenances
                if item.step is step
            ]

            if len(
                matches
            ) != 1:
                raise ValueError(
                    "Each GUI step requires one exact "
                    "runtime authority provenance."
                )

            item = matches[
                0
            ]

            if (
                item.plan
                is not self.plan
                or item.authority_decision
                is not self.authority_decision
                or item.human_goal
                != self.human_goal
                or item.issued_at_monotonic
                != self.issued_at_monotonic
            ):
                raise ValueError(
                    "Step provenance does not belong "
                    "to this exact plan authority graph."
                )

    def is_current(
        self,
    ):
        try:
            (
                _steps,
                gui_steps,
            ) = _validated_authority_shape(
                self.plan,
                self.human_goal,
                self.authority_decision,
            )

            if (
                len(
                    gui_steps
                )
                != len(
                    self.step_provenances
                )
            ):
                return False

            for item in self.step_provenances:
                if (
                    item.plan
                    is not self.plan
                    or item.authority_decision
                    is not self.authority_decision
                    or not item.is_current()
                ):
                    return False

            return True

        except Exception:
            return False

    def provenance_for_exact_step(
        self,
        step,
    ):
        if type(step) is not GoalStep:
            return None

        for item in self.step_provenances:
            if item.step is step:
                return item

        return None


class RuntimeGuiStepAuthorityProvenanceStore:
    """One active runtime-authorized GoalPlan provenance graph."""

    def __init__(
        self,
        *,
        clock=time.monotonic,
    ):
        if not callable(
            clock
        ):
            raise TypeError(
                "clock must be callable."
            )

        self._clock = clock

        self._lock = (
            threading.RLock()
        )

        self._active = None

        self._last_now = None

    def _now(
        self,
    ):
        try:
            now = self._clock()
        except Exception as error:
            raise RuntimeGuiStepAuthorityProvenanceError(
                "Runtime authority clock is unavailable."
            ) from None

        if not _timestamp(
            now
        ):
            raise RuntimeGuiStepAuthorityProvenanceError(
                "Runtime authority clock is unavailable."
            )

        if (
            self._last_now is not None
            and now
            < self._last_now
        ):
            raise RuntimeGuiStepAuthorityProvenanceError(
                "Runtime authority clock moved backwards."
            )

        self._last_now = now

        return now

    def _issue_authorized_plan(
        self,
        plan,
        human_goal,
        authority_decision,
    ):
        """Publish one exact already-authorized runtime plan.

        This is intentionally a private producer boundary.

        Production callers must use
        RuntimeGuiStepAuthorityProducer.authorize_plan().
        Plain GoalPlan / GoalStep / decision values are not
        themselves authority to publish into the global store.
        """

        with self._lock:
            self._active = None

            now = self._now()

            (
                _steps,
                gui_steps,
            ) = _validated_authority_shape(
                plan,
                human_goal,
                authority_decision,
            )

            step_provenances = tuple(
                RuntimeGuiStepAuthorityProvenance(
                    plan=plan,
                    step=step,
                    authority_decision=(
                        authority_decision
                    ),
                    human_goal=(
                        human_goal
                    ),
                    plan_goal=(
                        plan.goal
                    ),
                    step_id=(
                        step.id
                    ),
                    planned_tool=(
                        step.planned_tool
                    ),
                    gui_authority=(
                        step.gui_authority
                    ),
                    gui_authority_goal=(
                        step.gui_authority_goal
                    ),
                    issued_at_monotonic=(
                        now
                    ),
                    semantic_target_intent_snapshot=(
                        _semantic_target_intent_snapshot(
                            step
                        )
                    ),
                )
                for step
                in gui_steps
            )

            provenance = (
                RuntimeGuiPlanAuthorityProvenance(
                    plan=plan,
                    authority_decision=(
                        authority_decision
                    ),
                    human_goal=(
                        human_goal
                    ),
                    step_provenances=(
                        step_provenances
                    ),
                    issued_at_monotonic=(
                        now
                    ),
                )
            )

            self._active = provenance

            return provenance

    def get_current(
        self,
        plan,
        step,
    ):
        """Return exact provenance only for the exact active runtime step."""

        if (
            type(plan)
            is not GoalPlan
            or type(step)
            is not GoalStep
        ):
            return None

        with self._lock:
            active = self._active

            if active is None:
                return None

            if active.plan is not plan:
                return None

            if not active.is_current():
                self._active = None
                return None

            if (
                type(plan.current_step_id)
                is not str
                or not plan.current_step_id
                or plan.current_step_id
                != step.id
            ):
                return None

            try:
                current = (
                    plan.get_step(
                        plan.current_step_id
                    )
                )
            except Exception:
                self._active = None
                return None

            if current is not step:
                return None

            provenance = (
                active
                .provenance_for_exact_step(
                    step
                )
            )

            if (
                provenance is None
                or not provenance.is_current()
            ):
                self._active = None
                return None

            return provenance

    def clear(
        self,
    ):
        with self._lock:
            self._active = None

    def __len__(
        self,
    ):
        with self._lock:
            return (
                0
                if self._active is None
                else 1
            )


@dataclass(frozen=True)
class RuntimeGuiStepAuthorityProduction:
    """Result of the trusted runtime authorization producer.

    An allowed decision is returned only after its exact
    process-local provenance graph has also been published.
    """

    decision: (
        GuiPlanAuthorityDecision
    )

    provenance: (
        RuntimeGuiPlanAuthorityProvenance
        | None
    ) = field(
        default=None,
        repr=False,
    )

    diagnostics: tuple[str, ...] = ()

    def __post_init__(
        self,
    ):
        if (
            type(self.decision)
            is not GuiPlanAuthorityDecision
        ):
            raise ValueError(
                "Exact GUI authority decision is required."
            )

        if (
            type(self.diagnostics)
            is not tuple
            or any(
                type(code)
                is not str
                for code
                in self.diagnostics
            )
        ):
            raise ValueError(
                "Producer diagnostics must be immutable text."
            )

        if self.decision.allowed:
            if (
                type(self.provenance)
                is not RuntimeGuiPlanAuthorityProvenance
                or self.diagnostics
            ):
                raise ValueError(
                    "Allowed authority production requires "
                    "exact published provenance."
                )

            if (
                self.provenance.authority_decision
                is not self.decision
            ):
                raise ValueError(
                    "Published provenance must preserve "
                    "the exact authority decision."
                )

            return

        if self.provenance is not None:
            raise ValueError(
                "Rejected authority production cannot "
                "carry provenance."
            )


class RuntimeGuiStepAuthorityProducer:
    """Trusted owner of authorization + provenance publication.

    Callers provide only the original human goal, candidate
    runtime plan, and confirmation callback.

    Callers cannot provide:
    - an authority decision,
    - a provenance object,
    - a step provenance,
    - a claimed authority classification.

    Every attempt clears the prior active provenance first.
    """

    def __init__(
        self,
        *,
        store,
    ):
        if (
            type(store)
            is not RuntimeGuiStepAuthorityProvenanceStore
        ):
            raise TypeError(
                "Exact runtime authority provenance "
                "store is required."
            )

        self._store = store

    def authorize_plan(
        self,
        *,
        goal,
        plan,
        confirmation_fn,
    ):
        self._store.clear()

        try:
            decision = (
                authorize_plan_gui_actions(
                    goal=goal,
                    plan=plan,
                    confirmation_fn=(
                        confirmation_fn
                    ),
                )
            )
        except Exception:
            decision = (
                GuiPlanAuthorityDecision(
                    allowed=False,
                    reason=(
                        "Runtime GUI authority "
                        "authorization failed."
                    ),
                )
            )

            return (
                RuntimeGuiStepAuthorityProduction(
                    decision=decision,
                    diagnostics=(
                        "authorization_failed",
                    ),
                )
            )

        if (
            type(decision)
            is not GuiPlanAuthorityDecision
        ):
            rejected = (
                GuiPlanAuthorityDecision(
                    allowed=False,
                    reason=(
                        "Runtime GUI authority returned "
                        "an invalid decision."
                    ),
                )
            )

            return (
                RuntimeGuiStepAuthorityProduction(
                    decision=rejected,
                    diagnostics=(
                        "invalid_authority_decision",
                    ),
                )
            )

        if not decision.allowed:
            return (
                RuntimeGuiStepAuthorityProduction(
                    decision=decision,
                    diagnostics=(
                        "authority_rejected",
                    ),
                )
            )

        try:
            provenance = (
                self._store._issue_authorized_plan(
                    plan,
                    goal,
                    decision,
                )
            )

        except Exception:
            self._store.clear()

            rejected = (
                GuiPlanAuthorityDecision(
                    allowed=False,
                    reason=(
                        "Runtime GUI authority provenance "
                        "could not be established."
                    ),
                )
            )

            return (
                RuntimeGuiStepAuthorityProduction(
                    decision=rejected,
                    diagnostics=(
                        "provenance_publication_failed",
                    ),
                )
            )

        return (
            RuntimeGuiStepAuthorityProduction(
                decision=decision,
                provenance=provenance,
                diagnostics=(),
            )
        )


RUNTIME_GUI_STEP_AUTHORITY = (
    RuntimeGuiStepAuthorityProvenanceStore()
)


RUNTIME_GUI_STEP_AUTHORITY_PRODUCER = (
    RuntimeGuiStepAuthorityProducer(
        store=(
            RUNTIME_GUI_STEP_AUTHORITY
        ),
    )
)
