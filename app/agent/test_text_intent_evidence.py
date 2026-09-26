from dataclasses import (
    FrozenInstanceError,
    replace,
)
from pathlib import Path

import pytest

import app.agent.text_intent_evidence as text_intent
from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
)
from app.agent.gui_step_authority_provenance import (
    RuntimeGuiStepAuthorityProvenance,
    RuntimeGuiStepAuthorityProvenanceStore,
    RuntimeGuiStepAuthorityProducer,
)
from app.agent.text_intent_evidence import (
    EXACT_TEXT_INTENT_MAX_AGE_SECONDS,
    TEXT_INTENT_STATUS_MATCHED,
    TEXT_INTENT_STATUS_UNKNOWN,
    ExactTextIntentEvidence,
    ExactTextIntentEvidenceResult,
    derive_exact_text_intent_evidence,
    exact_explicit_text_payloads,
)


GOAL = (
    'type "hello   world"'
)


def active_provenance(
    monkeypatch,
    *,
    goal=GOAL,
    planned_tool="type_text",
    step_id="step-1",
):
    step = GoalStep(
        id=step_id,
        objective="Runtime GUI action",
        planned_tool=planned_tool,
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
        RuntimeGuiStepAuthorityProducer(
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

    assert (
        type(provenance)
        is RuntimeGuiStepAuthorityProvenance
    )

    monkeypatch.setattr(
        text_intent,
        "RUNTIME_GUI_STEP_AUTHORITY",
        store,
    )

    return (
        store,
        produced,
        provenance,
        plan,
        step,
    )


def derive(
    monkeypatch,
    payload,
    *,
    goal=GOAL,
    now=100.1,
):
    (
        store,
        produced,
        provenance,
        plan,
        step,
    ) = active_provenance(
        monkeypatch,
        goal=goal,
    )

    result = (
        derive_exact_text_intent_evidence(
            provenance,
            payload,
            clock=lambda: now,
        )
    )

    return (
        result,
        store,
        produced,
        provenance,
        plan,
        step,
    )


def test_exact_quoted_payload_preserves_repeated_spaces(
    monkeypatch,
):
    (
        result,
        _store,
        _produced,
        provenance,
        _plan,
        step,
    ) = derive(
        monkeypatch,
        "hello   world",
    )

    assert result.status == (
        TEXT_INTENT_STATUS_MATCHED
    )

    assert result.matched

    assert (
        result.evidence.raw_text
        == "hello   world"
    )

    assert (
        result.evidence
        .authority_provenance
        is provenance
    )

    assert (
        result.evidence.source_step
        is step
    )


def test_normalized_space_substitution_is_rejected(
    monkeypatch,
):
    (
        result,
        *_rest,
    ) = derive(
        monkeypatch,
        "hello world",
    )

    assert result.status == (
        TEXT_INTENT_STATUS_UNKNOWN
    )

    assert result.diagnostics == (
        "exact_text_not_authorized",
    )


@pytest.mark.parametrize(
    "payload",
    (
        "hello\tworld",
        "hello\nworld",
        "  leading",
        "trailing  ",
        "a  \n\t  b",
    ),
)
def test_exact_quoted_payload_preserves_whitespace(
    monkeypatch,
    payload,
):
    goal = (
        'type "'
        + payload
        + '"'
    )

    (
        result,
        *_rest,
    ) = derive(
        monkeypatch,
        payload,
        goal=goal,
    )

    assert result.matched

    assert (
        result.evidence.raw_text
        == payload
    )


def test_exact_into_form_preserves_internal_spacing(
    monkeypatch,
):
    goal = (
        "type hello   world into the field"
    )

    assert (
        exact_explicit_text_payloads(
            goal
        )
        == (
            "hello   world",
        )
    )

    (
        result,
        *_rest,
    ) = derive(
        monkeypatch,
        "hello   world",
        goal=goal,
    )

    assert result.matched


def test_exact_colon_form_preserves_internal_spacing(
    monkeypatch,
):
    goal = (
        "type the following: "
        "alpha   beta"
    )

    assert (
        exact_explicit_text_payloads(
            goal
        )
        == (
            "alpha   beta",
        )
    )

    (
        result,
        *_rest,
    ) = derive(
        monkeypatch,
        "alpha   beta",
        goal=goal,
    )

    assert result.matched


def test_write_verb_is_not_silently_added_to_exact_extractor(
    monkeypatch,
):
    goal = (
        'write "hello"'
    )

    (
        result,
        *_rest,
    ) = derive(
        monkeypatch,
        "hello",
        goal=goal,
    )

    assert not result.matched

    assert result.diagnostics == (
        "exact_text_not_authorized",
    )


def test_multiple_payloads_remain_individually_exact(
    monkeypatch,
):
    goal = (
        'type "first" then '
        'type "second  value"'
    )

    assert (
        exact_explicit_text_payloads(
            goal
        )
        == (
            "first",
            "second  value",
        )
    )

    (
        result,
        *_rest,
    ) = derive(
        monkeypatch,
        "second  value",
        goal=goal,
    )

    assert result.matched


def test_confirmed_action_class_does_not_authorize_normalized_text(
    monkeypatch,
):
    (
        _store,
        produced,
        provenance,
        _plan,
        _step,
    ) = active_provenance(
        monkeypatch,
        goal=GOAL,
    )

    assert produced.decision.allowed

    result = (
        derive_exact_text_intent_evidence(
            provenance,
            "hello world",
            clock=lambda: 100.1,
        )
    )

    assert not result.matched

    assert result.diagnostics == (
        "exact_text_not_authorized",
    )


def test_naked_goalstep_is_rejected_even_with_valid_runtime_fields(
    monkeypatch,
):
    (
        _store,
        _produced,
        provenance,
        _plan,
        step,
    ) = active_provenance(
        monkeypatch
    )

    forged = GoalStep(
        id=step.id,
        objective=step.objective,
        planned_tool=(
            provenance.planned_tool
        ),
        gui_authority=(
            provenance.gui_authority
        ),
        gui_authority_goal=(
            provenance.human_goal
        ),
    )

    result = (
        derive_exact_text_intent_evidence(
            forged,
            "hello   world",
            clock=lambda: 100.1,
        )
    )

    assert result.diagnostics == (
        "invalid_authority_provenance",
    )


def test_equal_value_reconstructed_provenance_is_rejected(
    monkeypatch,
):
    (
        _store,
        _produced,
        provenance,
        _plan,
        _step,
    ) = active_provenance(
        monkeypatch
    )

    reconstructed = replace(
        provenance
    )

    assert reconstructed == provenance

    assert reconstructed is not provenance

    result = (
        derive_exact_text_intent_evidence(
            reconstructed,
            "hello   world",
            clock=lambda: 100.1,
        )
    )

    assert result.diagnostics == (
        "inactive_authority_provenance",
    )


def test_wrong_gui_tool_provenance_cannot_create_text_evidence(
    monkeypatch,
):
    (
        store,
        _produced,
        provenance,
        plan,
        step,
    ) = active_provenance(
        monkeypatch,
        goal="click the button",
        planned_tool="click",
    )

    assert (
        store.get_current(
            plan,
            step,
        )
        is provenance
    )

    result = (
        derive_exact_text_intent_evidence(
            provenance,
            "anything",
            clock=lambda: 100.1,
        )
    )

    assert result.diagnostics == (
        "wrong_planned_tool",
    )


def test_clearing_runtime_authority_store_invalidates_evidence(
    monkeypatch,
):
    (
        result,
        store,
        _produced,
        _provenance,
        _plan,
        _step,
    ) = derive(
        monkeypatch,
        "hello   world",
    )

    evidence = (
        result.evidence
    )

    assert evidence.is_current(
        100.2
    )

    store.clear()

    assert not evidence.is_current(
        100.3
    )


def test_current_step_change_invalidates_evidence(
    monkeypatch,
):
    (
        result,
        _store,
        _produced,
        _provenance,
        plan,
        _step,
    ) = derive(
        monkeypatch,
        "hello   world",
    )

    plan.current_step_id = ""

    assert not (
        result.evidence
        .is_current(
            100.2
        )
    )


def test_step_authority_mutation_invalidates_evidence(
    monkeypatch,
):
    (
        result,
        _store,
        _produced,
        _provenance,
        _plan,
        step,
    ) = derive(
        monkeypatch,
        "hello   world",
    )

    step.gui_authority_goal = (
        'type "other"'
    )

    assert not (
        result.evidence
        .is_current(
            100.2
        )
    )


def test_step_replacement_invalidates_evidence(
    monkeypatch,
):
    (
        result,
        _store,
        _produced,
        _provenance,
        plan,
        step,
    ) = derive(
        monkeypatch,
        "hello   world",
    )

    plan.steps[
        0
    ] = replace(
        step
    )

    assert not (
        result.evidence
        .is_current(
            100.2
        )
    )


def test_new_runtime_authority_graph_invalidates_old_text_evidence(
    monkeypatch,
):
    (
        result,
        store,
        _produced,
        _provenance,
        _plan,
        _step,
    ) = derive(
        monkeypatch,
        "hello   world",
    )

    evidence = (
        result.evidence
    )

    second_step = GoalStep(
        id="step-2",
        objective="Second",
        planned_tool="type_text",
    )

    second_goal = (
        'type "second"'
    )

    second_plan = GoalPlan(
        goal=second_goal,
        steps=[
            second_step,
        ],
        current_step_id=(
            second_step.id
        ),
    )

    producer = (
        RuntimeGuiStepAuthorityProducer(
            store=store
        )
    )

    second = producer.authorize_plan(
        goal=second_goal,
        plan=second_plan,
        confirmation_fn=(
            lambda *_args: True
        ),
    )

    assert second.decision.allowed

    assert not evidence.is_current(
        100.2
    )


def test_direct_constructor_rejects_reconstructed_provenance(
    monkeypatch,
):
    (
        _store,
        _produced,
        provenance,
        _plan,
        _step,
    ) = active_provenance(
        monkeypatch
    )

    reconstructed = replace(
        provenance
    )

    with pytest.raises(
        ValueError,
        match="active runtime",
    ):
        ExactTextIntentEvidence(
            authority_provenance=(
                reconstructed
            ),
            source_step_id=(
                reconstructed.step_id
            ),
            source_planned_tool="type_text",
            source_gui_authority=(
                reconstructed.gui_authority
            ),
            source_human_goal=(
                reconstructed.human_goal
            ),
            raw_text="hello   world",
            issued_at_monotonic=100.1,
            expires_at_monotonic=(
                100.1
                + EXACT_TEXT_INTENT_MAX_AGE_SECONDS
            ),
        )


def test_direct_constructor_rejects_normalized_text_substitution(
    monkeypatch,
):
    (
        _store,
        _produced,
        provenance,
        _plan,
        _step,
    ) = active_provenance(
        monkeypatch
    )

    with pytest.raises(
        ValueError,
        match="exactly authorized",
    ):
        ExactTextIntentEvidence(
            authority_provenance=(
                provenance
            ),
            source_step_id=(
                provenance.step_id
            ),
            source_planned_tool="type_text",
            source_gui_authority=(
                provenance.gui_authority
            ),
            source_human_goal=(
                provenance.human_goal
            ),
            raw_text="hello world",
            issued_at_monotonic=100.1,
            expires_at_monotonic=(
                100.1
                + EXACT_TEXT_INTENT_MAX_AGE_SECONDS
            ),
        )


def test_evidence_cannot_predate_authority_provenance(
    monkeypatch,
):
    (
        _store,
        _produced,
        provenance,
        _plan,
        _step,
    ) = active_provenance(
        monkeypatch
    )

    result = (
        derive_exact_text_intent_evidence(
            provenance,
            "hello   world",
            clock=lambda: 99.9,
        )
    )

    assert result.diagnostics == (
        "clock_unavailable",
    )


def test_exact_evidence_expires_after_fixed_short_lifetime(
    monkeypatch,
):
    (
        result,
        *_rest,
    ) = derive(
        monkeypatch,
        "hello   world",
    )

    evidence = (
        result.evidence
    )

    assert (
        evidence.expires_at_monotonic
        == pytest.approx(
            105.1
        )
    )

    assert evidence.is_current(
        105.099
    )

    assert not evidence.is_current(
        105.1
    )


@pytest.mark.parametrize(
    "clock",
    (
        lambda: float("nan"),
        lambda: float("inf"),
        lambda: -1.0,
    ),
)
def test_invalid_clock_fails_closed(
    monkeypatch,
    clock,
):
    (
        _store,
        _produced,
        provenance,
        _plan,
        _step,
    ) = active_provenance(
        monkeypatch
    )

    result = (
        derive_exact_text_intent_evidence(
            provenance,
            "hello   world",
            clock=clock,
        )
    )

    assert result.diagnostics == (
        "clock_unavailable",
    )


def test_noncallable_clock_fails_closed(
    monkeypatch,
):
    (
        _store,
        _produced,
        provenance,
        _plan,
        _step,
    ) = active_provenance(
        monkeypatch
    )

    result = (
        derive_exact_text_intent_evidence(
            provenance,
            "hello   world",
            clock=None,
        )
    )

    assert result.diagnostics == (
        "clock_unavailable",
    )


def test_result_contract_rejects_forged_combinations():
    with pytest.raises(
        ValueError
    ):
        ExactTextIntentEvidenceResult(
            status=(
                TEXT_INTENT_STATUS_MATCHED
            ),
        )

    with pytest.raises(
        ValueError
    ):
        ExactTextIntentEvidenceResult(
            status=(
                TEXT_INTENT_STATUS_UNKNOWN
            ),
            diagnostics=(
                "made_up",
            ),
        )


def test_evidence_and_result_are_immutable(
    monkeypatch,
):
    (
        result,
        *_rest,
    ) = derive(
        monkeypatch,
        "hello   world",
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        result.evidence.raw_text = (
            "other"
        )

    with pytest.raises(
        FrozenInstanceError
    ):
        result.status = (
            TEXT_INTENT_STATUS_UNKNOWN
        )


def test_module_has_no_focus_permission_or_execution_surface():
    path = Path(
        __file__
    ).with_name(
        "text_intent_evidence.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    forbidden = (
        "pyautogui",
        "computer_tools",
        "focus_target_provenance",
        "FocusTargetProvenance",
        "AXUIElement",
        "ApplicationServices",
        "AppKit",
        "CoreFoundation",
        "request_confirmation",
        "PermissionLevel",
    )

    for marker in forbidden:
        assert marker not in text


def test_evidence_has_no_keyboard_or_focus_authority_surface(
    monkeypatch,
):
    (
        result,
        *_rest,
    ) = derive(
        monkeypatch,
        "hello   world",
    )

    evidence = (
        result.evidence
    )

    forbidden = (
        "permission",
        "approved",
        "attestation",
        "receipt",
        "focus",
        "focus_provenance",
        "keyboard_authority",
        "execute",
        "consume",
        "claim",
    )

    for name in forbidden:
        assert not hasattr(
            evidence,
            name,
        )


def test_extractor_never_uses_whitespace_normalizer():
    path = Path(
        __file__
    ).with_name(
        "text_intent_evidence.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    assert (
        "_normalized_spaces"
        not in text
    )

    assert (
        "match.group("
        in text
    )


def test_derivation_signature_has_no_goalstep_parameter():
    import inspect

    signature = inspect.signature(
        derive_exact_text_intent_evidence
    )

    assert (
        "source_step"
        not in signature.parameters
    )

    assert (
        "authority_provenance"
        in signature.parameters
    )
