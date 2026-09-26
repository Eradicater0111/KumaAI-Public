from __future__ import annotations

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)
from app.agent.task_state import TaskState


class MissionController:
    """
    Coordinates a KUMA GoalPlan with its TaskState.

    This class does not:
    - call the LLM
    - select tools
    - execute tools
    - grant permissions

    It only maintains mission progress.
    """

    def __init__(
        self,
        goal: str,
        plan: GoalPlan | None = None,
    ):
        self.task_state = TaskState(
            goal=goal
        )

        self.plan = plan

        self._sync_plan_state()

    @classmethod
    def from_mission_state(
        cls,
        mission_state,
    ) -> "MissionController":
        """
        Reconstruct a live mission controller from durable state.

        The persisted GoalPlan is authoritative. No new plan is
        generated here.
        """

        if mission_state is None:
            raise ValueError(
                "MissionState is required."
            )

        plan = getattr(
            mission_state,
            "plan",
            None,
        )

        if plan is None:
            raise ValueError(
                "MissionState does not contain a GoalPlan."
            )

        goal = str(
            getattr(
                mission_state,
                "goal",
                "",
            )
            or ""
        ).strip()

        if not goal:
            raise ValueError(
                "MissionState does not contain a goal."
            )

        if plan.goal.strip() != goal:
            raise ValueError(
                "Persisted GoalPlan goal does not match "
                "the mission goal."
            )

        valid, error = plan.validate()

        if not valid:
            raise ValueError(
                error
                or "Persisted GoalPlan is invalid."
            )

        controller = cls(
            goal=goal,
        )

        controller.plan = plan

        # Restore the live task state from durable mission data.
        controller.task_state.current_step = (
            f"Mission step: {plan.current_step_id} — "
            f"{plan.get_step(plan.current_step_id).objective}"
            if (
                plan.current_step_id
                and plan.get_step(
                    plan.current_step_id
                ) is not None
            )
            else ""
        )

        controller.task_state.completed_steps = [
            f"{step.id}: {step.objective}"
            for step in plan.steps
            if step.status == StepStatus.COMPLETED
        ]

        controller.task_state.failures = list(
            getattr(
                mission_state,
                "failures",
                [],
            )
            or []
        )

        controller.task_state.observations = list(
            getattr(
                mission_state,
                "observations",
                [],
            )
            or []
        )

        controller.task_state.action_history = list(
            getattr(
                mission_state,
                "action_history",
                [],
            )
            or []
        )

        controller.task_state.last_evidence = (
            getattr(
                mission_state,
                "last_evidence",
                "",
            )
            or ""
        )

        if bool(
            getattr(
                mission_state,
                "continuation_guard_known",
                False,
            )
        ):

            controller.task_state.set_continuation_guard_action(
                tool_name=getattr(
                    mission_state,
                    "continuation_guard_tool",
                    "",
                ),
                arguments=getattr(
                    mission_state,
                    "continuation_guard_arguments",
                    {},
                ),
                capability=getattr(
                    mission_state,
                    "continuation_guard_capability",
                    "",
                ),
            )

        else:

            controller.task_state.clear_continuation_guard_action()

        controller.task_state.continuation_verification_pending = (
            bool(
                getattr(
                    mission_state,
                    "continuation_verification_pending",
                    False,
                )
            )
        )

        controller.task_state.continuation_execution_inflight = (
            bool(
                getattr(
                    mission_state,
                    "continuation_execution_inflight",
                    False,
                )
            )
        )

        controller.task_state.recovery_continuation_cycles = (
            getattr(
                mission_state,
                "recovery_continuation_cycles",
                0,
            )
        )

        status = getattr(
            mission_state,
            "status",
            None,
        )

        controller.task_state.finished = (
            status is not None
            and getattr(
                status,
                "value",
                "",
            ) == "completed"
        )

        persisted_remaining_objective = str(
            getattr(
                mission_state,
                "remaining_objective",
                "",
            )
            or ""
        ).strip()

        if persisted_remaining_objective:

            controller.task_state.set_remaining_objective(
                persisted_remaining_objective
            )

        elif plan.current_step_id:

            current = plan.get_step(
                plan.current_step_id
            )

            paused_partial_step = (
                current is not None
                and current.status
                == StepStatus.IN_PROGRESS
                and status is not None
                and getattr(
                    status,
                    "value",
                    "",
                )
                == "paused"
            )

            # A paused partial step must wait for the bounded
            # remaining-objective resolver. Reusing the original
            # objective here could accidentally turn RESUME into
            # replay.
            if (
                current is not None
                and not paused_partial_step
            ):
                controller.task_state.set_remaining_objective(
                    current.objective
                )

        elif not controller.task_state.finished:

            next_step = plan.next_pending_step()

            if next_step is not None:
                controller.task_state.set_remaining_objective(
                    next_step.objective
                )

        return controller

    # =====================================================
    # PLAN
    # =====================================================

    def set_plan(
        self,
        plan: GoalPlan,
    ) -> tuple[bool, str | None]:
        """
        Attach and validate a mission plan.
        """

        valid, error = plan.validate()

        if not valid:
            return False, error

        if plan.goal.strip() != self.task_state.goal.strip():
            return (
                False,
                "GoalPlan goal does not match the mission goal.",
            )

        self.plan = plan

        self._sync_plan_state()

        return True, None

    # =====================================================
    # CURRENT STEP
    # =====================================================

    def current_step(self) -> GoalStep | None:
        """
        Return the currently active step.
        """

        if self.plan is None:
            return None

        if self.plan.current_step_id:
            return self.plan.get_step(
                self.plan.current_step_id
            )

        return None

    def next_step(self) -> GoalStep | None:
        """
        Return the next executable plan step.
        """

        if self.plan is None:
            return None

        return self.plan.next_pending_step()

    def begin_next_step(self) -> GoalStep | None:
        """
        Mark the next executable step as in progress.
        """

        step = self.next_step()

        if step is None:
            return None

        if self.plan is None:
            return None

        step.status = StepStatus.IN_PROGRESS

        self.plan.current_step_id = step.id

        self.task_state.current_step = (
            f"Mission step: {step.id} — "
            f"{step.objective}"
        )

        self.task_state.set_remaining_objective(
            step.objective
        )

        return step

    # =====================================================
    # STEP COMPLETION
    # =====================================================

    def complete_current_step(
        self,
        result: str,
        tool_name: str | None = None,
        arguments: dict | None = None,
    ) -> bool:
        """
        Mark the current plan step as completed after verified execution.

        The actual capability/tool execution details may be supplied
        by the runtime so TaskState records authoritative execution
        facts rather than inventing them.
        """

        step = self.current_step()

        if step is None:
            return False

        step.status = StepStatus.COMPLETED

        step.result = str(
            result or ""
        )

        self.task_state.record_action(
            tool_name=(
                str(tool_name)
                if tool_name
                else step.id
            ),
            arguments=(
                dict(arguments)
                if arguments is not None
                else {}
            ),
            result=result,
            verified=True,
        )

        self.task_state.complete_step(
            f"{step.id}: {step.objective}"
        )

        self.task_state.reset_recovery_continuation_cycles()

        # The completed step is no longer the active step.
        #
        # Leaving current_step_id populated would make
        # controller.current_step() return a COMPLETED step
        # and would persist stale active-step state.
        if (
            self.plan is not None
            and self.plan.current_step_id == step.id
        ):
            self.plan.current_step_id = ""

        self._sync_plan_state()

        return True

    def complete_current_step_from_verification(
        self,
        *,
        result: str,
        evidence: str = "",
        reason: str = "",
    ) -> bool:
        """
        Complete the active GoalStep from independent objective
        verification.

        This method records NO new tool execution.

        The continuation action was already recorded when it
        actually executed. Objective verification proves the
        original step's end-state; it is not another action.
        """

        step = self.current_step()

        if step is None:
            return False

        if step.status != StepStatus.IN_PROGRESS:
            return False

        result = str(
            result or ""
        ).strip()

        evidence = str(
            evidence or ""
        ).strip()

        reason = str(
            reason or ""
        ).strip()

        step.status = StepStatus.COMPLETED

        step.result = (
            result
            or evidence
            or reason
        )

        if reason:
            step.reason = reason

        if evidence:
            self.task_state.set_evidence(
                evidence
            )

        self.task_state.complete_step(
            f"{step.id}: {step.objective}"
        )

        self.task_state.clear_remaining_objective()

        self.task_state.clear_continuation_guard_action()

        self.task_state.clear_continuation_verification_pending()

        self.task_state.clear_continuation_execution_inflight()

        self.task_state.reset_recovery_continuation_cycles()

        self.task_state.add_observation(
            "Original mission-step objective independently "
            "verified as satisfied."
        )

        if (
            self.plan is not None
            and self.plan.current_step_id == step.id
        ):
            self.plan.current_step_id = ""

        self._sync_plan_state()

        return True

    # =====================================================
    # RESUMABLE PARTIAL STATE
    # =====================================================

    def preserve_current_step_for_resume(
        self,
        *,
        reason: str,
        evidence: str,
        tool_name: str = "",
        arguments: dict | None = None,
        capability: str = "",
    ) -> bool:
        """
        Preserve the active step after independently verified
        partial execution.

        This does not complete, retry, or replan the step.
        """

        step = self.current_step()

        if step is None:
            return False

        if step.status != StepStatus.IN_PROGRESS:
            return False

        evidence = str(
            evidence or ""
        ).strip()

        if not evidence:
            return False

        reason = str(
            reason or ""
        ).strip()

        # Keep the exact current step active.
        step.status = StepStatus.IN_PROGRESS

        if reason:
            step.reason = reason

            self.task_state.add_observation(
                "Recovery resume: "
                f"{reason}"
            )

        self.task_state.set_evidence(
            evidence
        )

        self.task_state.set_continuation_guard_action(
            tool_name=tool_name,
            arguments=arguments,
            capability=capability,
        )

        self.task_state.clear_continuation_verification_pending()

        self.task_state.clear_continuation_execution_inflight()

        # The original GoalStep objective is not automatically
        # equivalent to the unfinished remainder after partial
        # execution.
        #
        # A dedicated reasoning boundary resolves that later.
        self.task_state.clear_remaining_objective()

        return True

    # =====================================================
    # FAILURE
    # =====================================================

    def fail_current_step(
        self,
        reason: str,
    ) -> bool:
        """
        Mark the current plan step as failed.
        """

        step = self.current_step()

        if step is None:
            return False

        reason = str(
            reason or ""
        ).strip()

        step.status = StepStatus.FAILED
        step.reason = reason

        self.task_state.record_failure(
    reason
)

        self.task_state.current_step = ""

        self._sync_plan_state()

        return True

    # =====================================================
    # COMPLETION
    # =====================================================

    def is_complete(self) -> bool:
        """
        Determine whether every planned step has completed.
        """

        if self.plan is None:
            return False

        return self.plan.is_complete()

    def mark_complete(self) -> None:
        """
        Mark the mission complete when the plan is fully satisfied.
        """

        if self.plan is not None:
            self.plan.current_step_id = ""

        self.task_state.mark_finished()

    # =====================================================
    # INTERNAL SYNCHRONIZATION
    # =====================================================

    def _sync_plan_state(self) -> None:
        """
        Keep plan/task state aligned.
        """

        if self.plan is None:
            return

        if self.plan.current_step_id:
            return

        if self.plan.is_complete():
            self.task_state.mark_finished()
            return

        next_step = self.plan.next_pending_step()

        if next_step is not None:
            self.task_state.set_remaining_objective(
                next_step.objective
            )

    # =====================================================
    # SUMMARY
    # =====================================================

    def summary(self) -> str:
        """
        Produce a combined mission view.
        """

        lines = [
            "KUMA MISSION CONTROLLER",
            "",
            self.plan.summary()
            if self.plan is not None
            else "Goal plan: not initialized.",
            "",
            self.task_state.summary(),
        ]

        return "\n".join(lines)
    