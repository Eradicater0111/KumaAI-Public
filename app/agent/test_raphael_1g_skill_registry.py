from __future__ import annotations

from dataclasses import (
    FrozenInstanceError,
)
import inspect

import pytest

from app.agent.capability_registry import (
    Capability,
    CapabilityRegistry,
)
from app.agent.skill_registry import (
    SkillDefinition,
    SkillMatch,
    SkillPhase,
    SkillRegistry,
)


def capability_registry():
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
                description="Open applications.",
                tools=(
                    "open_app",
                ),
            ),
            Capability(
                name="web_research",
                description="Read public web evidence.",
                tools=(
                    "web_search",
                    "fetch_webpage",
                ),
            ),
        ]
    )


def phase(
    *,
    phase_id="inspect",
    objective="Inspect current state.",
    dependencies=(),
    capabilities=(
        "system_inspection",
    ),
):
    return SkillPhase(
        phase_id=phase_id,
        objective=objective,
        dependencies=dependencies,
        required_capabilities=capabilities,
        success_criteria=(
            f"{phase_id} has observable completion evidence.",
        ),
        verification_requirements=(
            f"Verify {phase_id} from independent runtime evidence.",
        ),
    )


def skill(
    *,
    skill_id="inspect_then_open",
    phases=None,
    required_capabilities=(
        "system_inspection",
        "application_control",
    ),
    reversible=True,
    provenance="static",
):
    if phases is None:
        phases = (
            phase(
                phase_id="inspect",
                capabilities=(
                    "system_inspection",
                ),
            ),
            phase(
                phase_id="open",
                objective="Open the application.",
                dependencies=(
                    "inspect",
                ),
                capabilities=(
                    "application_control",
                ),
            ),
        )

    return SkillDefinition(
        skill_id=skill_id,
        description="Inspect state, then open the application.",
        phases=phases,
        required_capabilities=required_capabilities,
        preconditions=(
            "The target application identity is known.",
        ),
        expected_outcomes=(
            "The requested application may be opened after inspection.",
        ),
        failure_modes=(
            "Inspection may be insufficient.",
            "Application opening may fail.",
        ),
        verification_requirements=(
            "Verify final application state independently.",
        ),
        reversible=reversible,
        provenance=provenance,
    )


def test_skill_phase_is_frozen_and_zero_authority():
    item = phase()

    assert item.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        item.objective = "changed"


def test_skill_definition_is_frozen_and_zero_authority():
    item = skill()

    assert item.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        item.description = "changed"


def test_skill_match_is_frozen_and_zero_authority():
    item = skill()

    match = SkillMatch(
        skill=item,
        eligible=True,
        missing_capabilities=(),
    )

    assert match.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        match.eligible = False


def test_phase_normalizes_text_and_deduplicates_tuple_fields():
    item = SkillPhase(
        phase_id=" inspect ",
        objective=" Inspect\nstate. ",
        required_capabilities=(
            "system_inspection",
            "system_inspection",
        ),
        success_criteria=(
            " State observed. ",
            "State observed.",
        ),
        verification_requirements=(
            " Verify state. ",
        ),
    )

    assert item.phase_id == "inspect"
    assert item.objective == "Inspect state."

    assert item.required_capabilities == (
        "system_inspection",
    )

    assert item.success_criteria == (
        "State observed.",
    )


def test_phase_rejects_string_as_tuple_field():
    with pytest.raises(
        TypeError,
        match="iterable of strings",
    ):
        SkillPhase(
            phase_id="inspect",
            objective="Inspect.",
            required_capabilities="system_inspection",
            success_criteria=(
                "Observed.",
            ),
            verification_requirements=(
                "Verify.",
            ),
        )


def test_phase_requires_success_criteria():
    with pytest.raises(
        ValueError,
        match="success criterion",
    ):
        SkillPhase(
            phase_id="inspect",
            objective="Inspect.",
            verification_requirements=(
                "Verify.",
            ),
        )


def test_phase_requires_verification_requirement():
    with pytest.raises(
        ValueError,
        match="verification requirement",
    ):
        SkillPhase(
            phase_id="inspect",
            objective="Inspect.",
            success_criteria=(
                "Observed.",
            ),
        )


def test_phase_rejects_self_dependency():
    with pytest.raises(
        ValueError,
        match="depend on itself",
    ):
        phase(
            phase_id="inspect",
            dependencies=(
                "inspect",
            ),
        )


def test_skill_requires_at_least_one_phase():
    with pytest.raises(
        ValueError,
        match="at least one phase",
    ):
        SkillDefinition(
            skill_id="empty",
            description="Empty skill.",
            phases=(),
            expected_outcomes=(
                "Nothing.",
            ),
            verification_requirements=(
                "Verify nothing.",
            ),
        )


def test_skill_rejects_duplicate_phase_ids():
    with pytest.raises(
        ValueError,
        match="phase IDs must be unique",
    ):
        skill(
            phases=(
                phase(
                    phase_id="same",
                ),
                phase(
                    phase_id="same",
                ),
            ),
            required_capabilities=(
                "system_inspection",
            ),
        )


def test_skill_rejects_unknown_phase_dependency():
    with pytest.raises(
        ValueError,
        match="unknown dependency",
    ):
        skill(
            phases=(
                phase(
                    phase_id="open",
                    dependencies=(
                        "missing",
                    ),
                    capabilities=(
                        "application_control",
                    ),
                ),
            ),
            required_capabilities=(
                "application_control",
            ),
        )


def test_skill_rejects_dependency_cycle():
    with pytest.raises(
        ValueError,
        match="contain a cycle",
    ):
        skill(
            phases=(
                phase(
                    phase_id="a",
                    dependencies=(
                        "b",
                    ),
                    capabilities=(
                        "system_inspection",
                    ),
                ),
                phase(
                    phase_id="b",
                    dependencies=(
                        "a",
                    ),
                    capabilities=(
                        "application_control",
                    ),
                ),
            ),
        )


def test_skill_accepts_valid_dependency_graph():
    item = skill()

    assert item.phase_ids == (
        "inspect",
        "open",
    )


def test_skill_get_phase_is_exact_and_read_only():
    item = skill()

    assert (
        item.get_phase(
            "open"
        ).objective
        == "Open the application."
    )

    assert (
        item.get_phase(
            "missing"
        )
        is None
    )


def test_phase_capability_must_be_declared_by_skill():
    with pytest.raises(
        ValueError,
        match="not declared",
    ):
        skill(
            phases=(
                phase(
                    capabilities=(
                        "web_research",
                    ),
                ),
            ),
            required_capabilities=(
                "system_inspection",
            ),
        )


def test_skill_requires_expected_outcome():
    with pytest.raises(
        ValueError,
        match="expected outcome",
    ):
        SkillDefinition(
            skill_id="missing-outcome",
            description="Missing outcome.",
            phases=(
                phase(),
            ),
            required_capabilities=(
                "system_inspection",
            ),
            expected_outcomes=(),
            verification_requirements=(
                "Verify.",
            ),
        )


def test_skill_requires_verification_requirement():
    with pytest.raises(
        ValueError,
        match="verification requirement",
    ):
        SkillDefinition(
            skill_id="missing-verification",
            description="Missing verification.",
            phases=(
                phase(),
            ),
            required_capabilities=(
                "system_inspection",
            ),
            expected_outcomes=(
                "Observed.",
            ),
            verification_requirements=(),
        )


def test_skill_reversible_must_be_bool():
    with pytest.raises(
        TypeError,
        match="reversible",
    ):
        SkillDefinition(
            skill_id="bad-reversible",
            description="Bad reversible.",
            phases=(
                phase(),
            ),
            required_capabilities=(
                "system_inspection",
            ),
            expected_outcomes=(
                "Observed.",
            ),
            verification_requirements=(
                "Verify.",
            ),
            reversible=1,
        )


def test_provenance_is_descriptive_text_only():
    item = skill(
        provenance=" generated proposal "
    )

    assert (
        item.provenance
        == "generated proposal"
    )

    assert item.authority == "NONE"


def test_registry_requires_capability_registry():
    with pytest.raises(
        TypeError,
        match="CapabilityRegistry",
    ):
        SkillRegistry(
            object()
        )


def test_registry_registers_and_retrieves_exact_skill():
    item = skill()

    registry = SkillRegistry(
        capability_registry()
    )

    registry.register(
        item
    )

    assert registry.has(
        "inspect_then_open"
    )

    assert (
        registry.get(
            "inspect_then_open"
        )
        is item
    )


def test_registry_constructor_accepts_initial_skills():
    item = skill()

    registry = SkillRegistry(
        capability_registry(),
        (
            item,
        ),
    )

    assert registry.get(
        item.skill_id
    ) is item


def test_registry_rejects_duplicate_skill_id():
    item = skill()

    registry = SkillRegistry(
        capability_registry(),
        (
            item,
        ),
    )

    with pytest.raises(
        ValueError,
        match="already contains",
    ):
        registry.register(
            item
        )


def test_registry_rejects_unknown_skill_capability():
    item = skill(
        required_capabilities=(
            "system_inspection",
            "unknown_capability",
        ),
        phases=(
            phase(
                capabilities=(
                    "system_inspection",
                ),
            ),
        ),
    )

    registry = SkillRegistry(
        capability_registry()
    )

    with pytest.raises(
        ValueError,
        match="unknown capabilities",
    ):
        registry.register(
            item
        )


def test_registry_revalidates_current_capability_names():
    item = skill()

    registry = SkillRegistry(
        capability_registry(),
        (
            item,
        ),
    )

    assert set(
        registry.get(
            item.skill_id
        ).required_capabilities
    ) == {
        "system_inspection",
        "application_control",
    }


def test_registry_ids_are_deterministically_sorted():
    registry = SkillRegistry(
        capability_registry(),
        (
            skill(
                skill_id="zeta",
            ),
            skill(
                skill_id="alpha",
            ),
        ),
    )

    assert registry.ids() == (
        "alpha",
        "zeta",
    )


def test_registry_all_is_deterministically_sorted():
    registry = SkillRegistry(
        capability_registry(),
        (
            skill(
                skill_id="zeta",
            ),
            skill(
                skill_id="alpha",
            ),
        ),
    )

    assert tuple(
        item.skill_id
        for item
        in registry.all()
    ) == (
        "alpha",
        "zeta",
    )


def test_assess_reports_eligible_when_all_capabilities_available():
    registry = SkillRegistry(
        capability_registry(),
        (
            skill(),
        ),
    )

    match = registry.assess(
        "inspect_then_open",
        available_capabilities=(
            "application_control",
            "system_inspection",
        ),
    )

    assert match.eligible is True
    assert match.missing_capabilities == ()
    assert match.authority == "NONE"


def test_assess_reports_missing_capabilities_in_skill_order():
    registry = SkillRegistry(
        capability_registry(),
        (
            skill(),
        ),
    )

    match = registry.assess(
        "inspect_then_open",
        available_capabilities=(
            "system_inspection",
        ),
    )

    assert match.eligible is False

    assert match.missing_capabilities == (
        "application_control",
    )


def test_assess_rejects_unknown_available_capability():
    registry = SkillRegistry(
        capability_registry(),
        (
            skill(),
        ),
    )

    with pytest.raises(
        ValueError,
        match="unknown capability names",
    ):
        registry.assess(
            "inspect_then_open",
            available_capabilities=(
                "system_inspection",
                "invented",
            ),
        )


def test_assess_rejects_unknown_skill_id():
    registry = SkillRegistry(
        capability_registry()
    )

    with pytest.raises(
        KeyError,
        match="Unknown skill_id",
    ):
        registry.assess(
            "missing",
            available_capabilities=(),
        )


def test_matching_returns_only_capability_eligible_skills():
    inspect_only = SkillDefinition(
        skill_id="inspect_only",
        description="Inspect only.",
        phases=(
            phase(),
        ),
        required_capabilities=(
            "system_inspection",
        ),
        expected_outcomes=(
            "State inspected.",
        ),
        verification_requirements=(
            "Verify inspection.",
        ),
    )

    registry = SkillRegistry(
        capability_registry(),
        (
            skill(),
            inspect_only,
        ),
    )

    matched = registry.matching(
        available_capabilities=(
            "system_inspection",
        ),
    )

    assert tuple(
        item.skill_id
        for item
        in matched
    ) == (
        "inspect_only",
    )


def test_matching_is_deterministic_by_skill_id():
    inspect_a = SkillDefinition(
        skill_id="a",
        description="A.",
        phases=(
            phase(
                phase_id="a-phase",
            ),
        ),
        required_capabilities=(
            "system_inspection",
        ),
        expected_outcomes=(
            "A outcome.",
        ),
        verification_requirements=(
            "Verify A.",
        ),
    )

    inspect_z = SkillDefinition(
        skill_id="z",
        description="Z.",
        phases=(
            phase(
                phase_id="z-phase",
            ),
        ),
        required_capabilities=(
            "system_inspection",
        ),
        expected_outcomes=(
            "Z outcome.",
        ),
        verification_requirements=(
            "Verify Z.",
        ),
    )

    registry = SkillRegistry(
        capability_registry(),
        (
            inspect_z,
            inspect_a,
        ),
    )

    assert tuple(
        item.skill_id
        for item
        in registry.matching(
            available_capabilities=(
                "system_inspection",
            ),
        )
    ) == (
        "a",
        "z",
    )


def test_matching_with_no_available_capabilities_can_match_capability_free_skill():
    no_capability_phase = phase(
        phase_id="reason",
        capabilities=(),
    )

    no_capability_skill = skill(
        skill_id="reason_only",
        phases=(
            no_capability_phase,
        ),
        required_capabilities=(),
    )

    registry = SkillRegistry(
        capability_registry(),
        (
            no_capability_skill,
        ),
    )

    assert tuple(
        item.skill_id
        for item
        in registry.matching(
            available_capabilities=(),
        )
    ) == (
        "reason_only",
    )


def test_skill_definition_contains_no_tool_surface():
    item = skill()

    forbidden = (
        "tool",
        "planned_tool",
        "tool_name",
        "arguments",
        "permission",
        "approved",
        "confirmed",
        "executor",
        "callable",
        "code",
    )

    fields = set(
        item.__dataclass_fields__
    )

    for name in forbidden:
        assert name not in fields


def test_skill_phase_contains_no_goalstep_runtime_state():
    item = phase()

    forbidden = (
        "status",
        "result",
        "reason",
        "planned_tool",
        "gui_target_intent",
        "gui_authority",
        "gui_authority_goal",
        "artifacts",
        "risk_level",
    )

    fields = set(
        item.__dataclass_fields__
    )

    for name in forbidden:
        assert name not in fields


def test_skill_match_has_no_decision_or_execution_surface():
    match = SkillMatch(
        skill=skill(),
        eligible=True,
        missing_capabilities=(),
    )

    for name in (
        "chosen_option",
        "disposition",
        "required_permission",
        "tool_name",
        "execute",
        "approved",
        "authorized",
    ):
        assert not hasattr(
            match,
            name,
        )


def test_module_has_no_permission_tool_registration_or_execution_imports():
    import app.agent.skill_registry as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "app.agent.permissions",
        "PermissionLevel",
        "require_explicit_permission",
        "register_tool(",
        "TOOL_PERMISSIONS",
        "app.agent.executor",
        "app.agent.kuma_agent",
        "app.agent.mission_service",
        ".execute(",
        "execute_mission_step(",
        "request_confirmation(",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_model_provider_memory_sensor_or_network_surface():
    import app.agent.skill_registry as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "ollama",
        "generate_content(",
        "ask_model(",
        "app.memory",
        "get_memory_context",
        "retrieve_memories",
        "app.realtime",
        "get_current_location(",
        "web_search(",
        "fetch_webpage(",
        "requests",
        "urllib",
        "pyautogui",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_dynamic_code_or_persistence_surface():
    import app.agent.skill_registry as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "exec(",
        "eval(",
        "compile(",
        "importlib",
        "pickle",
        "marshal",
        "sqlite",
        "json.dump",
        "write_text(",
        "write_bytes(",
        "open(",
    )

    for marker in forbidden:
        assert marker not in source


def test_skill_registry_does_not_snapshot_full_capability_objects():
    registry = SkillRegistry(
        capability_registry(),
        (
            skill(),
        ),
    )

    stored = registry.get(
        "inspect_then_open"
    )

    assert all(
        isinstance(
            name,
            str,
        )
        for name
        in stored.required_capabilities
    )

    assert not any(
        isinstance(
            name,
            Capability,
        )
        for name
        in stored.required_capabilities
    )


def test_skill_registration_does_not_mutate_capability_registry():
    capabilities = capability_registry()

    before_names = set(
        capabilities.names()
    )

    before_all = tuple(
        capabilities.all()
    )

    registry = SkillRegistry(
        capabilities
    )

    registry.register(
        skill()
    )

    assert set(
        capabilities.names()
    ) == before_names

    assert tuple(
        capabilities.all()
    ) == before_all


def test_skill_matching_does_not_mutate_skill_registry():
    registry = SkillRegistry(
        capability_registry(),
        (
            skill(),
        ),
    )

    before = registry.all()

    registry.matching(
        available_capabilities=(
            "system_inspection",
            "application_control",
        ),
    )

    assert registry.all() == before


def test_tampered_skill_authority_is_rejected_by_registry():
    item = skill()

    object.__setattr__(
        item,
        "authority",
        "AUTHORIZED",
    )

    registry = SkillRegistry(
        capability_registry()
    )

    with pytest.raises(
        ValueError,
        match="authority must remain NONE",
    ):
        registry.register(
            item
        )


def test_tampered_phase_authority_is_rejected_by_registry():
    item = skill()

    object.__setattr__(
        item.phases[0],
        "authority",
        "AUTHORIZED",
    )

    registry = SkillRegistry(
        capability_registry()
    )

    with pytest.raises(
        ValueError,
        match="SkillPhase authority",
    ):
        registry.register(
            item
        )


def test_registry_has_no_execution_method():
    registry = SkillRegistry(
        capability_registry()
    )

    for name in (
        "execute",
        "run",
        "invoke",
        "call",
        "authorize",
        "approve",
    ):
        assert not hasattr(
            registry,
            name,
        )


def test_skill_contract_has_no_runtime_tool_parameter():
    signature = inspect.signature(
        SkillDefinition
    )

    forbidden = {
        "tool",
        "tool_name",
        "planned_tool",
        "arguments",
        "permission",
        "executor",
    }

    assert not (
        forbidden
        & set(
            signature.parameters
        )
    )


def test_skill_phase_contract_has_no_runtime_tool_parameter():
    signature = inspect.signature(
        SkillPhase
    )

    forbidden = {
        "tool",
        "tool_name",
        "planned_tool",
        "arguments",
        "permission",
        "executor",
    }

    assert not (
        forbidden
        & set(
            signature.parameters
        )
    )
