from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from app.agent.goal_plan import GoalPlan


class MissionStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    PAUSED = "paused"


@dataclass
class MissionState:
    """
    Durable state describing an entire KUMA mission.

    MissionState records what happened.
    It does not decide what should happen next.
    """

    mission_id: str

    goal: str

    status: MissionStatus = MissionStatus.PLANNED

    created_at: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )

    updated_at: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )

    current_step_id: str = ""

    remaining_objective: str = ""

    completed_step_ids: list[str] = field(
        default_factory=list
    )

    failed_step_ids: list[str] = field(
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

    last_evidence: str = ""

    continuation_guard_known: bool = False

    continuation_guard_tool: str = ""

    continuation_guard_arguments: dict[str, Any] = field(
        default_factory=dict
    )

    continuation_guard_capability: str = ""

    continuation_verification_pending: bool = False

    continuation_execution_inflight: bool = False

    recovery_continuation_cycles: int = 0

    artifacts: list[str] = field(
        default_factory=list
    )

    plan: GoalPlan | None = None

    final_result: dict[str, Any] | None = None

    @classmethod
    def from_controller(
        cls,
        controller,
        mission: "MissionState | None" = None,
    ) -> "MissionState":
        """
        Build durable mission state from the live controller.

        Existing mission identity is preserved when supplied.
        """

        if mission is None:
            mission = cls.create(
                controller.task_state.goal
            )

        task_state = controller.task_state

        plan = controller.plan

        mission.current_step_id = (
            plan.current_step_id
            if plan is not None
            else ""
        )

        mission.remaining_objective = (
            str(
                task_state.remaining_objective
                or ""
            ).strip()
        )

        mission.completed_step_ids = []

        mission.failed_step_ids = []

        if plan is not None:
            mission.completed_step_ids = [
                step.id
                for step in plan.steps
                if step.status.value == "completed"
            ]

            mission.failed_step_ids = [
                step.id
                for step in plan.steps
                if step.status.value == "failed"
            ]

        mission.observations = list(
            task_state.observations
        )

        mission.failures = list(
            task_state.failures
        )

        mission.action_history = list(
            task_state.action_history
        )

        mission.last_evidence = (
            task_state.last_evidence
        )

        mission.continuation_guard_known = (
            bool(
                task_state.continuation_guard_known
            )
        )

        mission.continuation_guard_tool = str(
            task_state.continuation_guard_tool
            or ""
        ).strip()

        mission.continuation_guard_arguments = dict(
            task_state.continuation_guard_arguments
            or {}
        )

        mission.continuation_guard_capability = str(
            task_state.continuation_guard_capability
            or ""
        ).strip()

        mission.continuation_verification_pending = (
            bool(
                task_state.continuation_verification_pending
            )
        )

        mission.continuation_execution_inflight = (
            bool(
                task_state.continuation_execution_inflight
            )
        )

        mission.recovery_continuation_cycles = (
            task_state.recovery_continuation_cycles
        )

        mission.status = (
            MissionStatus.COMPLETED
            if controller.is_complete()
            else mission.status
        )

        if not controller.is_complete():
            if (
                mission.status
                != MissionStatus.FAILED
            ):
                mission.status = (
                    MissionStatus.RUNNING
                )

        mission.touch()

        return mission

    @classmethod
    def create(
        cls,
        goal: str,
    ) -> "MissionState":
        """
        Create a new mission with a unique ID.
        """

        goal = str(
            goal or ""
        ).strip()

        if not goal:
            raise ValueError(
                "Mission goal cannot be empty."
            )

        mission_id = (
            f"M-{uuid.uuid4().hex[:12]}"
        )

        return cls(
            mission_id=mission_id,
            goal=goal,
        )

    def touch(self) -> None:
        """
        Update the durable modification timestamp.
        """

        self.updated_at = datetime.now(
            timezone.utc
        ).isoformat()

    def start(
        self,
    ) -> None:
        self.status = MissionStatus.RUNNING
        self.touch()

    def set_current_step(
        self,
        step_id: str,
    ) -> None:
        self.current_step_id = (
            str(step_id or "").strip()
        )
        self.touch()

    def complete_step(
        self,
        step_id: str,
    ) -> None:
        step_id = str(
            step_id or ""
        ).strip()

        if not step_id:
            return

        if step_id not in self.completed_step_ids:
            self.completed_step_ids.append(
                step_id
            )

        if step_id in self.failed_step_ids:
            self.failed_step_ids.remove(
                step_id
            )

        if self.current_step_id == step_id:
            self.current_step_id = ""

        self.touch()

    def fail_step(
        self,
        step_id: str,
        reason: str,
    ) -> None:
        step_id = str(
            step_id or ""
        ).strip()

        reason = str(
            reason or ""
        ).strip()

        if step_id and step_id not in self.failed_step_ids:
            self.failed_step_ids.append(
                step_id
            )

        if reason:
            self.failures.append(
                reason
            )

        if self.current_step_id == step_id:
            self.current_step_id = ""

        self.status = MissionStatus.FAILED

        self.touch()

    def add_observation(
        self,
        observation: Any,
    ) -> None:
        if observation is None:
            return

        self.observations.append(
            str(observation)
        )

        self.touch()

    def add_action(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        result: Any,
        verified: bool,
        capability: str = "",
    ) -> None:

        self.action_history.append(
            {
                "capability": str(
                    capability or ""
                ),
                "tool": str(
                    tool_name or ""
                ),
                "arguments": dict(
                    arguments or {}
                ),
                "result": str(
                    result
                    if result is not None
                    else ""
                ),
                "verified": bool(
                    verified
                ),
            }
        )

        if verified:
            self.last_evidence = str(
                result
                if result is not None
                else ""
            )

        self.touch()

    def add_artifact(
        self,
        artifact: str,
    ) -> None:
        artifact = str(
            artifact or ""
        ).strip()

        if artifact and artifact not in self.artifacts:
            self.artifacts.append(
                artifact
            )

        self.touch()

    def mark_completed(
        self,
        result: Any = None,
    ) -> None:
        self.status = MissionStatus.COMPLETED
        self.current_step_id = ""

        if result is not None:
            self.final_result = {
                "result": str(result)
            }

        self.touch()

    def mark_blocked(
        self,
        reason: str,
    ) -> None:
        self.status = MissionStatus.BLOCKED

        reason = str(
            reason or ""
        ).strip()

        if reason:
            self.failures.append(
                reason
            )

        self.current_step_id = ""

        self.touch()

    def mark_paused(self) -> None:
        self.status = MissionStatus.PAUSED
        self.touch()

    def is_terminal(self) -> bool:
        return self.status in {
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.BLOCKED,
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)

        data["status"] = self.status.value

        data["plan"] = (
    self.plan.to_dict()
    if self.plan is not None
    else None
)

        return data

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
        )

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "MissionState":
        # Persisted mission state is untrusted input.
        # Recovery-sensitive fields are parsed strictly and
        # malformed state fails closed with ValueError.

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "MissionState data must be a dictionary."
            )

        def strict_string(
            key: str,
            *,
            default: str = "",
            strip: bool = False,
        ) -> str:

            value = (
                data[key]
                if key in data
                else default
            )

            if not isinstance(
                value,
                str,
            ):
                raise ValueError(
                    f"MissionState field '{key}' "
                    "must be a string."
                )

            return (
                value.strip()
                if strip
                else value
            )

        def strict_bool(
            key: str,
            *,
            default: bool = False,
        ) -> bool:

            if key not in data:
                return default

            value = data[key]

            if type(value) is not bool:
                raise ValueError(
                    f"MissionState field '{key}' "
                    "must be a JSON boolean."
                )

            return value

        def strict_nonnegative_int(
            key: str,
            *,
            default: int = 0,
        ) -> int:

            if key not in data:
                return default

            value = data[key]

            if type(value) is not int:
                raise ValueError(
                    f"MissionState field '{key}' "
                    "must be a JSON integer."
                )

            if value < 0:
                raise ValueError(
                    f"MissionState field '{key}' "
                    "must be non-negative."
                )

            return value

        def strict_string_list(
            key: str,
        ) -> list[str]:

            if key not in data:
                return []

            value = data[key]

            if not isinstance(
                value,
                list,
            ):
                raise ValueError(
                    f"MissionState field '{key}' "
                    "must be a list."
                )

            parsed = []

            for item in value:

                if not isinstance(
                    item,
                    str,
                ):
                    raise ValueError(
                        f"MissionState field '{key}' "
                        "must contain only strings."
                    )

                parsed.append(
                    item
                )

            return parsed

        def strict_dict(
            key: str,
        ) -> dict[str, Any]:

            if key not in data:
                return {}

            value = data[key]

            if not isinstance(
                value,
                dict,
            ):
                raise ValueError(
                    f"MissionState field '{key}' "
                    "must be a dictionary."
                )

            return dict(
                value
            )

        def strict_dict_list(
            key: str,
        ) -> list[dict[str, Any]]:

            if key not in data:
                return []

            value = data[key]

            if not isinstance(
                value,
                list,
            ):
                raise ValueError(
                    f"MissionState field '{key}' "
                    "must be a list."
                )

            parsed = []

            for item in value:

                if not isinstance(
                    item,
                    dict,
                ):
                    raise ValueError(
                        f"MissionState field '{key}' "
                        "must contain only dictionaries."
                    )

                parsed.append(
                    dict(
                        item
                    )
                )

            return parsed

        raw_plan = data.get(
            "plan",
            None,
        )

        if (
            raw_plan is not None
            and not isinstance(
                raw_plan,
                dict,
            )
        ):
            raise ValueError(
                "MissionState field 'plan' must be "
                "a dictionary or null."
            )

        plan = (
            GoalPlan.from_dict(
                raw_plan
            )
            if raw_plan is not None
            else None
        )

        mission_id = strict_string(
            "mission_id",
            strip=True,
        )

        goal = strict_string(
            "goal",
            strip=True,
        )

        if not mission_id:
            raise ValueError(
                "MissionState requires a mission_id."
            )

        if not goal:
            raise ValueError(
                "MissionState requires a goal."
            )

        raw_status = strict_string(
            "status",
            default=(
                MissionStatus.PLANNED.value
            ),
        )

        try:
            status = MissionStatus(
                raw_status
            )

        except ValueError as error:
            raise ValueError(
                f"Invalid mission status: {raw_status}"
            ) from error

        raw_final_result = data.get(
            "final_result",
            None,
        )

        if (
            raw_final_result is not None
            and not isinstance(
                raw_final_result,
                dict,
            )
        ):
            raise ValueError(
                "MissionState field 'final_result' must be "
                "a dictionary or null."
            )

        mission = cls(
            mission_id=mission_id,
            goal=goal,
            status=status,
            created_at=strict_string(
                "created_at",
            ),
            updated_at=strict_string(
                "updated_at",
            ),
            current_step_id=strict_string(
                "current_step_id",
                strip=True,
            ),
            remaining_objective=strict_string(
                "remaining_objective",
                strip=True,
            ),
            completed_step_ids=(
                strict_string_list(
                    "completed_step_ids"
                )
            ),
            failed_step_ids=(
                strict_string_list(
                    "failed_step_ids"
                )
            ),
            observations=(
                strict_string_list(
                    "observations"
                )
            ),
            failures=(
                strict_string_list(
                    "failures"
                )
            ),
            action_history=(
                strict_dict_list(
                    "action_history"
                )
            ),
            last_evidence=strict_string(
                "last_evidence",
            ),
            continuation_guard_known=(
                strict_bool(
                    "continuation_guard_known"
                )
            ),
            continuation_guard_tool=(
                strict_string(
                    "continuation_guard_tool",
                    strip=True,
                )
            ),
            continuation_guard_arguments=(
                strict_dict(
                    "continuation_guard_arguments"
                )
            ),
            continuation_guard_capability=(
                strict_string(
                    "continuation_guard_capability",
                    strip=True,
                )
            ),
            continuation_verification_pending=(
                strict_bool(
                    "continuation_verification_pending"
                )
            ),

            continuation_execution_inflight=(

                strict_bool(

                    "continuation_execution_inflight"

                )

            ),
            recovery_continuation_cycles=(
                strict_nonnegative_int(
                    "recovery_continuation_cycles"
                )
            ),
            artifacts=(
                strict_string_list(
                    "artifacts"
                )
            ),
            plan=plan,
            final_result=(
                dict(
                    raw_final_result
                )
                if raw_final_result is not None
                else None
            ),
        )

        # Mission and plan must agree on authoritative identity
        # and active-step state.
        if plan is not None:

            if plan.goal.strip() != mission.goal:
                raise ValueError(
                    "Persisted GoalPlan goal does not "
                    "match the mission goal."
                )

            if (
                mission.current_step_id
                != plan.current_step_id
            ):
                raise ValueError(
                    "MissionState current_step_id does not "
                    "match GoalPlan current_step_id."
                )

            if (
                mission.status
                == MissionStatus.COMPLETED
            ):

                if mission.current_step_id:
                    raise ValueError(
                        "Completed mission cannot retain "
                        "an active current step."
                    )

                if not plan.is_complete():
                    raise ValueError(
                        "Completed mission contains an "
                        "incomplete GoalPlan."
                    )

            if (
                mission.status
                == MissionStatus.PAUSED
                and mission.current_step_id
            ):

                current = plan.get_step(
                    mission.current_step_id
                )

                if (
                    current is None
                    or getattr(
                        current.status,
                        "value",
                        "",
                    )
                    != "in_progress"
                ):
                    raise ValueError(
                        "Paused mission current step must "
                        "be IN_PROGRESS."
                    )

        # Replay provenance is all-or-nothing. Unknown provenance
        # may not carry stale executable-looking data.
        if mission.continuation_guard_known:

            if not mission.continuation_guard_tool:
                raise ValueError(
                    "Known continuation replay provenance "
                    "requires a tool identity."
                )

        else:

            if (
                mission.continuation_guard_tool
                or mission.continuation_guard_arguments
                or mission.continuation_guard_capability
            ):
                raise ValueError(
                    "Unknown continuation replay provenance "
                    "cannot retain tool, argument, or "
                    "capability data."
                )

        # continuation_verification_pending is a recovery barrier,
        # not authorization. Do not "repair" or over-normalize its
        # semantic context during deserialization.
        #
        # Transitional/legacy states may legitimately persist the
        # barrier before complete provenance is available. The resume
        # layer already fails closed when provenance/state evidence is
        # insufficient, so loading the barrier itself must remain
        # backward-compatible and non-executing.

        if mission.continuation_execution_inflight:

            if mission.status != MissionStatus.PAUSED:
                raise ValueError(
                    "In-flight continuation execution requires "
                    "a PAUSED mission."
                )

            if mission.continuation_verification_pending:
                raise ValueError(
                    "In-flight continuation execution cannot also "
                    "be pending post-continuation verification."
                )

            if not mission.remaining_objective:
                raise ValueError(
                    "In-flight continuation execution requires "
                    "a persisted remaining objective."
                )

            if plan is None or not mission.current_step_id:
                raise ValueError(
                    "In-flight continuation execution requires "
                    "an active persisted GoalPlan step."
                )

            current = plan.get_step(
                mission.current_step_id
            )

            if (
                current is None
                or getattr(
                    current.status,
                    "value",
                    "",
                )
                != "in_progress"
            ):
                raise ValueError(
                    "In-flight continuation execution requires "
                    "an IN_PROGRESS current step."
                )

        return mission

    @classmethod
    def from_json(
        cls,
        payload: str,
    ) -> "MissionState":

        data = json.loads(
            payload
        )

        return cls.from_dict(
            data
        )

    def summary(self) -> str:
        lines = [
            "KUMA MISSION STATE",
            f"Mission ID: {self.mission_id}",
            f"Goal: {self.goal}",
            f"Status: {self.status.value}",
        ]

        if self.current_step_id:
            lines.append(
                f"Current step: {self.current_step_id}"
            )

        if self.completed_step_ids:
            lines.append(
                "Completed steps: "
                + ", ".join(
                    self.completed_step_ids
                )
            )

        if self.failed_step_ids:
            lines.append(
                "Failed steps: "
                + ", ".join(
                    self.failed_step_ids
                )
            )

        if self.last_evidence:
            lines.extend(
                [
                    "Latest evidence:",
                    self.last_evidence,
                ]
            )

        return "\n".join(
            lines
        )