from __future__ import annotations

from copy import deepcopy
import inspect

import pytest

from app.agent.capability_registry import (
    Capability,
    CapabilityRegistry,
)
from app.agent.cognitive_contracts import (
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.tactical_analysis import (
    TacticalAnalyzer,
)


STAMP = "2026-09-12T16:30:00+05:30"


def snapshot(
    *,
    task_goal="Recover the editor safely.",
    system_state=(),
    desktop_state=(),
    realtime_state=(),
    task_state=(),
    mission_state=(),
    relevant_memory=(),
):
    return WorldStateSnapshot(
        timestamp=STAMP,
        task_goal=task_goal,
        system_state=system_state,
        desktop_state=desktop_state,
        realtime_state=realtime_state,
        task_state=task_state,
        mission_state=mission_state,
        relevant_memory=relevant_memory,
    )


def registry():
    return CapabilityRegistry(
        [
            Capability(
                name="system_inspection",
                description="Inspect system state.",
                tools=(
                    "inspect_system",
                ),
            ),
            Capability(
                name="application_control",
                description="Launch applications.",
                tools=(
                    "open_app",
                ),
            ),
            Capability(
                name="filesystem",
                description="Read filesystem state.",
                tools=(
                    "list_files",
                    "open_file",
                ),
            ),
        ]
    )


def test_analysis_returns_zero_authority_tactical_situation():
    situation = TacticalAnalyzer().analyze(
        snapshot()
    )

    assert isinstance(
        situation,
        TacticalSituation,
    )
    assert situation.authority == "NONE"
    assert (
        situation.world_state.authority
        == "NONE"
    )


def test_snapshot_goal_is_used_without_reinterpretation():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            task_goal="Diagnose the failure."
        )
    )

    assert (
        situation.goal
        == "Diagnose the failure."
    )


def test_missing_goal_requires_explicit_grounded_goal():
    with pytest.raises(
        ValueError,
        match="grounded goal",
    ):
        TacticalAnalyzer().analyze(
            snapshot(
                task_goal=None
            )
        )


def test_explicit_goal_can_fill_missing_snapshot_goal():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            task_goal=None
        ),
        goal="Inspect the current state.",
    )

    assert (
        situation.goal
        == "Inspect the current state."
    )


def test_conflicting_explicit_goal_is_rejected():
    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        TacticalAnalyzer().analyze(
            snapshot(
                task_goal="Goal A"
            ),
            goal="Goal B",
        )


def test_world_sections_remain_descriptive_observed_state():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            system_state=(
                "system_evidence: CPU normal",
            ),
            desktop_state=(
                "desktop_evidence: Error dialog visible",
            ),
            realtime_state=(
                "realtime_fact: kind=system.network authority=NONE",
            ),
            relevant_memory=(
                "memory_data: Previous retry failed",
            ),
        )
    )

    assert situation.observed_state == (
        "system_evidence: CPU normal",
        "desktop_evidence: Error dialog visible",
        "realtime_fact: kind=system.network authority=NONE",
        "memory_data: Previous retry failed",
    )

    assert (
        situation.known_facts
        == ()
    )


def test_structured_task_observation_is_observed_not_promoted_to_fact():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            task_state=(
                "observation: Error dialog visible.",
            )
        )
    )

    assert situation.observed_state == (
        "Task observation: Error dialog visible.",
    )

    assert (
        situation.known_facts
        == ()
    )


def test_structured_verified_task_evidence_becomes_known_fact():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            task_state=(
                "current_step: Inspect editor.",
                "last_evidence: Editor is responsive.",
                "completed: Captured screenshot.",
                (
                    "action: tool=inspect_system "
                    "verified=true result=System responsive."
                ),
            )
        )
    )

    assert situation.known_facts == (
        "Current task step: Inspect editor.",
        "Task evidence: Editor is responsive.",
        "Completed task step: Captured screenshot.",
        (
            "Verified action evidence: "
            "tool=inspect_system "
            "verified=true result=System responsive."
        ),
    )


def test_structured_mission_state_becomes_known_fact():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            mission_state=(
                "status: running",
                "current_step_id: diagnose",
                "completed_step: inspect",
                "last_evidence: Inspection verified.",
            )
        )
    )

    assert situation.known_facts == (
        "Mission status: running",
        "Current mission step: diagnose",
        "Completed mission step: inspect",
        "Mission evidence: Inspection verified.",
    )


def test_structured_task_failure_and_remainder_become_uncertainties():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            task_state=(
                "remaining_objective: Determine root cause.",
                "failure: Retry failed.",
            )
        )
    )

    assert situation.uncertainties == (
        "Unresolved objective: Determine root cause.",
        "Recorded task failure: Retry failed.",
    )


def test_unverified_action_outcome_becomes_uncertainty():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            task_state=(
                (
                    "action: tool=open_app "
                    "verified=false result=Unknown."
                ),
            )
        )
    )

    assert situation.uncertainties == (
        (
            "Unverified action outcome: "
            "tool=open_app "
            "verified=false result=Unknown."
        ),
    )


def test_pending_verification_becomes_uncertainty():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            task_state=(
                "continuation_verification_pending: true",
            ),
            mission_state=(
                "continuation_verification_pending: true",
            ),
        )
    )

    assert situation.uncertainties == (
        "Continuation verification is pending.",
        "Mission continuation verification is pending.",
    )


def test_failed_mission_step_and_failure_become_uncertainties():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            mission_state=(
                "remaining_objective: Finish recovery.",
                "failed_step: restart",
                "failure: Restart did not verify.",
            )
        )
    )

    assert situation.uncertainties == (
        "Unresolved mission objective: Finish recovery.",
        "Failed mission step: restart",
        "Recorded mission failure: Restart did not verify.",
    )


@pytest.mark.parametrize(
    "text",
    (
        "system_evidence: failure count is zero",
        "desktop_evidence: unknown label is visible",
        "realtime_fact: kind=blocked_word_demo authority=NONE",
        "memory_data: User once said failure is useful wording",
    ),
)
def test_arbitrary_keywords_do_not_create_uncertainty(text):
    situation = TacticalAnalyzer().analyze(
        snapshot(
            system_state=(
                text,
            )
        )
    )

    assert situation.observed_state == (
        text,
    )

    assert (
        situation.uncertainties
        == ()
    )


def test_explicit_constraints_are_flattened_and_preserved():
    situation = TacticalAnalyzer().analyze(
        snapshot(),
        constraints=(
            "Do not alter\nuser files.",
            "Remain read-only.",
        ),
    )

    assert situation.constraints == (
        "Do not alter user files.",
        "Remain read-only.",
    )


def test_explicit_uncertainties_are_flattened_and_preserved():
    situation = TacticalAnalyzer().analyze(
        snapshot(),
        uncertainties=(
            "Root cause\nnot verified.",
        ),
    )

    assert situation.uncertainties == (
        "Root cause not verified.",
    )


def test_runtime_tools_map_to_existing_semantic_capabilities():
    situation = TacticalAnalyzer(
        capability_registry=registry()
    ).analyze(
        snapshot(),
        available_tool_names=(
            "open_app",
            "inspect_system",
            "open_file",
        ),
    )

    assert situation.available_capabilities == (
        "application_control",
        "filesystem",
        "system_inspection",
    )


def test_duplicate_tools_and_shared_capability_are_deduplicated():
    situation = TacticalAnalyzer(
        capability_registry=registry()
    ).analyze(
        snapshot(),
        available_tool_names=(
            "open_file",
            "list_files",
            "open_file",
        ),
    )

    assert situation.available_capabilities == (
        "filesystem",
    )


def test_unmapped_available_tool_becomes_uncertainty_not_capability():
    situation = TacticalAnalyzer(
        capability_registry=registry()
    ).analyze(
        snapshot(),
        available_tool_names=(
            "inspect_system",
            "future_tool",
        ),
    )

    assert situation.available_capabilities == (
        "system_inspection",
    )

    assert (
        (
            "Available runtime tool has no semantic capability mapping: "
            "future_tool"
        )
        in situation.uncertainties
    )


def test_tools_without_registry_are_rejected():
    with pytest.raises(
        ValueError,
        match="CapabilityRegistry",
    ):
        TacticalAnalyzer().analyze(
            snapshot(),
            available_tool_names=(
                "inspect_system",
            ),
        )


def test_invalid_registry_is_rejected():
    with pytest.raises(
        TypeError,
        match="CapabilityRegistry",
    ):
        TacticalAnalyzer(
            capability_registry=object()
        )


def test_analysis_does_not_mutate_snapshot():
    item = snapshot(
        task_state=(
            "failure: Retry failed.",
        ),
        relevant_memory=(
            "memory_data: Prior attempt.",
        ),
    )

    before = deepcopy(
        item
    )

    TacticalAnalyzer().analyze(
        item,
        constraints=(
            "Stay read-only.",
        ),
    )

    assert item == before


def test_duplicate_evidence_is_deduplicated_deterministically():
    situation = TacticalAnalyzer().analyze(
        snapshot(
            system_state=(
                "system_evidence: same",
                "system_evidence: same",
            ),
            task_state=(
                "failure: same",
                "failure: same",
            ),
        )
    )

    assert situation.observed_state == (
        "system_evidence: same",
    )

    assert situation.uncertainties == (
        "Recorded task failure: same",
    )


def test_analysis_module_has_no_option_generation_or_execution_surface():
    import app.agent.tactical_analysis as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "TacticalOption(",
        "TacticalDecision(",
        "ActionExecutor",
        "register_tool(",
        ".execute(",
        "request_confirmation(",
        "open_app(",
        "type_text(",
        "execute_command(",
    )

    for marker in forbidden:
        assert marker not in source


def test_analysis_module_has_no_active_information_collection():
    import app.agent.tactical_analysis as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "app.memory.manager",
        "get_memory_context",
        "retrieve_memories",
        "app.realtime.runtime",
        "refresh_weather(",
        "get_current_location(",
        "web_search(",
        "fetch_webpage(",
        "pyautogui",
        "requests",
        "urllib",
    )

    for marker in forbidden:
        assert marker not in source


def test_analysis_module_does_not_import_permission_system():
    import app.agent.tactical_analysis as module

    source = inspect.getsource(
        module
    )

    assert (
        "app.agent.permissions"
        not in source
    )


def test_situation_never_exposes_approval_fields():
    situation = TacticalAnalyzer().analyze(
        snapshot()
    )

    for field_name in (
        "approved",
        "confirmed",
        "permission_granted",
        "authorized",
        "execute",
    ):
        assert not hasattr(
            situation,
            field_name,
        )
