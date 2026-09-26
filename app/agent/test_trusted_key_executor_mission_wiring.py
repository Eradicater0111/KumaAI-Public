import inspect

from app.agent.executor import (
    ActionExecutor,
)
from app.agent.mission_service import (
    MissionService,
)
from app.agent.trusted_key_receipt import (
    TrustedKeyReceiptStore,
)


def test_executor_trusted_key_lane_accepts_receipt_not_key():
    signature = inspect.signature(
        ActionExecutor.execute_trusted_key
    )

    assert list(
        signature.parameters
    ) == [
        "self",
        "receipt",
        "approved",
    ]

    assert (
        "key"
        not in signature.parameters
    )

    assert (
        "arguments"
        not in signature.parameters
    )


def test_executor_uses_private_trusted_bridge():
    source = inspect.getsource(
        ActionExecutor.execute_trusted_key
    )

    assert 'tool_name = "press_key"' in source
    assert "TrustedKeyReceipt" in source
    assert "press_key_trusted" in source
    assert "effect_started" in source

    assert (
        "self.tool_registry.get"
        in source
    )


def test_mission_trusted_key_chain_is_complete():
    source = inspect.getsource(
        MissionService._execute_trusted_key
    )

    required = (
        "RUNTIME_GUI_STEP_AUTHORITY",
        "derive_exact_key_intent_evidence(",
        "collect_bound_focused_ui()",
        "FOCUS_DESKTOP_PROVENANCE.get(",
        "TRUSTED_KEY_RECEIPT_PRODUCER.produce(",
        ".execute_trusted_key(",
    )

    for marker in required:
        assert marker in source


def test_mission_trusted_key_helper_never_uses_generic_executor():
    source = inspect.getsource(
        MissionService._execute_trusted_key
    )

    assert (
        ".executor.execute("
        not in source
    )


def test_raw_key_stops_before_private_executor():
    source = inspect.getsource(
        MissionService._execute_trusted_key
    )

    start = source.find(
        ".execute_trusted_key("
    )

    assert start >= 0

    executor_section = source[start:]

    assert (
        "proposed_key"
        not in executor_section
    )

    assert (
        "arguments.get"
        not in executor_section
    )


def test_press_key_routes_before_generic_executor():
    source = inspect.getsource(
        MissionService._execute_single_mission_step
    )

    trusted = source.find(
        'elif tool_name == "press_key":'
    )

    generic = source.find(
        "self.kuma.executor.execute("
    )

    assert trusted >= 0
    assert generic >= 0
    assert trusted < generic


def test_type_text_execution_is_assigned_to_common_action_result():
    source = inspect.getsource(
        MissionService._execute_single_mission_step
    )

    assert (
        "action_result = execution"
        in source
    )


def test_receipt_claim_consumes_before_revalidation():
    source = inspect.getsource(
        TrustedKeyReceiptStore.claim
    )

    consume = source.find(
        "self._receipt = None"
    )

    authority = source.find(
        "RUNTIME_GUI_STEP_AUTHORITY"
    )

    focus = source.find(
        "self.focus_get("
    )

    assert consume >= 0
    assert authority > consume
    assert focus > consume


def test_receipt_claim_rechecks_exact_authority_and_focus_identity():
    source = inspect.getsource(
        TrustedKeyReceiptStore.claim
    )

    assert (
        "active_authority is not authority"
        in source
    )

    assert (
        "active_focus is not focus_provenance"
        in source
    )
