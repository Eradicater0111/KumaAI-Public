from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable


@dataclass(frozen=True)
class RemainingObjectiveResolution:
    """
    A bounded recovery-continuation decision.

    This object can describe only what remains unfinished.
    It has no authority to complete a mission, execute tools,
    grant permissions, retry an action, or rewrite a GoalPlan.
    """

    known: bool

    remaining_objective: str

    reason: str

    # Populated by the runtime from authoritative evidence.
    # The model never supplies this field.
    evidence_used: str = ""


def parse_remaining_objective_resolution(
    raw_response: Any,
    *,
    evidence_used: str,
) -> tuple[
    RemainingObjectiveResolution | None,
    str | None,
]:
    """
    Parse a model-produced remaining-objective decision.

    The model is intentionally restricted to:
    - known
    - remaining_objective
    - reason

    Evidence provenance comes from the runtime, not the model.
    """

    if raw_response is None:
        return (
            None,
            "Remaining-objective response was empty.",
        )

    if isinstance(
        raw_response,
        str,
    ):
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
        return (
            None,
            "Remaining-objective response was empty.",
        )

    try:
        data = json.loads(
            text
        )

    except json.JSONDecodeError as error:
        return (
            None,
            "Remaining-objective response was not "
            f"valid JSON: {error}",
        )

    if not isinstance(
        data,
        dict,
    ):
        return (
            None,
            "Remaining-objective response must "
            "be a JSON object.",
        )

    required_fields = {
        "known",
        "remaining_objective",
        "reason",
    }

    actual_fields = set(
        data
    )

    missing = (
        required_fields
        - actual_fields
    )

    extra = (
        actual_fields
        - required_fields
    )

    if missing:
        return (
            None,
            "Remaining-objective response is missing "
            "field(s): "
            + ", ".join(
                sorted(
                    missing
                )
            ),
        )

    if extra:
        return (
            None,
            "Remaining-objective response contains "
            "unexpected field(s): "
            + ", ".join(
                sorted(
                    extra
                )
            ),
        )

    known = data.get(
        "known"
    )

    if not isinstance(
        known,
        bool,
    ):
        return (
            None,
            "'known' must be a JSON boolean.",
        )

    remaining_objective = str(
        data.get(
            "remaining_objective",
            "",
        )
        or ""
    ).strip()

    reason = str(
        data.get(
            "reason",
            "",
        )
        or ""
    ).strip()

    evidence_used = str(
        evidence_used
        or ""
    ).strip()

    if not reason:
        return (
            None,
            "Remaining-objective resolution "
            "requires a reason.",
        )

    if known:

        if not remaining_objective:
            return (
                None,
                "Known remaining-objective resolution "
                "requires a remaining objective.",
            )

    else:

        if remaining_objective:
            return (
                None,
                "Unknown remaining-objective resolution "
                "cannot contain a remaining objective.",
            )

    return (
        RemainingObjectiveResolution(
            known=known,
            remaining_objective=(
                remaining_objective
            ),
            reason=reason,
            evidence_used=evidence_used,
        ),
        None,
    )


class RemainingObjectiveResolver:
    """
    Determine only the unfinished remainder of a GoalStep.

    This component:
    - receives authoritative recovery evidence,
    - may call a tool-less reasoning model,
    - returns a bounded structured resolution.

    It does not:
    - execute tools,
    - authorize actions,
    - mark steps complete,
    - retry the failed operation,
    - replace the GoalPlan.
    """

    def __init__(
        self,
        model_call: Callable[
            [list[dict[str, str]]],
            Any,
        ],
    ):
        self.model_call = model_call

    def resolve(
        self,
        *,
        step,
        evidence: str,
        recovery_reason: str = "",
    ) -> RemainingObjectiveResolution:
        """
        Resolve what remains unfinished after verified
        partial execution.

        Any uncertainty fails closed to known=False.
        """

        objective = str(
            getattr(
                step,
                "objective",
                "",
            )
            or ""
        ).strip()

        evidence = str(
            evidence
            or ""
        ).strip()

        recovery_reason = str(
            recovery_reason
            or ""
        ).strip()

        success_criteria = [
            str(
                item
            ).strip()
            for item in (
                getattr(
                    step,
                    "success_criteria",
                    [],
                )
                or []
            )
            if str(
                item
            ).strip()
        ]

        verification_requirements = [
            str(
                item
            ).strip()
            for item in (
                getattr(
                    step,
                    "verification_requirements",
                    [],
                )
                or []
            )
            if str(
                item
            ).strip()
        ]

        if not objective:

            return RemainingObjectiveResolution(
                known=False,
                remaining_objective="",
                reason=(
                    "The active mission step has no "
                    "objective to continue."
                ),
                evidence_used=evidence,
            )

        if not evidence:

            return RemainingObjectiveResolution(
                known=False,
                remaining_objective="",
                reason=(
                    "Verified partial-state evidence "
                    "is required before deriving a "
                    "remaining objective."
                ),
                evidence_used="",
            )

        context = {
            "original_step_objective": (
                objective
            ),
            "success_criteria": (
                success_criteria
            ),
            "verification_requirements": (
                verification_requirements
            ),
            "recovery_reason": (
                recovery_reason
            ),
            "authoritative_partial_state_evidence": (
                evidence
            ),
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are KUMA's bounded recovery "
                    "continuation evaluator.\n\n"

                    "Your ONLY job is to determine what "
                    "remains unfinished in the current "
                    "mission step after verified partial "
                    "execution.\n\n"

                    "The supplied partial-state evidence "
                    "is authoritative.\n"
                    "Do not invent facts.\n"
                    "Do not claim the mission step is "
                    "complete.\n"
                    "Do not propose that already verified "
                    "effects be repeated.\n"
                    "Do not execute or request tools.\n"
                    "Do not rewrite the GoalPlan.\n"
                    "Do not grant permissions.\n\n"

                    "If the remaining work cannot be "
                    "determined safely from the supplied "
                    "objective and evidence, return "
                    "known=false.\n\n"

                    "Return JSON only with EXACTLY these "
                    "fields:\n"
                    "{\n"
                    '  "known": true | false,\n'
                    '  "remaining_objective": "string",\n'
                    '  "reason": "string"\n'
                    "}\n\n"

                    "Rules:\n"
                    "- known=true requires a non-empty "
                    "remaining_objective.\n"
                    "- known=false requires an empty "
                    "remaining_objective.\n"
                    "- reason is always required.\n"
                    "- Never return a completion status."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    context,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ]

        try:

            response = self.model_call(
                messages
            )

        except Exception as error:

            return RemainingObjectiveResolution(
                known=False,
                remaining_objective="",
                reason=(
                    "Remaining-objective reasoning "
                    f"failed: {error}"
                ),
                evidence_used=evidence,
            )

        model_message = getattr(
            response,
            "message",
            response,
        )

        resolution, error = (
            parse_remaining_objective_resolution(
                model_message,
                evidence_used=evidence,
            )
        )

        if error or resolution is None:

            return RemainingObjectiveResolution(
                known=False,
                remaining_objective="",
                reason=(
                    error
                    or (
                        "Remaining-objective reasoning "
                        "could not be validated."
                    )
                ),
                evidence_used=evidence,
            )

        return resolution
