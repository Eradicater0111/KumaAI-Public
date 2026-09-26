from dataclasses import (
    FrozenInstanceError,
    replace,
)
from pathlib import Path

import pytest

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
)
from app.agent.gui_intent_authority import (
    GUI_AUTHORITY_CONFIRMED,
    GUI_AUTHORITY_EXPLICIT,
    GuiPlanAuthorityDecision,
)
from app.agent.gui_step_authority_provenance import (
    RuntimeGuiPlanAuthorityProvenance,
    RuntimeGuiStepAuthorityProvenance,
    RuntimeGuiStepAuthorityProvenanceError,
    RuntimeGuiStepAuthorityProvenanceStore,
)


GOAL = (
    'type "hello   world"'
)


class Clock:
    def __init__(
        self,
        *values,
    ):
        self.values = list(
            values
        )

    def __call__(
        self,
    ):
        if len(
            self.values
        ) > 1:
            return self.values.pop(
                0
            )

        return self.values[
            0
        ]


def explicit_step(
    *,
    step_id="step-1",
    goal=GOAL,
):
    return GoalStep(
        id=step_id,
        objective="Type requested text",
        planned_tool="type_text",
        gui_authority=(
            GUI_AUTHORITY_EXPLICIT
        ),
        gui_authority_goal=goal,
    )


def confirmed_step(
    *,
    step_id="step-1",
    goal=GOAL,
):
    return GoalStep(
        id=step_id,
        objective="Type requested text",
        planned_tool="type_text",
        gui_authority=(
            GUI_AUTHORITY_CONFIRMED
        ),
        gui_authority_goal=goal,
    )


def plan_for(
    step,
    *,
    goal=GOAL,
    current=True,
):
    return GoalPlan(
        goal=goal,
        steps=[
            step,
        ],
        current_step_id=(
            step.id
            if current
            else ""
        ),
    )


def explicit_decision(
    step,
):
    return GuiPlanAuthorityDecision(
        allowed=True,
        explicit_steps=(
            step.id,
        ),
    )


def confirmed_decision(
    step,
):
    return GuiPlanAuthorityDecision(
        allowed=True,
        confirmed_steps=(
            step.id,
        ),
    )


def issued_explicit():
    step = explicit_step()

    plan = plan_for(
        step
    )

    decision = explicit_decision(
        step
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=Clock(
                100.0
            )
        )
    )

    batch = store._issue_authorized_plan(
        plan,
        GOAL,
        decision,
    )

    return (
        store,
        batch,
        plan,
        step,
        decision,
    )


def test_issue_preserves_exact_runtime_object_graph():
    (
        store,
        batch,
        plan,
        step,
        decision,
    ) = issued_explicit()

    assert (
        batch.plan
        is plan
    )

    assert (
        batch.authority_decision
        is decision
    )

    assert (
        batch.human_goal
        == GOAL
    )

    assert len(
        batch.step_provenances
    ) == 1

    provenance = (
        batch.step_provenances[
            0
        ]
    )

    assert (
        provenance.plan
        is plan
    )

    assert (
        provenance.step
        is step
    )

    assert (
        provenance.authority_decision
        is decision
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is provenance
    )


def test_exact_current_step_returns_same_provenance_object():
    (
        store,
        batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    provenance = (
        batch.step_provenances[
            0
        ]
    )

    first = store.get_current(
        plan,
        step,
    )

    second = store.get_current(
        plan,
        step,
    )

    assert first is provenance
    assert second is provenance


def test_equal_value_reconstructed_step_is_not_current_source():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    reconstructed = replace(
        step
    )

    assert reconstructed == step

    assert reconstructed is not step

    assert (
        store.get_current(
            plan,
            reconstructed,
        )
        is None
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is not None
    )


def test_equal_value_reconstructed_plan_is_not_current_source():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    reconstructed = replace(
        plan
    )

    assert reconstructed == plan

    assert reconstructed is not plan

    assert (
        store.get_current(
            reconstructed,
            step,
        )
        is None
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is not None
    )


def test_synthetic_forged_step_with_valid_authority_string_is_not_trusted():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    forged = GoalStep(
        id=step.id,
        objective=step.objective,
        planned_tool="type_text",
        gui_authority=(
            GUI_AUTHORITY_EXPLICIT
        ),
        gui_authority_goal=GOAL,
    )

    assert (
        forged.gui_authority
        == GUI_AUTHORITY_EXPLICIT
    )

    assert (
        store.get_current(
            plan,
            forged,
        )
        is None
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is not None
    )


def test_current_step_id_must_match_exact_step():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    plan.current_step_id = ""

    assert (
        store.get_current(
            plan,
            step,
        )
        is None
    )


def test_plan_get_step_must_return_exact_same_object():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    reconstructed = replace(
        step
    )

    plan.steps[
        0
    ] = reconstructed

    assert (
        store.get_current(
            plan,
            step,
        )
        is None
    )

    assert len(
        store
    ) == 0


def test_mutating_step_authority_invalidates_active_graph():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    step.gui_authority = (
        GUI_AUTHORITY_CONFIRMED
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is None
    )

    assert len(
        store
    ) == 0


def test_mutating_step_human_goal_invalidates_active_graph():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    step.gui_authority_goal = (
        'type "other"'
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is None
    )

    assert len(
        store
    ) == 0


def test_mutating_plan_goal_invalidates_active_graph():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    plan.goal = (
        'type "other"'
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is None
    )

    assert len(
        store
    ) == 0


def test_mutating_planned_tool_invalidates_active_graph():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    step.planned_tool = (
        "click"
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is None
    )

    assert len(
        store
    ) == 0


def test_confirmed_runtime_authority_is_supported():
    step = confirmed_step()

    plan = plan_for(
        step
    )

    decision = confirmed_decision(
        step
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    batch = store._issue_authorized_plan(
        plan,
        GOAL,
        decision,
    )

    provenance = (
        batch.step_provenances[
            0
        ]
    )

    assert (
        provenance.gui_authority
        == GUI_AUTHORITY_CONFIRMED
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is provenance
    )


def test_decision_must_match_explicit_authority_steps():
    step = explicit_step()

    plan = plan_for(
        step
    )

    wrong = GuiPlanAuthorityDecision(
        allowed=True,
        confirmed_steps=(
            step.id,
        ),
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    with pytest.raises(
        RuntimeGuiStepAuthorityProvenanceError,
        match="decision",
    ):
        store._issue_authorized_plan(
            plan,
            GOAL,
            wrong,
        )

    assert len(
        store
    ) == 0


def test_disallowed_decision_never_issues_provenance():
    step = explicit_step()

    plan = plan_for(
        step
    )

    decision = GuiPlanAuthorityDecision(
        allowed=False,
        reason="denied",
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    with pytest.raises(
        RuntimeGuiStepAuthorityProvenanceError,
        match="Allowed",
    ):
        store._issue_authorized_plan(
            plan,
            GOAL,
            decision,
        )

    assert len(
        store
    ) == 0


def test_goal_mismatch_never_issues_provenance():
    step = explicit_step()

    plan = plan_for(
        step
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    with pytest.raises(
        RuntimeGuiStepAuthorityProvenanceError,
        match="human goal",
    ):
        store._issue_authorized_plan(
            plan,
            'type "other"',
            explicit_decision(
                step
            ),
        )

    assert len(
        store
    ) == 0


def test_duplicate_step_ids_are_rejected():
    first = explicit_step(
        step_id="same"
    )

    second = explicit_step(
        step_id="same"
    )

    plan = GoalPlan(
        goal=GOAL,
        steps=[
            first,
            second,
        ],
        current_step_id="same",
    )

    decision = GuiPlanAuthorityDecision(
        allowed=True,
        explicit_steps=(
            "same",
            "same",
        ),
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    with pytest.raises(
        RuntimeGuiStepAuthorityProvenanceError,
        match="duplicate",
    ):
        store._issue_authorized_plan(
            plan,
            GOAL,
            decision,
        )


def test_new_issue_replaces_previous_runtime_plan_graph():
    first_step = explicit_step(
        step_id="first"
    )

    first_plan = plan_for(
        first_step
    )

    second_step = explicit_step(
        step_id="second"
    )

    second_plan = plan_for(
        second_step
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=Clock(
                100.0,
                101.0,
            )
        )
    )

    first = store._issue_authorized_plan(
        first_plan,
        GOAL,
        explicit_decision(
            first_step
        ),
    )

    second = store._issue_authorized_plan(
        second_plan,
        GOAL,
        explicit_decision(
            second_step
        ),
    )

    assert second is not first

    assert (
        store.get_current(
            first_plan,
            first_step,
        )
        is None
    )

    assert (
        store.get_current(
            second_plan,
            second_step,
        )
        is (
            second
            .step_provenances[
                0
            ]
        )
    )


def test_failed_new_issue_clears_previous_runtime_graph():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    assert (
        store.get_current(
            plan,
            step,
        )
        is not None
    )

    bad_step = explicit_step(
        step_id="bad"
    )

    bad_plan = plan_for(
        bad_step
    )

    bad_decision = (
        GuiPlanAuthorityDecision(
            allowed=False,
            reason="denied",
        )
    )

    with pytest.raises(
        RuntimeGuiStepAuthorityProvenanceError
    ):
        store._issue_authorized_plan(
            bad_plan,
            GOAL,
            bad_decision,
        )

    assert len(
        store
    ) == 0


def test_clear_removes_active_runtime_graph():
    (
        store,
        _batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    store.clear()

    assert len(
        store
    ) == 0

    assert (
        store.get_current(
            plan,
            step,
        )
        is None
    )


def test_clock_rollback_fails_closed_and_clears_previous_graph():
    step = explicit_step()

    plan = plan_for(
        step
    )

    decision = explicit_decision(
        step
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=Clock(
                100.0,
                99.0,
            )
        )
    )

    store._issue_authorized_plan(
        plan,
        GOAL,
        decision,
    )

    with pytest.raises(
        RuntimeGuiStepAuthorityProvenanceError,
        match="backwards",
    ):
        store._issue_authorized_plan(
            plan,
            GOAL,
            decision,
        )

    assert len(
        store
    ) == 0


def test_nonfinite_clock_is_rejected():
    step = explicit_step()

    plan = plan_for(
        step
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: float(
                "nan"
            ),
        )
    )

    with pytest.raises(
        RuntimeGuiStepAuthorityProvenanceError,
        match="clock",
    ):
        store._issue_authorized_plan(
            plan,
            GOAL,
            explicit_decision(
                step
            ),
        )


def test_noncallable_clock_is_rejected_before_use():
    with pytest.raises(
        TypeError,
        match="clock",
    ):
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=None
        )


def test_provenance_contracts_are_immutable():
    (
        _store,
        batch,
        _plan,
        _step,
        _decision,
    ) = issued_explicit()

    provenance = (
        batch.step_provenances[
            0
        ]
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        provenance.step_id = (
            "other"
        )

    with pytest.raises(
        FrozenInstanceError
    ):
        batch.human_goal = (
            "other"
        )


def test_equal_value_reconstructed_provenance_is_not_store_source():
    (
        store,
        batch,
        plan,
        step,
        _decision,
    ) = issued_explicit()

    active = (
        batch.step_provenances[
            0
        ]
    )

    reconstructed = replace(
        active
    )

    assert reconstructed == active

    assert reconstructed is not active

    assert (
        store.get_current(
            plan,
            step,
        )
        is active
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is not reconstructed
    )


def test_module_has_no_execution_focus_or_permission_surface():
    path = Path(
        __file__
    ).with_name(
        "gui_step_authority_provenance.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    forbidden = (
        "pyautogui",
        "computer_tools",
        "focus_target",
        "AXUIElement",
        "ApplicationServices",
        "AppKit",
        "CoreFoundation",
        "request_confirmation",
        "get_permission_level",
        "PermissionLevel",
    )

    for marker in forbidden:
        assert marker not in text


def test_runtime_provenance_has_no_execution_methods():
    (
        _store,
        batch,
        _plan,
        _step,
        _decision,
    ) = issued_explicit()

    provenance = (
        batch.step_provenances[
            0
        ]
    )

    forbidden = (
        "execute",
        "type_text",
        "click",
        "focus",
        "consume",
        "claim",
        "permission",
        "approved",
        "receipt",
    )

    for name in forbidden:
        assert not hasattr(
            provenance,
            name,
        )


def blank_explicit_plan():
    step = GoalStep(
        id="producer-step",
        objective="Type requested text",
        planned_tool="type_text",
    )

    plan = GoalPlan(
        goal=GOAL,
        steps=[
            step,
        ],
        current_step_id=(
            step.id
        ),
    )

    return (
        plan,
        step,
    )


def test_producer_derives_authority_and_publishes_exact_graph():
    import app.agent.gui_step_authority_provenance as module

    plan, step = (
        blank_explicit_plan()
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=GOAL,
        plan=plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert produced.decision.allowed

    assert (
        produced.provenance.plan
        is plan
    )

    assert (
        step.gui_authority
        == GUI_AUTHORITY_CONFIRMED
    )

    assert (
        step.gui_authority_goal
        == GOAL
    )

    provenance = (
        store.get_current(
            plan,
            step,
        )
    )

    assert provenance is not None

    assert (
        provenance.step
        is step
    )

    assert (
        provenance.authority_decision
        is produced.decision
    )


def test_producer_erases_preseeded_planner_authority_before_derivation():
    import app.agent.gui_step_authority_provenance as module

    plan, step = (
        blank_explicit_plan()
    )

    step.gui_authority = (
        GUI_AUTHORITY_CONFIRMED
    )

    step.gui_authority_goal = (
        'type "planner forged text"'
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=GOAL,
        plan=plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert produced.decision.allowed

    assert (
        step.gui_authority
        == GUI_AUTHORITY_CONFIRMED
    )

    assert (
        step.gui_authority_goal
        == GOAL
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is not None
    )


def test_producer_owns_authority_decision_creation():
    import inspect
    import app.agent.gui_step_authority_provenance as module

    signature = inspect.signature(
        module
        .RuntimeGuiStepAuthorityProducer
        .authorize_plan
    )

    assert (
        "authority_decision"
        not in signature.parameters
    )

    assert (
        "decision"
        not in signature.parameters
    )

    assert (
        "provenance"
        not in signature.parameters
    )

    assert (
        "step_provenance"
        not in signature.parameters
    )


def test_rejected_producer_attempt_clears_previous_graph():
    import app.agent.gui_step_authority_provenance as module

    first_plan, first_step = (
        blank_explicit_plan()
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    first = producer.authorize_plan(
        goal=GOAL,
        plan=first_plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert first.decision.allowed

    assert (
        store.get_current(
            first_plan,
            first_step,
        )
        is not None
    )

    second_step = GoalStep(
        id="second",
        objective="Click something",
        planned_tool="click",
    )

    second_plan = GoalPlan(
        goal="just explain something",
        steps=[
            second_step,
        ],
        current_step_id=(
            second_step.id
        ),
    )

    second = producer.authorize_plan(
        goal=second_plan.goal,
        plan=second_plan,
        confirmation_fn=None,
    )

    assert not second.decision.allowed

    assert len(
        store
    ) == 0


def test_confirmation_expansion_producer_publishes_confirmed_authority():
    import app.agent.gui_step_authority_provenance as module

    step = GoalStep(
        id="confirmed",
        objective="Type generated content",
        planned_tool="type_text",
    )

    plan = GoalPlan(
        goal="complete the form",
        steps=[
            step,
        ],
        current_step_id=(
            step.id
        ),
    )

    confirmations = []

    def confirm(
        tool_name,
        arguments,
    ):
        confirmations.append(
            (
                tool_name,
                arguments,
            )
        )

        return True

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=plan.goal,
        plan=plan,
        confirmation_fn=confirm,
    )

    assert produced.decision.allowed

    assert confirmations

    assert (
        step.gui_authority
        == GUI_AUTHORITY_CONFIRMED
    )

    provenance = (
        store.get_current(
            plan,
            step,
        )
    )

    assert provenance is not None

    assert (
        provenance.gui_authority
        == GUI_AUTHORITY_CONFIRMED
    )


def test_denied_confirmation_never_publishes_runtime_provenance():
    import app.agent.gui_step_authority_provenance as module

    step = GoalStep(
        id="denied",
        objective="Type generated content",
        planned_tool="type_text",
    )

    plan = GoalPlan(
        goal="complete the form",
        steps=[
            step,
        ],
        current_step_id=(
            step.id
        ),
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=plan.goal,
        plan=plan,
        confirmation_fn=(
            lambda *_args: False
        ),
    )

    assert not produced.decision.allowed

    assert produced.provenance is None

    assert len(
        store
    ) == 0


def test_provenance_publication_failure_converts_allowed_to_rejection():
    import app.agent.gui_step_authority_provenance as module

    plan, _step = (
        blank_explicit_plan()
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: float(
                "nan"
            ),
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=GOAL,
        plan=plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert not produced.decision.allowed

    assert produced.provenance is None

    assert produced.diagnostics == (
        "provenance_publication_failed",
    )

    assert len(
        store
    ) == 0


def test_store_has_no_public_authority_publication_surface():
    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    for name in (
        "issue",
        "publish",
        "put",
        "authorize",
        "authorize_plan",
    ):
        assert not hasattr(
            store,
            name,
        )


def test_global_runtime_store_has_no_public_issue_surface():
    import app.agent.gui_step_authority_provenance as module

    assert not hasattr(
        module.RUNTIME_GUI_STEP_AUTHORITY,
        "issue",
    )

    assert not hasattr(
        module.RUNTIME_GUI_STEP_AUTHORITY,
        "publish",
    )

    assert hasattr(
        module.RUNTIME_GUI_STEP_AUTHORITY_PRODUCER,
        "authorize_plan",
    )


def test_private_publication_is_used_only_by_owning_producer_in_production():
    from pathlib import Path

    root = Path(
        __file__
    ).parents[
        1
    ]

    marker = (
        "._issue_authorized_plan("
    )

    production_hits = []

    for path in root.rglob(
        "*.py"
    ):
        if path.name.startswith(
            "test_"
        ):
            continue

        text = path.read_text(
            encoding="utf-8"
        )

        count = text.count(
            marker
        )

        if count:
            production_hits.append(
                (
                    path.relative_to(
                        root.parent
                    ).as_posix(),
                    count,
                )
            )

    assert production_hits == [
        (
            "app/agent/"
            "gui_step_authority_provenance.py",
            1,
        ),
    ]


def test_valid_looking_values_cannot_use_public_store_api():
    import app.agent.gui_step_authority_provenance as module

    forged_step = GoalStep(
        id="forged-publication",
        objective="Type forged text",
        planned_tool="type_text",
        gui_authority=(
            GUI_AUTHORITY_EXPLICIT
        ),
        gui_authority_goal=(
            'type "forged text"'
        ),
    )

    forged_plan = GoalPlan(
        goal='type "forged text"',
        steps=[
            forged_step,
        ],
        current_step_id=(
            forged_step.id
        ),
    )

    forged_decision = (
        GuiPlanAuthorityDecision(
            allowed=True,
            explicit_steps=(
                forged_step.id,
            ),
        )
    )

    store = (
        module
        .RUNTIME_GUI_STEP_AUTHORITY
    )

    assert not hasattr(
        store,
        "issue",
    )

    assert not hasattr(
        store,
        "publish",
    )

    assert (
        forged_decision.allowed
        is True
    )

    assert (
        forged_step.gui_authority
        == GUI_AUTHORITY_EXPLICIT
    )

    assert (
        store.get_current(
            forged_plan,
            forged_step,
        )
        is None
    )


def type_text_step_with_target(
    *,
    target_text="First Name",
):
    return GoalStep(
        id="typing-target-step",
        objective="Type requested text into field",
        planned_tool="type_text",
        gui_target_intent={
            "role": "AXTextField",
            "subrole": None,
            "text": target_text,
            "require_enabled": True,
            "require_positive_area": True,
        },
    )


def test_runtime_provenance_freezes_semantic_target_intent_value():
    import app.agent.gui_step_authority_provenance as module
    from app.agent.gui_target_intent import (
        StructuredUITargetIntent,
    )

    goal = (
        'type "Alice" into First Name'
    )

    step = (
        type_text_step_with_target()
    )

    plan = GoalPlan(
        goal=goal,
        steps=[
            step,
        ],
        current_step_id=(
            step.id
        ),
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=goal,
        plan=plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert produced.decision.allowed

    provenance = store.get_current(
        plan,
        step,
    )

    assert provenance is not None

    snapshot = (
        provenance
        .semantic_target_intent_snapshot
    )

    assert (
        type(snapshot)
        is StructuredUITargetIntent
    )

    assert snapshot.role == (
        "AXTextField"
    )

    assert snapshot.text == (
        "First Name"
    )

    assert snapshot.require_enabled is True

    assert (
        snapshot.require_positive_area
        is True
    )

    assert (
        snapshot.to_dict()
        == step.gui_target_intent
    )


def test_semantic_target_snapshot_is_not_target_authority():
    import app.agent.gui_step_authority_provenance as module

    goal = (
        'type "Alice" into First Name'
    )

    step = (
        type_text_step_with_target()
    )

    plan = GoalPlan(
        goal=goal,
        steps=[
            step,
        ],
        current_step_id=(
            step.id
        ),
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=goal,
        plan=plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert produced.decision.allowed

    provenance = store.get_current(
        plan,
        step,
    )

    snapshot = (
        provenance
        .semantic_target_intent_snapshot
    )

    for forbidden in (
        "authorized",
        "authority",
        "permission",
        "approved",
        "attestation",
        "receipt",
        "verified",
        "focused",
        "focus",
        "execute",
        "click",
    ):
        assert not hasattr(
            snapshot,
            forbidden,
        )


def test_mutating_semantic_target_intent_invalidates_runtime_provenance():
    import app.agent.gui_step_authority_provenance as module

    goal = (
        'type "Alice" into First Name'
    )

    step = (
        type_text_step_with_target()
    )

    plan = GoalPlan(
        goal=goal,
        steps=[
            step,
        ],
        current_step_id=(
            step.id
        ),
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=goal,
        plan=plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert produced.decision.allowed

    provenance = store.get_current(
        plan,
        step,
    )

    assert provenance is not None

    step.gui_target_intent[
        "text"
    ] = "Last Name"

    assert (
        store.get_current(
            plan,
            step,
        )
        is None
    )

    assert len(
        store
    ) == 0


def test_replacing_target_dict_with_equal_value_keeps_semantic_snapshot_current():
    import app.agent.gui_step_authority_provenance as module

    goal = (
        'type "Alice" into First Name'
    )

    step = (
        type_text_step_with_target()
    )

    plan = GoalPlan(
        goal=goal,
        steps=[
            step,
        ],
        current_step_id=(
            step.id
        ),
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=goal,
        plan=plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert produced.decision.allowed

    provenance = store.get_current(
        plan,
        step,
    )

    original_dict = (
        step.gui_target_intent
    )

    replacement = dict(
        original_dict
    )

    assert replacement == original_dict

    assert replacement is not (
        original_dict
    )

    step.gui_target_intent = (
        replacement
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is provenance
    )


def test_malformed_semantic_target_data_cannot_publish_runtime_provenance():
    import app.agent.gui_step_authority_provenance as module

    goal = (
        'type "Alice" into First Name'
    )

    step = GoalStep(
        id="bad-target",
        objective="Type",
        planned_tool="type_text",
        gui_target_intent={
            "role": "AXTextField",
            "text": "First Name",
            "authorized": True,
        },
    )

    plan = GoalPlan(
        goal=goal,
        steps=[
            step,
        ],
        current_step_id=(
            step.id
        ),
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=goal,
        plan=plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert not produced.decision.allowed

    assert produced.provenance is None

    assert produced.diagnostics == (
        "provenance_publication_failed",
    )

    assert len(
        store
    ) == 0


def test_type_text_without_target_intent_has_no_semantic_snapshot():
    import app.agent.gui_step_authority_provenance as module

    goal = (
        'type "hello"'
    )

    step = GoalStep(
        id="no-target",
        objective="Type requested text",
        planned_tool="type_text",
    )

    plan = GoalPlan(
        goal=goal,
        steps=[
            step,
        ],
        current_step_id=(
            step.id
        ),
    )

    store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: 100.0,
        )
    )

    producer = (
        module
        .RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    produced = producer.authorize_plan(
        goal=goal,
        plan=plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert produced.decision.allowed

    provenance = store.get_current(
        plan,
        step,
    )

    assert provenance is not None

    assert (
        provenance
        .semantic_target_intent_snapshot
        is None
    )


def test_snapshot_support_allows_8d4_type_text_target_planning():
    import json

    from app.agent.capability_registry import (
        create_default_capability_registry,
    )

    from app.agent.goal_decomposer import (
        GoalDecomposer,
    )

    registry = (
        create_default_capability_registry()
    )

    capability = None

    for name in registry.names():
        if (
            "type_text"
            in registry.tools_for(
                name
            )
        ):
            capability = name
            break

    assert capability is not None

    payload = {
        "goal": (
            'type "Alice" into First Name'
        ),
        "steps": [
            {
                "id": "typing-step",
                "objective": (
                    "Type Alice into First Name"
                ),
                "dependencies": [],
                "success_criteria": [
                    (
                        "First Name contains "
                        "Alice"
                    ),
                ],
                "required_capabilities": [
                    capability,
                ],
                "planned_tool": (
                    "type_text"
                ),
                "gui_target_intent": {
                    "role": "AXTextField",
                    "subrole": None,
                    "text": "First Name",
                    "require_enabled": True,
                    "require_positive_area": True,
                },
                "risk_level": "normal",
                "artifacts": [],
                "verification_requirements": [
                    (
                        "Verify First Name "
                        "contains Alice."
                    ),
                ],
            },
        ],
    }

    plan, error = (
        GoalDecomposer.parse_plan(
            json.dumps(
                payload
            ),
            capability_registry=registry,
        )
    )

    assert error is None
    assert plan is not None

    step = (
        plan.steps[0]
    )

    assert (
        step.planned_tool
        == "type_text"
    )

    assert (
        step.gui_target_intent
        is not None
    )

    assert (
        step.gui_authority
        == ""
    )

    assert (
        step.gui_authority_goal
        == ""
    )
