from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class GoalStep:

    id: str
    objective: str

    status: StepStatus = StepStatus.PENDING
    result: str = ""
    reason: str = ""

    dependencies: list[str] = field(
        default_factory=list
    )

    success_criteria: list[str] = field(
        default_factory=list
    )

    required_capabilities: list[str] = field(
        default_factory=list
    )

    planned_tool: str = ""

    # Planner-owned, untrusted STEP-LOCAL semantic GUI target
    # requirements.
    #
    # This contains no observation identity, geometry, permission,
    # attestation, or execution authority. MissionService must parse
    # it through StructuredUITargetIntent before it can participate
    # in the B8 evidence chain.
    #
    # A synthetic recovery step with a newly resolved objective must
    # never inherit this field from the original GoalStep.
    gui_target_intent: dict[str, Any] | None = None

    # Trusted runtime metadata.
    # The planner does not assign this field.
    gui_authority: str = ""

    # Original human mission goal bound by trusted runtime
    # after plan acceptance. Planner output is not allowed
    # to assign this field.
    gui_authority_goal: str = ""

    risk_level: str = "normal"

    artifacts: list[str] = field(
        default_factory=list
    )

    verification_requirements: list[str] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "objective": self.objective,
            "status": self.status.value,
            "result": self.result,
            "reason": self.reason,
            "dependencies": list(
                self.dependencies
            ),
            "success_criteria": list(
                self.success_criteria
            ),
            "required_capabilities": list(
                self.required_capabilities
            ),
            "planned_tool": self.planned_tool,
            # Planner-owned semantic metadata is durable because it
            # is explicitly untrusted and grants no runtime authority.
            "gui_target_intent": (
                dict(self.gui_target_intent)
                if type(self.gui_target_intent) is dict
                else None
            ),
            # GUI authority is trusted runtime metadata. It is
            # deliberately excluded from durable/planner-shaped
            # serialization and must be re-derived after restore.
            "risk_level": self.risk_level,
            "artifacts": list(
                self.artifacts
            ),
            "verification_requirements": list(
                self.verification_requirements
            ),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "GoalStep":

        if not isinstance(data, dict):
            raise ValueError(
                "GoalStep data must be a dictionary."
            )

        step_id = str(
            data.get("id", "")
            or ""
        ).strip()

        objective = str(
            data.get("objective", "")
            or ""
        ).strip()

        if not step_id:
            raise ValueError(
                "GoalStep requires an ID."
            )

        if not objective:
            raise ValueError(
                f"GoalStep '{step_id}' requires an objective."
            )

        raw_status = str(
            data.get(
                "status",
                StepStatus.PENDING.value,
            )
        )

        try:
            status = StepStatus(
                raw_status
            )
        except ValueError as error:
            raise ValueError(
                f"Invalid step status: {raw_status}"
            ) from error

        def string_list(value) -> list[str]:
            if not isinstance(value, list):
                return []

            return [
                str(item).strip()
                for item in value
            ]

        return cls(
            id=step_id,
            objective=objective,
            status=status,
            result=str(
                data.get(
                    "result",
                    "",
                )
                or ""
            ),
            reason=str(
                data.get(
                    "reason",
                    "",
                )
                or ""
            ),
            dependencies=string_list(
                data.get(
                    "dependencies",
                    [],
                )
            ),
            success_criteria=string_list(
                data.get(
                    "success_criteria",
                    [],
                )
            ),
            required_capabilities=string_list(
                data.get(
                    "required_capabilities",
                    [],
                )
            ),
            planned_tool=str(
                data.get(
                    "planned_tool",
                    "",
                )
                or ""
            ).strip(),
            # Restored semantic intent remains untrusted planner
            # metadata. Runtime B8 parsing revalidates its strict
            # shape before it can become evidence.
            gui_target_intent=(
                dict(data.get("gui_target_intent"))
                if type(data.get("gui_target_intent")) is dict
                else None
            ),
            # Persisted/planner-shaped authority fields are
            # intentionally ignored. Runtime authority must be
            # re-derived from the trusted mission goal.
            gui_authority="",
            gui_authority_goal="",
            risk_level=str(
                data.get(
                    "risk_level",
                    "normal",
                )
                or "normal"
            ).strip().lower(),
            artifacts=string_list(
                data.get(
                    "artifacts",
                    [],
                )
            ),
            verification_requirements=string_list(
                data.get(
                    "verification_requirements",
                    [],
                )
            ),
        )


@dataclass
class GoalPlan:
    """
    Structured decomposition of a user's larger objective.

    GoalPlan is planning state, not permission to execute.
    """

    goal: str

    steps: list[GoalStep] = field(
        default_factory=list
    )

    current_step_id: str = ""

    def get_step(
        self,
        step_id: str,
    ) -> GoalStep | None:
        """
        Find a step by ID.
        """

        for step in self.steps:

            if step.id == step_id:
                return step

        return None

    def add_step(
        self,
        step: GoalStep,
    ) -> None:
        """
        Add a step to the plan.
        """

        self.steps.append(step)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "current_step_id": self.current_step_id,
            "steps": [
                step.to_dict()
                for step in self.steps
            ],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "GoalPlan":

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "GoalPlan data must be a dictionary."
            )

        goal = str(
            data.get("goal", "")
            or ""
        ).strip()

        if not goal:
            raise ValueError(
                "GoalPlan requires a goal."
            )

        raw_steps = data.get(
            "steps",
            [],
        )

        if not isinstance(
            raw_steps,
            list,
        ):
            raise ValueError(
                "GoalPlan steps must be a list."
            )

        plan = cls(
            goal=goal
        )

        plan.current_step_id = str(
            data.get(
                "current_step_id",
                "",
            )
            or ""
        ).strip()

        for raw_step in raw_steps:
            plan.add_step(
                GoalStep.from_dict(
                    raw_step
                )
            )

        valid, error = plan.validate()

        if not valid:
            raise ValueError(
                error
                or "Invalid GoalPlan."
            )

        if (
            plan.current_step_id
            and plan.get_step(
                plan.current_step_id
            ) is None
        ):
            raise ValueError(
                "GoalPlan current_step_id references "
                "an unknown step."
            )

        return plan

    def to_json(self) -> str:
        import json

        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
        )

    @classmethod
    def from_json(
        cls,
        payload: str,
    ) -> "GoalPlan":
        import json

        return cls.from_dict(
            json.loads(payload)
        )

    def is_complete(self) -> bool:
        """
        A plan is complete only when every step is completed.
        """

        if not self.steps:
            return False

        return all(
            step.status
            == StepStatus.COMPLETED
            for step in self.steps
        )

    def next_pending_step(self) -> GoalStep | None:
        """
        Find the next executable pending step while respecting
        dependencies.
        """

        completed_ids = {
            step.id
            for step in self.steps
            if step.status
            == StepStatus.COMPLETED
        }

        for step in self.steps:

            if step.status != StepStatus.PENDING:
                continue

            if all(
                dependency in completed_ids
                for dependency in step.dependencies
            ):
                return step

        return None

    def validate(self) -> tuple[bool, str | None]:
        """
        Validate the structural integrity of the plan.

        This does not authorize any capability.
        """

        if not self.goal.strip():
            return (
                False,
                "GoalPlan requires a goal.",
            )

        if not self.steps:
            return (
                False,
                "GoalPlan requires at least one step.",
            )

        ids = {
            step.id
            for step in self.steps
        }

        if "" in ids:
            return (
                False,
                "Every goal step requires an ID.",
            )

        if len(ids) != len(self.steps):
            return (
                False,
                "GoalPlan contains duplicate step IDs.",
            )

        for step in self.steps:

            if not step.objective.strip():
                return (
                    False,
                    f"Step '{step.id}' has no objective.",
                )

            if not step.risk_level.strip():
                return (
                    False,
                    f"Step '{step.id}' has no risk level.",
                )

            allowed_risk_levels = {
                "low",
                "normal",
                "high",
                "critical",
            }

            if step.risk_level not in allowed_risk_levels:
                return (
                    False,
                    f"Step '{step.id}' has invalid "
                    f"risk level '{step.risk_level}'.",
                )

            for capability in step.required_capabilities:

                if not str(capability).strip():
                    return (
                        False,
                        f"Step '{step.id}' contains an "
                        "empty capability.",
                    )

            for criterion in step.success_criteria:

                if not str(criterion).strip():
                    return (
                        False,
                        f"Step '{step.id}' contains an "
                        "empty success criterion.",
                    )

            for requirement in (
                step.verification_requirements
            ):

                if not str(requirement).strip():
                    return (
                        False,
                        f"Step '{step.id}' contains an "
                        "empty verification requirement.",
                    )

            for artifact in step.artifacts:

                if not str(artifact).strip():
                    return (
                        False,
                        f"Step '{step.id}' contains an "
                        "empty artifact.",
                    )

            for dependency in step.dependencies:

                if dependency not in ids:
                    return (
                        False,
                        f"Step '{step.id}' references unknown "
                        f"dependency '{dependency}'.",
                    )

                if dependency == step.id:
                    return (
                        False,
                        f"Step '{step.id}' cannot depend on itself.",
                    )

        return True, None

    def summary(self) -> str:
        """
        Human-readable representation of the mission.
        """

        lines = [
            "KUMA GOAL PLAN",
            f"Goal: {self.goal}",
            f"Current step: "
            f"{self.current_step_id or 'none'}",
            "",
            "Steps:",
        ]

        for index, step in enumerate(
            self.steps,
            start=1,
        ):

            lines.append(
                f"{index}. "
                f"[{step.status.value}] "
                f"{step.id}: "
                f"{step.objective}"
            )

            if step.dependencies:
                lines.append(
                    "   Dependencies: "
                    + ", ".join(
                        step.dependencies
                    )
                )

            if step.success_criteria:
                lines.append(
                    "   Success criteria:"
                )

                for criterion in step.success_criteria:
                    lines.append(
                        f"   - {criterion}"
                    )

            if step.required_capabilities:
                lines.append(
                    "   Capabilities: "
                    + ", ".join(
                        step.required_capabilities
                    )
                )

            if step.risk_level:
                lines.append(
                    f"   Risk: {step.risk_level}"
                )

            if step.artifacts:
                lines.append(
                    "   Artifacts: "
                    + ", ".join(
                        step.artifacts
                    )
                )

            if step.verification_requirements:
                lines.append(
                    "   Verification:"
                )

                for requirement in (
                    step.verification_requirements
                ):
                    lines.append(
                        f"   - {requirement}"
                    )

        return "\n".join(lines)