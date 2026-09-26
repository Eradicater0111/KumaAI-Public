from __future__ import annotations

from app.agent.mission_controller import (
    MissionController,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)


class MissionRunner:
    """
    Coordinates mission progression with an execution callback.

    MissionRunner does not:
    - decide permissions
    - execute tools directly
    - call the LLM
    - invent execution results

    It asks an injected execution function to perform the
    currently selected mission step.
    """

    def __init__(
        self,
        controller: MissionController,
        execute_step,
        on_state_change=None,
    ):
        self.controller = controller
        self.execute_step = execute_step
        self.on_state_change = on_state_change

    # =====================================================
    # STATE EVENTS
    # =====================================================

    def _state_changed(self) -> None:
        """
        Notify the owner that mission state has changed.
        """

        if self.on_state_change is None:
            return

        self.on_state_change(
            self.controller
        )

    # =====================================================
    # CURRENT STEP
    # =====================================================

    def prepare_next_step(self):
        """
        Advance the mission to its next executable step.
        """

        step = self.controller.begin_next_step()

        if step is not None:
            self._state_changed()

        return step

    # =====================================================
    # EXECUTION
    # =====================================================

    def run_current_step(
        self,
    ) -> MissionExecutionResult:
        """
        Execute the currently active mission step.
        """

        step = self.controller.current_step()

        if step is None:

            return MissionExecutionResult(
                success=False,
                step_id="",
                error="No active mission step.",
            )

        try:

            execution = self.execute_step(
                step
            )

        except Exception as error:

            reason = str(
                error
            )

            self.controller.fail_current_step(
                reason
            )

            self._state_changed()

            return MissionExecutionResult(
                success=False,
                step_id=step.id,
                error=reason,
            )

        if not isinstance(
            execution,
            MissionExecutionResult,
        ):

            reason = (
                "Mission execution callback returned "
                "an invalid result."
            )

            self.controller.fail_current_step(
                reason
            )

            self._state_changed()

            return MissionExecutionResult(
                success=False,
                step_id=step.id,
                error=reason,
            )

        # -------------------------------------------------
        # RESUMABLE PARTIAL STATE
        # -------------------------------------------------
        #
        # RESUME is neither failure nor completion.
        #
        # Never repeat the failed operation here. Preserve the
        # active step and independently verified recovery evidence
        # for the mission layer.
        # -------------------------------------------------

        recovery_action = str(
            execution.recovery_action or ""
        ).strip().lower()

        if recovery_action == "resume":

            evidence = str(
                execution.recovery_evidence or ""
            ).strip()

            if not evidence:

                reason = (
                    "RESUME recovery result lacked verified "
                    "partial-state evidence."
                )

                self.controller.fail_current_step(
                    reason
                )

                self._state_changed()

                return MissionExecutionResult(
                    success=False,
                    step_id=step.id,
                    capability=execution.capability,
                    tool_name=execution.tool_name,
                    arguments=execution.arguments,
                    result=execution.result,
                    error=reason,
                    verified=False,
                    verification=execution.verification,
                    recovery_action="escalate",
                    recovery_reason=reason,
                )

            preserved = (
                self.controller
                .preserve_current_step_for_resume(
                    reason=execution.recovery_reason,
                    evidence=evidence,
                    tool_name=execution.tool_name,
                    arguments=execution.arguments,
                    capability=execution.capability,
                )
            )

            if not preserved:

                reason = (
                    "Mission runner could not preserve the "
                    "active step for safe resume."
                )

                self.controller.fail_current_step(
                    reason
                )

                self._state_changed()

                return MissionExecutionResult(
                    success=False,
                    step_id=step.id,
                    error=reason,
                    verified=False,
                    recovery_action="escalate",
                    recovery_reason=reason,
                )

            self._state_changed()

            return execution

        if not execution.success:

            self.controller.fail_current_step(
                execution.error
                or "Mission step failed."
            )

            self._state_changed()

            return execution

        if not execution.verified:

            reason = (
                execution.verification
                or "Mission step was not verified."
            )

            self.controller.fail_current_step(
                reason
            )
            self._state_changed()

            return MissionExecutionResult(
                success=False,
                step_id=step.id,
                tool_name=execution.tool_name,
                arguments=execution.arguments,
                result=execution.result,
                error=reason,
                verified=False,
                verification=execution.verification,
            )

        self.controller.complete_current_step(
            result=execution.result,
            tool_name=execution.tool_name,
            arguments=execution.arguments,
        )
        self._state_changed()

        return execution

    # =====================================================
    # MISSION
    # =====================================================

    def run_next_step(self):
        """
        Prepare and execute the next available mission step.
        """

        step = self.prepare_next_step()

        if step is None:

            return MissionExecutionResult(
                success=False,
                step_id="",
                error=(
                    "No executable mission step "
                    "is currently available."
                ),
            )

        return self.run_current_step()

        # =====================================================
    # FULL MISSION
    # =====================================================

    def run_mission(self):
        """
        Execute the mission one dependency-aware step at a time.

        Stops immediately when:
        - a step fails,
        - a step cannot be executed,
        - the mission is complete.

        Returns the most recent MissionExecutionResult.
        """

        last_result = None

        while True:

            if self.mission_complete():
                return last_result

            step = self.prepare_next_step()

            if step is None:

                return MissionExecutionResult(
                    success=False,
                    step_id="",
                    error=(
                        "Mission cannot progress: "
                        "no executable step is available."
                    ),
                )

            result = self.run_current_step()

            last_result = result

            if not result.completed:
                return result

            if self.mission_complete():
                return result

    def mission_complete(self) -> bool:
        """
        Return whether the complete mission is finished.
        """

        if not self.controller.is_complete():
            return False

        self.controller.mark_complete()

        return True