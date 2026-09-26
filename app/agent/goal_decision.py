from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any


def parse_goal_decision(
    raw_response: Any,
) -> tuple[GoalDecision | None, str | None]:
    """
    Parse and validate a model-produced goal decision.

    The model is not trusted to control the runtime directly.
    Only a valid structured decision is returned.
    """

    if raw_response is None:
        return None, "Goal decision response was empty."

    # Accept either raw text or a response/message-like object.
    if isinstance(raw_response, str):
        text = raw_response.strip()
    else:
        content = getattr(
            raw_response,
            "content",
            raw_response,
        )
        text = str(
            content or ""
        ).strip()

    if not text:
        return None, "Goal decision response was empty."

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return None, (
            "Goal decision was not valid JSON: "
            f"{error}"
        )

    if not isinstance(data, dict):
        return None, (
            "Goal decision must be a JSON object."
        )

    raw_status = str(
        data.get("status", "")
    ).strip().lower()

    try:
        status = GoalStatus(
            raw_status
        )
    except ValueError:
        return None, (
            f"Invalid goal status: {raw_status!r}"
        )

    decision = GoalDecision(
        status=status,
        remaining_objective=str(
            data.get(
                "remaining_objective",
                "",
            ) or ""
        ).strip(),
        next_action=str(
            data.get(
                "next_action",
                "",
            ) or ""
        ).strip(),
        reason=str(
            data.get(
                "reason",
                "",
            ) or ""
        ).strip(),
    )

    valid, error = decision.validate()

    if not valid:
        return None, error

    return decision, None


class GoalStatus(str, Enum):
    CONTINUE = "continue"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass
class GoalDecision:
    """
    Structured decision produced by KUMA's reasoning layer.

    The model may propose this decision, but the runtime remains
    responsible for validating it and enforcing execution safety.
    """

    status: GoalStatus

    remaining_objective: str = ""

    next_action: str = ""

    reason: str = ""

    @property
    def is_complete(self) -> bool:
        return self.status == GoalStatus.COMPLETE

    @property
    def should_continue(self) -> bool:
        return self.status == GoalStatus.CONTINUE

    @property
    def is_blocked(self) -> bool:
        return self.status == GoalStatus.BLOCKED

    def validate(self) -> tuple[bool, str]:
        """
        Validate the semantic shape of the decision.

        This does not authorize tools or actions.
        """

        if not isinstance(
            self.status,
            GoalStatus,
        ):
            return (
                False,
                "Goal status is invalid.",
            )

        if self.status == GoalStatus.CONTINUE:

            if not self.remaining_objective.strip():
                return (
                    False,
                    "CONTINUE decision requires "
                    "a remaining objective.",
                )

        if self.status == GoalStatus.BLOCKED:

            if not self.reason.strip():
                return (
                    False,
                    "BLOCKED decision requires "
                    "a reason.",
                )

        if self.status == GoalStatus.COMPLETE:

            if self.remaining_objective.strip():
                return (
                    False,
                    "COMPLETE decision cannot have "
                    "a remaining objective.",
                )

        return True, ""

    def as_prompt(self) -> str:
        """
        Serialize the contract into a format that can be shown
        to the reasoning model.
        """

        return (
            "GOAL DECISION\n"
            f"STATUS: {self.status.value}\n"
            f"REMAINING_OBJECTIVE: "
            f"{self.remaining_objective}\n"
            f"NEXT_ACTION: {self.next_action}\n"
            f"REASON: {self.reason}"
        )