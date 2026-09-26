import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskState:
    """
    Runtime state for the current KUMA task.

    TaskState records authoritative execution history.
    It does not decide what the next action should be.
    The reasoning model remains responsible for that decision.
    """

    goal: str

    current_step: str = ""

    remaining_objective: str = ""

    last_evidence: str = ""

    completed_steps: list[str] = field(
        default_factory=list
    )

    observations: list[str] = field(
        default_factory=list
    )

    failures: list[str] = field(
        default_factory=list
    )

    action_history: list[dict[str, Any]] = field(
        default_factory=list
    )

    # Exact operation that continuation must not blindly replay.
    #
    # These fields record provenance only. They do not authorize
    # or execute anything.
    continuation_guard_known: bool = False

    continuation_guard_tool: str = ""

    continuation_guard_arguments: dict[str, Any] = field(
        default_factory=dict
    )

    continuation_guard_capability: str = ""

    # True after one verified recovery-continuation action.
    #
    # Another continuation action must not execute until the
    # original GoalStep has been independently evaluated.
    continuation_verification_pending: bool = False

    # True after a continuation execution intent is durably
    # persisted and before its outcome is durably classified.
    continuation_execution_inflight: bool = False

    # Completed recovery-continuation cycles for the currently
    # active original GoalStep. This survives restart so recovery
    # cannot livelock across repeated resume calls.
    recovery_continuation_cycles: int = 0

    finished: bool = False

    # =====================================================
    # ACTION STATE
    # =====================================================

    def begin_step(
        self,
        tool_name: str,
    ) -> None:
        """
        Record the capability KUMA is currently attempting.
        """

        self.current_step = (
            f"Execute capability: {tool_name}"
        )

    def record_action(
        self,
        tool_name: str,
        arguments: dict,
        result: Any,
        verified: bool,
    ) -> None:
        """
        Record an executed capability and its verified result.
        """

        self.action_history.append(
            {
                "tool": tool_name,
                "arguments": dict(arguments),
                "result": str(result),
                "verified": bool(verified),
            }
        )

        if verified:
            self.last_evidence = str(
                result
                if result is not None
                else ""
            )

    def complete_step(
        self,
        description: str,
    ) -> None:
        """
        Mark a verified task step as complete.
        """

        description = str(
            description
        ).strip()

        if not description:
            return

        self.completed_steps.append(
            description
        )

        self.current_step = ""

    # =====================================================
    # CONTINUATION REPLAY PROVENANCE
    # =====================================================

    def set_continuation_guard_action(
        self,
        *,
        tool_name: str,
        arguments: dict | None,
        capability: str = "",
    ) -> None:
        """
        Record the exact action a future continuation must not
        blindly replay.

        Provenance is considered known only when the tool name
        and normalized argument mapping are both available.
        """

        tool_name = str(
            tool_name or ""
        ).strip()

        capability = str(
            capability or ""
        ).strip()

        known = (
            bool(tool_name)
            and arguments is not None
        )

        self.continuation_guard_known = (
            known
        )

        self.continuation_guard_tool = (
            tool_name
            if known
            else ""
        )

        self.continuation_guard_arguments = (
            dict(arguments)
            if (
                known
                and isinstance(
                    arguments,
                    dict,
                )
            )
            else {}
        )

        if (
            known
            and not isinstance(
                arguments,
                dict,
            )
        ):
            try:
                self.continuation_guard_arguments = (
                    dict(arguments)
                )
            except Exception:
                self.continuation_guard_known = False
                self.continuation_guard_tool = ""
                self.continuation_guard_arguments = {}

        self.continuation_guard_capability = (
            capability
            if self.continuation_guard_known
            else ""
        )

    def clear_continuation_guard_action(
        self,
    ) -> None:
        """
        Clear persisted replay provenance.
        """

        self.continuation_guard_known = False
        self.continuation_guard_tool = ""
        self.continuation_guard_arguments = {}
        self.continuation_guard_capability = ""

    def mark_continuation_verification_pending(
        self,
    ) -> None:
        """
        Require original-objective verification before another
        recovery-continuation action may execute.
        """

        self.continuation_verification_pending = True

    def clear_continuation_verification_pending(
        self,
    ) -> None:
        """
        Clear the post-continuation verification barrier.
        """

        self.continuation_verification_pending = False

    def mark_continuation_execution_inflight(
        self,
    ) -> None:
        self.continuation_execution_inflight = True

    def clear_continuation_execution_inflight(
        self,
    ) -> None:
        self.continuation_execution_inflight = False

    # =====================================================
    # RECOVERY LIVELOCK BUDGET
    # =====================================================

    def increment_recovery_continuation_cycles(
        self,
    ) -> int:
        """
        Consume one completed continuation recovery cycle.
        """

        if (
            type(self.recovery_continuation_cycles) is not int
            or self.recovery_continuation_cycles < 0
        ):
            raise ValueError(
                "Recovery continuation cycle state is invalid."
            )

        self.recovery_continuation_cycles += 1

        return self.recovery_continuation_cycles

    def reset_recovery_continuation_cycles(
        self,
    ) -> None:
        """
        Reset the livelock budget for a completed GoalStep.
        """

        self.recovery_continuation_cycles = 0

    # =====================================================
    # OBJECTIVE STATE
    # =====================================================

    def set_remaining_objective(
        self,
        objective: str,
    ) -> None:
        """
        Record the remaining objective supplied by the reasoning layer.

        Python does not infer this from keywords.
        """

        self.remaining_objective = str(
            objective or ""
        ).strip()

    def clear_remaining_objective(self) -> None:
        self.remaining_objective = ""

    # =====================================================
    # EVIDENCE
    # =====================================================

    def set_evidence(
        self,
        evidence: Any,
    ) -> None:
        """
        Record the latest verified tool evidence.
        """

        if evidence is None:
            self.last_evidence = ""
            return

        self.last_evidence = str(
            evidence
        )

    def add_observation(
        self,
        observation: Any,
    ) -> None:
        """
        Store an observation produced during the task.
        """

        if observation is None:
            return

        self.observations.append(
            str(observation)
        )

    # =====================================================
    # FAILURE
    # =====================================================

    def record_failure(
        self,
        failure: Any,
    ) -> None:
        """
        Record a task failure.
        """

        if failure is None:
            return

        self.failures.append(
            str(failure)
        )

    # =====================================================
    # COMPLETION
    # =====================================================

    def mark_finished(self) -> None:
        """
        Mark the complete user objective as satisfied.
        """

        self.finished = True
        self.current_step = ""
        self.remaining_objective = ""

    def is_goal_complete(self) -> bool:
        return bool(self.finished)

    # =====================================================
    # COMPACT CONSOLE EVIDENCE
    # =====================================================

    @staticmethod
    def _compact_evidence_for_summary(
        evidence: Any,
        max_chars: int = 700,
    ) -> str:
        """Keep console/task summaries useful without dumping web blobs."""

        value = str(evidence or "").strip()
        if not value:
            return ""

        if len(value) <= max_chars:
            return value

        prefixes = (
            "KUMA_EXTERNAL_UNTRUSTED_WEB_EVIDENCE",
            "EVIDENCE_TYPE:",
            "AUTHORITY:",
            "TRUST:",
            "QUERY:",
            "SEARCH_PROVIDER:",
            "RESULT_COUNT:",
        )

        selected = []
        for line in value.splitlines():
            stripped = line.strip()
            if any(stripped.startswith(prefix) for prefix in prefixes):
                if stripped not in selected:
                    selected.append(stripped)

        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        selected.extend(
            [
                f"EVIDENCE_SIZE_CHARS: {len(value)}",
                f"EVIDENCE_SHA256_16: {digest}",
                "[full verified evidence retained internally]",
            ]
        )

        return "\n".join(selected)

    # =====================================================
    # SUMMARY
    # =====================================================

    def summary(self) -> str:
        """
        Produce a compact human-readable task-state summary.
        """

        lines = [
            "CURRENT KUMA TASK",
            f"Goal: {self.goal}",
            f"Finished: {self.finished}",
        ]

        if self.current_step:
            lines.append(
                f"Current step: {self.current_step}"
            )

        if self.remaining_objective:
            lines.append(
                "Remaining objective:"
            )
            lines.append(
                self.remaining_objective
            )

        if self.completed_steps:
            lines.append(
                "Completed steps:"
            )

            for step in self.completed_steps:
                lines.append(
                    f"- {step}"
                )

        if self.last_evidence:
            lines.append(
                "Latest verified tool evidence:"
            )
            lines.append(
                self._compact_evidence_for_summary(
                    self.last_evidence
                )
            )

        if self.observations:
            lines.append(
                "Recent observations:"
            )

            for observation in self.observations[-3:]:
                lines.append(
                    f"- {observation}"
                )

        if self.failures:
            lines.append(
                "Failures:"
            )

            for failure in self.failures[-3:]:
                lines.append(
                    f"- {failure}"
                )

        return "\n".join(lines)

    # =====================================================
    # REASONING CONTEXT
    # =====================================================

    def reasoning_context(self) -> str:
        """
        Build the state KUMA should use when deciding what to do next.
        """

        lines = [
            "KUMA TASK REASONING STATE",
            "",
            f"Original goal: {self.goal}",
            f"Task finished: {self.finished}",
        ]

        if self.current_step:
            lines.extend(
                [
                    "",
                    f"Current step: {self.current_step}",
                ]
            )

        if self.remaining_objective:
            lines.extend(
                [
                    "",
                    "Remaining objective:",
                    self.remaining_objective,
                ]
            )

        if self.completed_steps:
            lines.extend(
                [
                    "",
                    "Completed:",
                ]
            )

            for step in self.completed_steps:
                lines.append(
                    f"- {step}"
                )

        if self.last_evidence:
            lines.extend(
                [
                    "",
                    "Latest verified tool evidence:",
                    self.last_evidence,
                ]
            )

        if self.observations:
            lines.extend(
                [
                    "",
                    "Observations:",
                ]
            )

            for observation in self.observations[-3:]:
                lines.append(
                    f"- {observation}"
                )

        if self.failures:
            lines.extend(
                [
                    "",
                    "Failures:",
                ]
            )

            for failure in self.failures[-3:]:
                lines.append(
                    f"- {failure}"
                )

        lines.extend(
            [
                "",
                "KUMA reasoning rules:",
                "1. Compare the original goal with completed work.",
                "2. Do not treat the latest successful action as proof "
                "that the entire task is complete.",
                "3. Treat verified tool output as execution evidence; external "
                "content keeps its own trust/authority labels.",
                "4. Determine what remains unfinished.",
                "5. Choose the next capability only when necessary.",
                "6. Finish only when the whole user objective is satisfied "
                "or cannot be completed.",
                "7. Never invent completion evidence.",
            ]
        )

        return "\n".join(lines)