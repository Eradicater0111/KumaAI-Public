from __future__ import annotations

from collections import deque

from app.agent.goal_plan import GoalPlan, StepStatus


class PlannerQualityGate:
    """
    Deterministic quality checks for LLM-generated GoalPlans.

    This layer does not execute tools and does not grant permissions.
    It only decides whether a plan is structurally and operationally
    coherent enough to enter the mission runtime.
    """

    DEFAULT_MAX_STEPS = 50

    def __init__(
        self,
        available_capabilities: set[str] | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
    ):
        self.available_capabilities = set(
            available_capabilities or set()
        )

        self.max_steps = int(max_steps)

    def validate(
        self,
        plan: GoalPlan,
    ) -> tuple[bool, list[str]]:
        """
        Validate a complete GoalPlan.

        Returns:
            (accepted, reasons)
        """

        reasons: list[str] = []

        valid, error = plan.validate()

        if not valid:
            reasons.append(error or "GoalPlan validation failed.")

        if len(plan.steps) > self.max_steps:
            reasons.append(
                f"Plan contains {len(plan.steps)} steps; "
                f"maximum allowed is {self.max_steps}."
            )

        self._check_goal(plan, reasons)
        self._check_step_quality(plan, reasons)
        self._check_dependencies(plan, reasons)
        self._check_capabilities(plan, reasons)
        self._check_dependency_cycles(plan, reasons)

        return (
            len(reasons) == 0,
            reasons,
        )

    # =====================================================
    # GOAL
    # =====================================================

    @staticmethod
    def _check_goal(
        plan: GoalPlan,
        reasons: list[str],
    ) -> None:

        if not plan.goal.strip():
            reasons.append(
                "Plan goal is empty."
            )

    # =====================================================
    # STEP QUALITY
    # =====================================================

    @staticmethod
    def _check_step_quality(
        plan: GoalPlan,
        reasons: list[str],
    ) -> None:

        for step in plan.steps:

            if not step.objective.strip():
                reasons.append(
                    f"Step '{step.id}' has no objective."
                )

            if not step.success_criteria:
                reasons.append(
                    f"Step '{step.id}' has no success criteria."
                )

            if not step.verification_requirements:
                reasons.append(
                    f"Step '{step.id}' has no verification "
                    "requirements."
                )

            if not step.artifacts:
                reasons.append(
                    f"Step '{step.id}' has no declared artifacts."
                )

    # =====================================================
    # DEPENDENCIES
    # =====================================================

    @staticmethod
    def _check_dependencies(
        plan: GoalPlan,
        reasons: list[str],
    ) -> None:

        ids = {
            step.id
            for step in plan.steps
        }

        for step in plan.steps:

            for dependency in step.dependencies:

                if dependency not in ids:
                    reasons.append(
                        f"Step '{step.id}' depends on unknown "
                        f"step '{dependency}'."
                    )

                if dependency == step.id:
                    reasons.append(
                        f"Step '{step.id}' depends on itself."
                    )

    # =====================================================
    # CAPABILITIES
    # =====================================================

    def _check_capabilities(
        self,
        plan: GoalPlan,
        reasons: list[str],
    ) -> None:

        if not self.available_capabilities:
            return

        for step in plan.steps:

            for capability in step.required_capabilities:

                if capability not in self.available_capabilities:
                    reasons.append(
                        f"Step '{step.id}' requires unavailable "
                        f"capability '{capability}'."
                    )

    # =====================================================
    # CYCLE DETECTION
    # =====================================================

    @staticmethod
    def _check_dependency_cycles(
        plan: GoalPlan,
        reasons: list[str],
    ) -> None:

        graph = {
            step.id: list(step.dependencies)
            for step in plan.steps
        }

        indegree = {
            step.id: 0
            for step in plan.steps
        }

        reverse_graph = {
            step.id: []
            for step in plan.steps
        }

        for step in plan.steps:

            for dependency in step.dependencies:

                if dependency not in indegree:
                    continue

                indegree[step.id] += 1

                reverse_graph[
                    dependency
                ].append(step.id)

        queue = deque(
            step_id
            for step_id, degree in indegree.items()
            if degree == 0
        )

        visited = 0

        while queue:

            current = queue.popleft()
            visited += 1

            for dependent in reverse_graph[current]:

                indegree[dependent] -= 1

                if indegree[dependent] == 0:
                    queue.append(dependent)

        if visited != len(graph):
            reasons.append(
                "GoalPlan contains a dependency cycle."
            )