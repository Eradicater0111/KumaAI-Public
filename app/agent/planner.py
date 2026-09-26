from dataclasses import dataclass
from typing import List


# =========================================================
# ACTION
# =========================================================

@dataclass
class Action:

    tool: str
    arguments: dict

    reason: str = ""


# =========================================================
# PLAN
# =========================================================

@dataclass
class Plan:

    goal: str
    actions: List[Action]


# =========================================================
# CREATE PLAN
# =========================================================

def create_plan(
    goal: str,
    actions: List[Action],
) -> Plan:

    return Plan(
        goal=goal,
        actions=actions,
    )


# =========================================================
# DESCRIBE PLAN
# =========================================================

def describe_plan(plan: Plan) -> str:

    if not plan.actions:

        return (
            f"No actions required for: "
            f"{plan.goal}"
        )

    lines = [
        f"Goal: {plan.goal}",
        "",
        "Planned actions:",
    ]

    for index, action in enumerate(
        plan.actions,
        start=1,
    ):

        description = (
            f"{index}. "
            f"{action.tool}"
        )

        if action.reason:

            description += (
                f" — {action.reason}"
            )

        lines.append(description)

    return "\n".join(lines)