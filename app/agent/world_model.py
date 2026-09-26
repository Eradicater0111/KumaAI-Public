"""RAPHAEL-1B read-only unified world-model builder."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable

from app.agent.cognitive_contracts import COGNITIVE_AUTHORITY_NONE, WorldStateSnapshot
from app.agent.mission_state import MissionState
from app.agent.task_state import TaskState
from app.agent.virtual_body import VirtualBodyState
from app.realtime import RealtimeFact

WORLD_MODEL_AUTHORITY_NONE = COGNITIVE_AUTHORITY_NONE
_MAX_SECTION_ITEMS = 12
_MAX_HISTORY_ITEMS = 5
_MAX_REALTIME_FACTS = 16
_MAX_TEXT_CHARS = 800


def _now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        raise TypeError("now must be datetime or None.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware.")
    return value


def _text(value, limit: int = _MAX_TEXT_CHARS) -> str:
    normalized = " ".join(str(value if value is not None else "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)] + ("..." if limit >= 3 else "")


def _line(label: str, value) -> str | None:
    value = _text(value)
    return f"{label}: {value}" if value else None


def _lines(values: Iterable[str], *, prefix: str, limit: int = _MAX_SECTION_ITEMS) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError("world-model evidence must be an iterable of strings, not one string.")
    try:
        values = tuple(values)
    except TypeError as error:
        raise TypeError("world-model evidence must be iterable.") from error
    out = []
    for value in values[:limit]:
        value = _text(value)
        if value:
            out.append(f"{prefix}: {value}")
    return tuple(out)


def _status(value) -> str:
    return _text(getattr(value, "value", value))


def _task(state: TaskState | None) -> tuple[str, ...]:
    if state is None:
        return ()
    if not isinstance(state, TaskState):
        raise TypeError("task_state must be TaskState or None.")
    out = []
    for label, name in (("current_step", "current_step"), ("remaining_objective", "remaining_objective"), ("last_evidence", "last_evidence")):
        item = _line(label, getattr(state, name, ""))
        if item:
            out.append(item)
    out.append(f"finished: {str(bool(getattr(state, 'finished', False))).lower()}")
    pending = getattr(state, "continuation_verification_pending", None)
    if type(pending) is bool:
        out.append(f"continuation_verification_pending: {str(pending).lower()}")
    for label, name in (("completed", "completed_steps"), ("observation", "observations"), ("failure", "failures")):
        values = getattr(state, name, ())
        if isinstance(values, list):
            out.extend(_lines(values[-_MAX_HISTORY_ITEMS:], prefix=label, limit=_MAX_HISTORY_ITEMS))
    history = getattr(state, "action_history", ())
    if isinstance(history, list):
        for entry in history[-_MAX_HISTORY_ITEMS:]:
            if not isinstance(entry, dict):
                continue
            tool = _text(entry.get("tool", ""), 160)
            if not tool:
                continue
            verified = bool(entry.get("verified", False))
            result = _text(entry.get("result", ""))
            text = f"action: tool={tool} verified={str(verified).lower()}"
            if result:
                text += f" result={result}"
            out.append(text)
    return tuple(out[:_MAX_SECTION_ITEMS])


def _mission(state: MissionState | None) -> tuple[str, ...]:
    if state is None:
        return ()
    if not isinstance(state, MissionState):
        raise TypeError("mission_state must be MissionState or None.")
    out = []
    for label, name in (("mission_id", "mission_id"), ("goal", "goal"), ("current_step_id", "current_step_id"), ("remaining_objective", "remaining_objective"), ("last_evidence", "last_evidence"), ("updated_at", "updated_at")):
        item = _line(label, getattr(state, name, ""))
        if item:
            out.append(item)
    status = _status(getattr(state, "status", ""))
    if status:
        out.insert(1 if out else 0, f"status: {status}")
    pending = getattr(state, "continuation_verification_pending", None)
    if type(pending) is bool:
        out.append(f"continuation_verification_pending: {str(pending).lower()}")
    for label, name in (("completed_step", "completed_step_ids"), ("failed_step", "failed_step_ids"), ("observation", "observations"), ("failure", "failures")):
        values = getattr(state, name, ())
        if isinstance(values, list):
            out.extend(_lines(values[-_MAX_HISTORY_ITEMS:], prefix=label, limit=_MAX_HISTORY_ITEMS))
    return tuple(out[:_MAX_SECTION_ITEMS])


def _body(state: VirtualBodyState | None) -> tuple[str, ...]:
    if state is None:
        return ()
    if not isinstance(state, VirtualBodyState):
        raise TypeError("virtual_body_state must be VirtualBodyState or None.")
    out = [f"platform: {_text(state.platform, 80)}"]
    if state.frontmost_application_pid is not None and state.frontmost_application_bundle_id is not None:
        out.append(f"frontmost_application: pid={state.frontmost_application_pid} bundle={_text(state.frontmost_application_bundle_id, 240)}")
    if state.screen_observation_id is not None:
        out.append(f"screen_observation_id: {_text(state.screen_observation_id, 240)}")
    if state.pointer_native_point is not None:
        x, y = state.pointer_native_point
        out.append(f"pointer_native_point: ({x}, {y})")
    return tuple(out)


def _jsonish(value) -> str:
    try:
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        value = str(value)
    return _text(value)


def _realtime(facts: Iterable[RealtimeFact], *, now: datetime) -> tuple[str, ...]:
    if isinstance(facts, (str, bytes)):
        raise TypeError("realtime_facts must be an iterable of RealtimeFact.")
    try:
        facts = tuple(facts)
    except TypeError as error:
        raise TypeError("realtime_facts must be iterable.") from error
    for fact in facts:
        if not isinstance(fact, RealtimeFact):
            raise TypeError("realtime_facts must contain RealtimeFact values.")
        if fact.authority != WORLD_MODEL_AUTHORITY_NONE:
            raise ValueError("realtime fact authority must remain NONE.")
    fresh = [fact for fact in facts if fact.expires_at is None or fact.expires_at > now]
    fresh.sort(key=lambda fact: (str(fact.kind), str(fact.location or ""), fact.observed_at.isoformat()))
    out = []
    for fact in fresh[:_MAX_REALTIME_FACTS]:
        parts = [
            "realtime_fact:",
            f"kind={_text(fact.kind, 160)}",
            f"source={_text(fact.source, 200)}",
            f"observed_at={fact.observed_at.isoformat()}",
            f"confidence={float(fact.confidence):.3f}",
            "authority=NONE",
        ]
        if fact.location is not None:
            parts.append(f"location={_text(fact.location, 240)}")
        parts.append(f"value={_jsonish(fact.value)}")
        out.append(" ".join(parts))
    return tuple(out)


class WorldModelBuilder:
    """Aggregate only already-supplied evidence into one zero-authority snapshot."""

    def build(
        self,
        *,
        task_state: TaskState | None = None,
        mission_state: MissionState | None = None,
        virtual_body_state: VirtualBodyState | None = None,
        realtime_facts: Iterable[RealtimeFact] = (),
        system_evidence: Iterable[str] = (),
        desktop_evidence: Iterable[str] = (),
        relevant_memory: Iterable[str] = (),
        now: datetime | None = None,
    ) -> WorldStateSnapshot:
        observed_now = _now(now)
        task_goal = None
        if task_state is not None:
            if not isinstance(task_state, TaskState):
                raise TypeError("task_state must be TaskState or None.")
            task_goal = _text(task_state.goal) or None
        if task_goal is None and mission_state is not None:
            if not isinstance(mission_state, MissionState):
                raise TypeError("mission_state must be MissionState or None.")
            task_goal = _text(mission_state.goal) or None
        snapshot = WorldStateSnapshot(
            timestamp=observed_now.isoformat(),
            task_goal=task_goal,
            system_state=_lines(system_evidence, prefix="system_evidence"),
            desktop_state=(_body(virtual_body_state) + _lines(desktop_evidence, prefix="desktop_evidence"))[:_MAX_SECTION_ITEMS],
            realtime_state=_realtime(realtime_facts, now=observed_now),
            task_state=_task(task_state),
            mission_state=_mission(mission_state),
            relevant_memory=_lines(relevant_memory, prefix="memory_data"),
        )
        if snapshot.authority != WORLD_MODEL_AUTHORITY_NONE:
            raise RuntimeError("world model authority invariant failed.")
        return snapshot
