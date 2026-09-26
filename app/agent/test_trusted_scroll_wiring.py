import inspect

from app.agent.executor import (
    ActionExecutor,
)
from app.agent.mission_service import (
    MissionService,
)
from app.agent.pointer_desktop_provenance import (
    collect_pointer_desktop_provenance,
)
from app.agent.trusted_scroll_receipt import (
    TrustedScrollReceiptStore,
)
from app.tools.computer_tools import (
    scroll_trusted,
)
from app.agent.tool_registry import (
    KUMA_TOOLS,
)


def test_scroll_private_bridge_is_not_registered():
    assert "scroll_trusted" not in KUMA_TOOLS


def test_scroll_private_bridge_accepts_receipt_only():
    signature = inspect.signature(
        scroll_trusted
    )

    assert list(
        signature.parameters
    ) == [
        "receipt"
    ]


def test_pointer_provenance_accepts_no_planner_coordinates():
    signature = inspect.signature(
        collect_pointer_desktop_provenance
    )

    assert "x" not in signature.parameters
    assert "y" not in signature.parameters
    assert "arguments" not in signature.parameters


def test_executor_trusted_scroll_accepts_no_amount():
    signature = inspect.signature(
        ActionExecutor.execute_trusted_scroll
    )

    assert "amount" not in signature.parameters
    assert "arguments" not in signature.parameters
    assert "receipt" in signature.parameters


def test_mission_scroll_uses_full_trust_chain():
    source = inspect.getsource(
        MissionService._execute_trusted_scroll
    )

    for marker in (
        "RUNTIME_GUI_STEP_AUTHORITY",
        "derive_exact_scroll_intent_evidence(",
        "collect_pointer_desktop_provenance()",
        "TRUSTED_SCROLL_RECEIPT_PRODUCER.produce(",
        ".execute_trusted_scroll(",
    ):
        assert marker in source


def test_scroll_routes_before_generic_executor():
    source = inspect.getsource(
        MissionService._execute_single_mission_step
    )

    trusted = source.find(
        'elif tool_name == "scroll":'
    )

    generic = source.find(
        "self.kuma.executor.execute("
    )

    assert trusted >= 0
    assert generic >= 0
    assert trusted < generic


def test_scroll_receipt_consumes_before_revalidation():
    source = inspect.getsource(
        TrustedScrollReceiptStore.claim
    )

    consume = source.find(
        "self._receipt = None"
    )

    authority = source.find(
        "RUNTIME_GUI_STEP_AUTHORITY"
    )

    pointer = source.find(
        "self.revalidate_fn("
    )

    assert consume >= 0
    assert authority > consume
    assert pointer > consume
