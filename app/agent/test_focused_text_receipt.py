from dataclasses import (
    FrozenInstanceError,
    replace,
)
import hashlib
import inspect
from pathlib import Path

import pytest

import app.agent.text_intent_evidence as text_intent_module
from app.agent.focused_text_receipt import (
    FOCUSED_TEXT_RECEIPT_MAX_AGE_SECONDS,
    FOCUSED_TEXT_RECEIPT_STATUS_MATCHED,
    FOCUSED_TEXT_RECEIPT_STATUS_UNKNOWN,
    FOCUSED_TEXT_RECEIPTS,
    FocusedTextReceipt,
    FocusedTextReceiptProducer,
    FocusedTextReceiptProduction,
    FocusedTextReceiptStore,
    compose_focused_text_receipt,
)
from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
)
from app.agent.gui_step_authority_provenance import (
    RuntimeGuiStepAuthorityProducer,
    RuntimeGuiStepAuthorityProvenanceStore,
)
from app.agent.gui_target_evidence_carrier import (
    StructuredUIVisualTargetEvidenceStore,
)
from app.agent.gui_target_evidence_producer import (
    produce_structured_ui_visual_target_evidence,
)
from app.agent.test_gui_target_evidence_producer import (
    inputs,
    sequence_clock,
    visual,
)
from app.agent.text_intent_evidence import (
    derive_exact_text_intent_evidence,
)
from app.ui_observation.focus_target_provenance import (
    FocusTargetProvenance,
    compose_focus_target_provenance,
)
from app.ui_observation.test_focus_target_provenance import (
    _shift_focus_to_bound_at,
    matched_correlation,
)


GOAL = (
    'Click Save and type "Alice"'
)


def goal_digest(
    goal=GOAL,
):
    return hashlib.sha256(
        goal.strip().encode(
            "utf-8"
        )
    ).hexdigest()


def joined_fixture(
    monkeypatch,
    *,
    step_target=None,
    b8_goal=GOAL,
):
    verification = visual(
        goal_sha256=(
            goal_digest(
                b8_goal
            )
        )
    )

    values = inputs(
        monkeypatch,
        verification=verification,
    )

    values[
        "human_goal"
    ] = b8_goal

    target_store = (
        StructuredUIVisualTargetEvidenceStore()
    )

    produced_target = (
        produce_structured_ui_visual_target_evidence(
            **values,
            store=target_store,
            clock=sequence_clock(
                104.0,
                109.0,
                109.25,
                109.5,
                109.75,
                110.0,
            ),
        )
    )

    assert produced_target.issued

    target_production = (
        produced_target.production
    )

    target_intent = (
        target_production
        .orchestration_result
        .intent
    )

    if step_target is None:
        step_target = (
            target_intent.to_dict()
        )

    step = GoalStep(
        id="typing-step",
        objective=(
            "Type the exact requested text "
            "into the intended field."
        ),
        planned_tool="type_text",
        gui_target_intent=(
            step_target
        ),
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

    authority_now = (
        target_production
        .carrier
        .issued_at_monotonic
        + 0.01
    )

    authority_store = (
        RuntimeGuiStepAuthorityProvenanceStore(
            clock=lambda: authority_now,
        )
    )

    authority_producer = (
        RuntimeGuiStepAuthorityProducer(
            store=authority_store
        )
    )

    authority = (
        authority_producer
        .authorize_plan(
            goal=GOAL,
            plan=plan,
            confirmation_fn=(
                lambda *_args: True
            ),
        )
    )

    assert authority.decision.allowed

    authority_provenance = (
        authority_store
        .get_current(
            plan,
            step,
        )
    )

    assert authority_provenance is not None

    monkeypatch.setattr(
        text_intent_module,
        "RUNTIME_GUI_STEP_AUTHORITY",
        authority_store,
    )

    text_now = (
        authority_now
        + 0.01
    )

    text_result = (
        derive_exact_text_intent_evidence(
            authority_provenance,
            "Alice",
            clock=lambda: text_now,
        )
    )

    assert text_result.matched

    text_evidence = (
        text_result.evidence
    )

    semantic_result = (
        target_production
        .orchestration_result
        .revalidation_result
    )

    semantic = (
        semantic_result
        .revalidation
    )

    wanted_focus_bound = (
        semantic
        .revalidated_at_monotonic
        + 0.01
    )

    focus_source = (
        _shift_focus_to_bound_at(
            wanted_focus_bound
        )
    )

    prerequisite = max(
        semantic
        .revalidated_at_monotonic,
        focus_source
        .binding
        .bound_at_monotonic,
    )

    source_expiry = min(
        semantic
        .expires_at_monotonic,
        focus_source
        .binding
        .expires_at_monotonic,
    )

    room = (
        source_expiry
        - prerequisite
    )

    assert room > 0

    gap = min(
        0.01,
        room / 4,
    )

    assert gap > 0

    captured = (
        prerequisite
        + gap
    )

    focus_issued = (
        captured
        + gap
    )

    correlation = (
        matched_correlation(
            semantic_result,
            focus=focus_source,
            captured=captured,
        )
    )

    focus_provenance = (
        compose_focus_target_provenance(
            semantic_result,
            focus_source,
            correlation,
            clock=lambda: focus_issued,
        )
    )

    assert (
        type(focus_provenance)
        is FocusTargetProvenance
    )

    receipt_now = max(
        text_now
        + 0.01,
        focus_issued
        + 0.01,
        target_production
        .carrier
        .issued_at_monotonic
        + 0.03,
    )

    focus_get = (
        lambda candidate: (
            focus_provenance
            if candidate
            is focus_provenance
            else None
        )
    )

    receipt_store = (
        FocusedTextReceiptStore(
            clock=lambda: receipt_now,
            focus_get=focus_get,
        )
    )

    receipt_producer = (
        FocusedTextReceiptProducer(
            receipt_store=receipt_store,
            target_store=target_store,
            focus_get=focus_get,
            clock=lambda: receipt_now,
        )
    )

    return {
        "values": values,
        "target_store": target_store,
        "target_production": target_production,
        "target_intent": target_intent,
        "step": step,
        "plan": plan,
        "authority_store": authority_store,
        "authority_provenance": authority_provenance,
        "text_evidence": text_evidence,
        "semantic_result": semantic_result,
        "focus_provenance": focus_provenance,
        "focus_get": focus_get,
        "receipt_store": receipt_store,
        "receipt_producer": receipt_producer,
        "receipt_now": receipt_now,
    }


def test_happy_path_produces_exact_focused_text_receipt(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert produced.status == (
        FOCUSED_TEXT_RECEIPT_STATUS_MATCHED
    )

    assert produced.matched

    receipt = (
        produced.receipt
    )

    assert (
        receipt.text_evidence
        is fixture[
            "text_evidence"
        ]
    )

    assert (
        receipt.focus_provenance
        is fixture[
            "focus_provenance"
        ]
    )

    assert (
        receipt.semantic_result
        is fixture[
            "semantic_result"
        ]
    )

    assert (
        receipt.target_intent_snapshot
        is fixture[
            "authority_provenance"
        ]
        .semantic_target_intent_snapshot
    )

    assert (
        receipt.target_consumption
        is produced.target_consumption
    )

    assert (
        receipt.raw_text
        == "Alice"
    )

    assert (
        fixture[
            "receipt_store"
        ]
        .get(
            receipt
        )
        is receipt
    )


def test_step_target_matches_b8_intent_by_semantic_value(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    snapshot = (
        fixture[
            "authority_provenance"
        ]
        .semantic_target_intent_snapshot
    )

    orchestration_intent = (
        fixture[
            "target_production"
        ]
        .orchestration_result
        .intent
    )

    assert snapshot == (
        orchestration_intent
    )

    assert snapshot is not (
        orchestration_intent
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert produced.matched


def test_focus_must_preserve_exact_b7_object_identity(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    reconstructed = replace(
        fixture[
            "semantic_result"
        ]
    )

    assert reconstructed == (
        fixture[
            "semantic_result"
        ]
    )

    assert reconstructed is not (
        fixture[
            "semantic_result"
        ]
    )

    fake_focus = replace(
        fixture[
            "focus_provenance"
        ],
        semantic_result=(
            reconstructed
        ),
    )

    focus_get = (
        lambda candidate: (
            fake_focus
            if candidate
            is fake_focus
            else None
        )
    )

    store = (
        FocusedTextReceiptStore(
            clock=lambda: fixture[
                "receipt_now"
            ],
            focus_get=focus_get,
        )
    )

    producer = (
        FocusedTextReceiptProducer(
            receipt_store=store,
            target_store=fixture[
                "target_store"
            ],
            focus_get=focus_get,
            clock=lambda: fixture[
                "receipt_now"
            ],
        )
    )

    produced = producer.produce(
        fixture[
            "text_evidence"
        ],
        fake_focus,
        fixture[
            "values"
        ][
            "visual_verification"
        ],
    )

    assert not produced.matched

    assert produced.diagnostics == (
        "focus_target_mismatch",
    )

    assert len(
        store
    ) == 0


def test_reconstructed_focus_provenance_is_not_active(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    reconstructed = replace(
        fixture[
            "focus_provenance"
        ]
    )

    assert reconstructed == (
        fixture[
            "focus_provenance"
        ]
    )

    assert reconstructed is not (
        fixture[
            "focus_provenance"
        ]
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            reconstructed,
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert not produced.matched

    assert produced.diagnostics == (
        "focus_provenance_unavailable",
    )

    assert len(
        fixture[
            "receipt_store"
        ]
    ) == 0


def test_wrong_step_target_is_rejected_after_single_b8_consumption(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch,
        step_target={
            "role": "AXButton",
            "text": "Delete",
        },
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert not produced.matched

    assert produced.diagnostics == (
        "target_intent_mismatch",
    )

    assert len(
        fixture[
            "receipt_store"
        ]
    ) == 0

    second = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert not second.matched

    assert second.diagnostics == (
        "target_consumption_unavailable",
    )


def test_wrong_human_goal_cannot_cross_b8g_boundary(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch,
        b8_goal="Click Save",
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert not produced.matched

    assert produced.diagnostics == (
        "target_consumption_unavailable",
    )


def test_equal_value_visual_reconstruction_is_rejected(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    visual_copy = replace(
        fixture[
            "values"
        ][
            "visual_verification"
        ]
    )

    assert visual_copy == (
        fixture[
            "values"
        ][
            "visual_verification"
        ]
    )

    assert visual_copy is not (
        fixture[
            "values"
        ][
            "visual_verification"
        ]
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            visual_copy,
        )
    )

    assert not produced.matched

    assert produced.diagnostics == (
        "target_consumption_unavailable",
    )


def test_receipt_expiry_is_exact_shortest_source(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert produced.matched

    receipt = (
        produced.receipt
    )

    expected = min(
        receipt.text_evidence
        .expires_at_monotonic,
        receipt.target_consumption
        .carrier
        .expires_at_monotonic,
        receipt.focus_provenance
        .expires_at_monotonic,
        receipt.issued_at_monotonic
        + FOCUSED_TEXT_RECEIPT_MAX_AGE_SECONDS,
    )

    assert (
        receipt.expires_at_monotonic
        == expected
    )


def test_receipt_store_requires_exact_receipt_identity(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert produced.matched

    reconstructed = replace(
        produced.receipt
    )

    assert reconstructed == (
        produced.receipt
    )

    assert reconstructed is not (
        produced.receipt
    )

    assert (
        fixture[
            "receipt_store"
        ]
        .get(
            reconstructed
        )
        is None
    )

    assert (
        fixture[
            "receipt_store"
        ]
        .get(
            produced.receipt
        )
        is produced.receipt
    )


def test_focus_replacement_invalidates_active_receipt(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    active_focus = [
        fixture[
            "focus_provenance"
        ]
    ]

    focus_get = (
        lambda candidate: (
            active_focus[
                0
            ]
            if candidate
            is active_focus[
                0
            ]
            else None
        )
    )

    store = (
        FocusedTextReceiptStore(
            clock=lambda: fixture[
                "receipt_now"
            ],
            focus_get=focus_get,
        )
    )

    producer = (
        FocusedTextReceiptProducer(
            receipt_store=store,
            target_store=fixture[
                "target_store"
            ],
            focus_get=focus_get,
            clock=lambda: fixture[
                "receipt_now"
            ],
        )
    )

    produced = producer.produce(
        fixture[
            "text_evidence"
        ],
        fixture[
            "focus_provenance"
        ],
        fixture[
            "values"
        ][
            "visual_verification"
        ],
    )

    assert produced.matched

    active_focus[
        0
    ] = None

    assert (
        store.get(
            produced.receipt
        )
        is None
    )

    assert len(
        store
    ) == 0


def test_step_target_mutation_invalidates_active_receipt(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert produced.matched

    fixture[
        "step"
    ].gui_target_intent[
        "text"
    ] = "Delete"

    assert (
        fixture[
            "receipt_store"
        ]
        .get(
            produced.receipt
        )
        is None
    )


def test_producer_does_not_accept_prebuilt_consumption_or_target():
    signature = inspect.signature(
        FocusedTextReceiptProducer
        .produce
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
        "text_evidence",
        "focus_provenance",
        "visual_verification",
    )


def test_receipt_store_exposes_only_execution_claim_and_read_clear_surface():
    store = FocusedTextReceiptStore(
        clock=lambda: 100.0,
        focus_get=lambda _provenance: None,
    )

    assert callable(
        store.claim
    )

    assert callable(
        store.get
    )

    assert callable(
        store.clear
    )

    for name in (
        "consume",
        "issue",
        "publish",
    ):
        assert not hasattr(
            store,
            name,
        )


def test_receipt_and_result_are_immutable(
    monkeypatch,
):
    fixture = joined_fixture(
        monkeypatch
    )

    produced = (
        fixture[
            "receipt_producer"
        ]
        .produce(
            fixture[
                "text_evidence"
            ],
            fixture[
                "focus_provenance"
            ],
            fixture[
                "values"
            ][
                "visual_verification"
            ],
        )
    )

    assert produced.matched

    with pytest.raises(
        FrozenInstanceError
    ):
        produced.receipt.application_pid = 7

    with pytest.raises(
        FrozenInstanceError
    ):
        produced.status = (
            FOCUSED_TEXT_RECEIPT_STATUS_UNKNOWN
        )


def test_unknown_result_contract_is_strict():
    with pytest.raises(
        ValueError
    ):
        FocusedTextReceiptProduction(
            status=(
                FOCUSED_TEXT_RECEIPT_STATUS_UNKNOWN
            ),
            diagnostics=(
                "made_up",
            ),
        )

    with pytest.raises(
        ValueError
    ):
        FocusedTextReceiptProduction(
            status=(
                FOCUSED_TEXT_RECEIPT_STATUS_MATCHED
            ),
        )


def test_module_has_no_keyboard_execution_or_permission_surface():
    import ast

    path = Path(
        __file__
    ).with_name(
        "focused_text_receipt.py"
    )

    source = path.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(
        source,
        filename=str(
            path
        ),
    )

    forbidden_modules = {
        "pyautogui",
        "app.tools.computer_tools",
    }

    forbidden_symbols = {
        "PermissionLevel",
        "request_confirmation",
        "press_key",
    }

    imported_modules = set()
    imported_symbols = set()
    referenced_names = set()
    attribute_chains = set()

    def attribute_chain(
        node,
    ):
        parts = []

        while isinstance(
            node,
            ast.Attribute,
        ):
            parts.append(
                node.attr
            )
            node = node.value

        if isinstance(
            node,
            ast.Name,
        ):
            parts.append(
                node.id
            )
        else:
            return None

        return ".".join(
            reversed(
                parts
            )
        )

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            for alias in node.names:
                imported_modules.add(
                    alias.name
                )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            module = (
                node.module
                or ""
            )

            imported_modules.add(
                module
            )

            for alias in node.names:
                imported_symbols.add(
                    alias.name
                )

        elif isinstance(
            node,
            ast.Name,
        ):
            referenced_names.add(
                node.id
            )

        elif isinstance(
            node,
            ast.Attribute,
        ):
            chain = (
                attribute_chain(
                    node
                )
            )

            if chain is not None:
                attribute_chains.add(
                    chain
                )

    assert not (
        imported_modules
        & forbidden_modules
    )

    assert not (
        imported_symbols
        & forbidden_symbols
    )

    assert not (
        referenced_names
        & (
            forbidden_symbols
            | {
                "pyautogui",
            }
        )
    )

    assert (
        "keyboard.write"
        not in attribute_chains
    )

    assert (
        "keyboard.press"
        not in attribute_chains
    )


def test_global_store_and_producer_are_nonexecuting_objects():
    from app.agent.focused_text_receipt import (
        FOCUSED_TEXT_RECEIPT_PRODUCER,
    )

    assert (
        type(FOCUSED_TEXT_RECEIPTS)
        is FocusedTextReceiptStore
    )

    assert (
        type(FOCUSED_TEXT_RECEIPT_PRODUCER)
        is FocusedTextReceiptProducer
    )

    assert not hasattr(
        FOCUSED_TEXT_RECEIPT_PRODUCER,
        "execute",
    )

    assert not hasattr(
        FOCUSED_TEXT_RECEIPT_PRODUCER,
        "type_text",
    )


def test_direct_compose_has_no_b8_claim_or_focus_production_surface():
    signature = inspect.signature(
        compose_focused_text_receipt
    )

    assert tuple(
        signature.parameters
    ) == (
        "text_evidence",
        "target_consumption",
        "focus_provenance",
        "clock",
    )
