from __future__ import annotations

import json
from typing import Any

from ollama import chat

from app.agent.capability_registry import (
    CapabilityRegistry,
    create_default_capability_registry,
)
from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)
from app.agent.gui_action_grounding import (
    MISSION_SEMANTIC_TARGET_TOOLS,
    validate_planned_tool_binding,
)

from app.agent.gui_target_intent import (
    StructuredUITargetIntent,
)


PLANNED_SEMANTIC_TARGET_TOOLS = frozenset(
    set(
        MISSION_SEMANTIC_TARGET_TOOLS
    )
    | {
        "type_text",
    }
)


class GoalDecomposer:
    """
    Converts a complex natural-language goal into a validated GoalPlan.

    This component plans only.

    It does not:
    - execute tools
    - select permissions
    - execute shell commands
    - interact with the computer
    """

    def __init__(
        self,
        model: str = "qwen3:8b",
        capability_registry: CapabilityRegistry | None = None,
    ):
        self.model = model

        self.capability_registry = (
            capability_registry
            or create_default_capability_registry()
        )

    # =====================================================
    # MODEL CALL
    # =====================================================

    def call_model(
        self,
        goal: str,
    ):
        """
        Ask the model to decompose the goal into structured JSON.

        The model may select only capabilities exposed by KUMA's
        capability registry.
        """

        capability_description = (
            self.capability_registry.describe()
        )

        prompt = f"""
You are KUMA's mission decomposition engine.

Convert the user's goal into a structured execution plan.

USER GOAL:
{goal}

AVAILABLE KUMA CAPABILITIES:

{capability_description}

IMPORTANT CAPABILITY RULES:

1. required_capabilities MUST contain only capability names
   from the AVAILABLE KUMA CAPABILITIES section.
2. Do not use programming languages, skills, expertise,
   human roles, knowledge domains, or vague descriptions
   as capability names.
3. Never invent a capability.
4. If a capability is unavailable, do not use it.
5. The capability list describes semantic abilities.
   The listed tools are the runtime mechanisms behind them.
6. If a step's capabilities expose a physical GUI action,
   planned_tool MUST name exactly one of those exposed GUI tools.
7. A runtime tool must never be invented.
8. For steps that require no GUI action, planned_tool may be
   an empty string.

GUI TARGET INTENT RULES:

- A step whose planned_tool is "click_vision",
  "move_mouse_vision", "type_text", or "hold_mouse_vision" MUST include
  gui_target_intent describing
  the semantic native UI target.
- gui_target_intent is UNTRUSTED planner metadata only.
- It may contain only:
  role, subrole, text, require_enabled, require_positive_area.
- It MUST NOT contain coordinates, observation IDs, AX paths,
  geometry, permission, authorization, attestation, verification
  state, or execution claims.
- Steps not using a trusted semantic target tool should use
  null or omit the field.

Return ONLY valid JSON.

Required structure:

{{
  "goal": "string",
  "steps": [
    {{
      "id": "unique_step_id",
      "objective": "clear objective",
      "dependencies": ["step_id"],
      "success_criteria": ["criterion"],
      "required_capabilities": ["capability_name"],
      "planned_tool": "tool_name_or_empty_string",
      "gui_target_intent": null,
      "risk_level": "low|normal|high|critical",
      "artifacts": ["artifact"],
      "verification_requirements": ["requirement"]
    }}
  ]
}}

Rules:

1. The plan must contain at least one step.
2. Every step must have a unique ID.
3. Dependencies must reference valid step IDs.
4. Do not create self-dependencies.
5. Objectives must describe concrete work.
6. Success criteria must describe observable completion conditions.
7. Verification requirements must describe how completion can be checked.
8. Required capabilities must come ONLY from the capability registry.
9. Do not execute anything.
10. Do not invent execution results.
11. Do not claim the user's goal is already complete.
12. Prefer a small number of meaningful steps rather than hundreds
    of trivial steps.
"""

        return chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            tools=[],
            think=False,
            options={
                "num_ctx": 4096,
                "temperature": 0.0,
            },
        )

    # =====================================================
    # PARSER
    # =====================================================

    @staticmethod
    def parse_plan(
    raw_response: Any,
    capability_registry=None,
) -> tuple[GoalPlan | None, str | None]:
        """
        Parse and validate model-produced planning JSON.
        """

        if capability_registry is None:
            from app.agent.capability_registry import (
                create_default_capability_registry,
            )

            capability_registry = (
                create_default_capability_registry()
            )

        if raw_response is None:
            return (
                None,
                "Goal decomposition response was empty.",
            )

        if isinstance(
            raw_response,
            str,
        ):
            text = raw_response.strip()

        else:
            message = getattr(
                raw_response,
                "message",
                raw_response,
            )

            content = getattr(
                message,
                "content",
                message,
            )

            text = str(
                content or ""
            ).strip()

        if not text:
            return (
                None,
                "Goal decomposition response was empty.",
            )

        try:

            data = json.loads(
                text
            )

        except json.JSONDecodeError as error:

            return (
                None,
                "Goal decomposition was not valid JSON: "
                f"{error}",
            )

        if not isinstance(
            data,
            dict,
        ):

            return (
                None,
                "Goal decomposition must be a JSON object.",
            )

        raw_goal = str(
            data.get(
                "goal",
                "",
            ) or ""
        ).strip()

        if not raw_goal:
            return (
                None,
                "Goal decomposition is missing its goal.",
            )

        raw_steps = data.get(
            "steps"
        )

        if not isinstance(
            raw_steps,
            list,
        ):

            return (
                None,
                "Goal decomposition must contain a steps list.",
            )

        available_capabilities = (
            capability_registry.names()
        )

        plan = GoalPlan(
            goal=raw_goal
        )

        for index, raw_step in enumerate(
            raw_steps,
            start=1,
        ):

            if not isinstance(
                raw_step,
                dict,
            ):

                return (
                    None,
                    f"Goal step {index} must be an object.",
                )

            step_id = str(
                raw_step.get(
                    "id",
                    "",
                ) or ""
            ).strip()

            objective = str(
                raw_step.get(
                    "objective",
                    "",
                ) or ""
            ).strip()

            dependencies = GoalDecomposer._string_list(
                raw_step.get(
                    "dependencies",
                    [],
                )
            )

            success_criteria = GoalDecomposer._string_list(
                raw_step.get(
                    "success_criteria",
                    [],
                )
            )

            required_capabilities = GoalDecomposer._string_list(
                raw_step.get(
                    "required_capabilities",
                    [],
                )
            )

            unknown_capabilities = [
                capability
                for capability in required_capabilities
                if capability
                not in available_capabilities
            ]

            if unknown_capabilities:
                return (
                    None,
                    f"Goal step {index} requires unavailable "
                    f"capabilities: "
                    f"{', '.join(unknown_capabilities)}.",
                )

            raw_planned_tool = raw_step.get(
                "planned_tool",
                "",
            )

            if (
                raw_planned_tool is not None
                and type(raw_planned_tool) is not str
            ):
                return (
                    None,
                    f"Goal step {index} planned_tool must "
                    "be a string.",
                )

            planned_tool = (
                str(
                    raw_planned_tool
                    or ""
                )
                .strip()
            )

            binding_valid, binding_error = (
                validate_planned_tool_binding(
                    capability_registry,
                    required_capabilities,
                    planned_tool,
                )
            )

            if not binding_valid:
                return (
                    None,
                    f"Goal step {index} has invalid tool "
                    f"grounding: {binding_error}",
                )

            raw_gui_target_intent = raw_step.get(
                "gui_target_intent",
                None,
            )

            gui_target_intent = None

            if (
                planned_tool == "type_text"
                and raw_gui_target_intent is None
            ):
                return (
                    None,
                    (
                        f"Goal step {index} type_text "
                        "requires gui_target_intent describing "
                        "the intended semantic text target."
                    ),
                )

            if raw_gui_target_intent is not None:

                if planned_tool not in PLANNED_SEMANTIC_TARGET_TOOLS:
                    return (
                        None,
                        (
                            f"Goal step {index} supplies "
                            "gui_target_intent without "
                            "a trusted semantic target tool."
                        ),
                    )

                try:
                    parsed_gui_target_intent = (
                        StructuredUITargetIntent.from_dict(
                            raw_gui_target_intent
                        )
                    )
                except Exception as error:
                    return (
                        None,
                        (
                            f"Goal step {index} "
                            "gui_target_intent is invalid: "
                            f"{error}"
                        ),
                    )

                gui_target_intent = (
                    parsed_gui_target_intent.to_dict()
                )

            artifacts = GoalDecomposer._string_list(
                raw_step.get(
                    "artifacts",
                    [],
                )
            )

            verification_requirements = (
                GoalDecomposer._string_list(
                    raw_step.get(
                        "verification_requirements",
                        [],
                    )
                )
            )

            risk_level = str(
                raw_step.get(
                    "risk_level",
                    "normal",
                ) or "normal"
            ).strip().lower()

            plan.add_step(
                GoalStep(
                    id=step_id,
                    objective=objective,
                    status=StepStatus.PENDING,
                    dependencies=dependencies,
                    success_criteria=success_criteria,
                    required_capabilities=required_capabilities,
                    planned_tool=planned_tool,
                    gui_target_intent=gui_target_intent,
                    risk_level=risk_level,
                    artifacts=artifacts,
                    verification_requirements=(
                        verification_requirements
                    ),
                )
            )

        if plan.goal.strip() != raw_goal.strip():
            return (
                None,
                "Goal decomposition goal mismatch.",
            )

        valid, error = plan.validate()

        if not valid:
            return (
                None,
                error,
            )

        return (
            plan,
            None,
        )

    # =====================================================
    # HELPERS
    # =====================================================

    @staticmethod
    def _string_list(
        value: Any,
    ) -> list[str]:
        """
        Normalize a list-like JSON field into a list of strings.
        """

        if value is None:
            return []

        if not isinstance(
            value,
            list,
        ):
            return []

        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    # =====================================================
    # DECOMPOSE
    # =====================================================

    def decompose(
        self,
        goal: str,
    ) -> tuple[GoalPlan | None, str | None]:

        goal = str(
            goal or ""
        ).strip()

        if not goal:
            return (
                None,
                "Cannot decompose an empty goal.",
            )

        response = self.call_model(
            goal
        )

        plan, error = self.parse_plan(
            response,
            capability_registry=self.capability_registry,
        )

        if error:
            return None, error

        if plan is None:
            return (
                None,
                "Goal decomposer produced no plan.",
            )

        plan.goal = goal

        return plan, None