import inspect

from app.agent.gui_dual_sensor_verification import (
    verify_runtime_focused_text_target,
)
from app.agent.mission_service import (
    MissionService,
)


def test_focused_text_verifier_accepts_no_pointer_coordinates():
    signature = inspect.signature(
        verify_runtime_focused_text_target
    )

    assert "x" not in signature.parameters
    assert "y" not in signature.parameters
    assert "consume_fn" not in signature.parameters
    assert "consume_evidence" not in signature.parameters


def test_focused_text_verifier_stops_after_b8j():
    source = inspect.getsource(
        verify_runtime_focused_text_target
    )

    assert "produce_fn(" in source
    assert "consume_fn(" not in source
    assert "evidence_consumed=False" in source
    assert ".revalidation_result" in source


def test_trusted_typing_helper_uses_complete_receipt_chain():
    source = inspect.getsource(
        MissionService._execute_trusted_focused_text
    )

    required = (
        "RUNTIME_GUI_STEP_AUTHORITY",
        "derive_exact_text_intent_evidence(",
        "bootstrap_structured_ui_screen_context()",
        "verify_runtime_focused_text_target(",
        "collect_bound_focused_ui()",
        "FOCUS_TARGET_PRODUCER.produce(",
        "FOCUSED_TEXT_RECEIPT_PRODUCER.produce(",
        ".execute_focused_text(",
    )

    for marker in required:
        assert marker in source

    assert ".executor.execute(" not in source


def test_type_text_branch_precedes_generic_executor():
    source = inspect.getsource(
        MissionService._execute_single_mission_step
    )

    trusted = source.find(
        'if tool_name == "type_text":'
    )

    generic = source.find(
        "self.kuma.executor.execute("
    )

    assert trusted >= 0
    assert generic >= 0
    assert trusted < generic


def test_inner_boundary_carries_exact_plan_and_step():
    signature = inspect.signature(
        MissionService._execute_single_mission_step
    )

    assert "runtime_plan" in signature.parameters
    assert "runtime_step" in signature.parameters


def test_focused_executor_receives_receipt_not_raw_text():
    source = inspect.getsource(
        MissionService._execute_trusted_focused_text
    )

    start = source.find(
        ".execute_focused_text("
    )

    assert start >= 0

    executor_section = source[start:]

    assert "proposed_text" not in executor_section
    assert 'arguments["text"]' not in executor_section
    assert "arguments.get(" not in executor_section


def test_focus_provenance_preserves_exact_semantic_identity():
    source = inspect.getsource(
        MissionService._execute_trusted_focused_text
    )

    assert (
        "focus_provenance.semantic_result"
        in source
    )

    assert (
        "is not dual.semantic_result"
        in source
    )


def test_receipt_preserves_exact_trust_objects():
    source = inspect.getsource(
        MissionService._execute_trusted_focused_text
    )

    assert "receipt.text_evidence" in source
    assert "is not text_evidence" in source

    assert "receipt.focus_provenance" in source
    assert "is not focus_provenance" in source

    assert "receipt.semantic_result" in source
    assert "is not dual.semantic_result" in source
