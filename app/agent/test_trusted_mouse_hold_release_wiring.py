import inspect

from app.agent.executor import (
    ActionExecutor,
)
from app.agent.mission_service import (
    MissionService,
)
from app.agent.tool_registry import (
    KUMA_TOOLS,
)
from app.agent.trusted_mouse_button_receipt import (
    TrustedMouseHoldReceiptStore,
    TrustedMouseReleaseReceiptStore,
)
from app.tools.computer_tools import (
    hold_mouse_trusted,
    release_mouse_trusted,
)


def test_private_mouse_bridges_are_not_registered():
    assert "hold_mouse_trusted" not in KUMA_TOOLS
    assert "release_mouse_trusted" not in KUMA_TOOLS


def test_private_hold_accepts_receipt_only():
    assert list(
        inspect.signature(
            hold_mouse_trusted
        ).parameters
    ) == ["receipt"]


def test_private_release_accepts_receipt_only():
    assert list(
        inspect.signature(
            release_mouse_trusted
        ).parameters
    ) == ["receipt"]


def test_release_bridge_accepts_no_button():
    source = inspect.getsource(
        release_mouse_trusted
    )

    assert "return release_mouse()" in source


def test_hold_executor_accepts_no_button():
    signature = inspect.signature(
        ActionExecutor.execute_trusted_hold_mouse
    )

    assert "button" not in signature.parameters
    assert "arguments" not in signature.parameters


def test_release_executor_accepts_no_button():
    signature = inspect.signature(
        ActionExecutor.execute_trusted_release_mouse
    )

    assert "button" not in signature.parameters
    assert "arguments" not in signature.parameters


def test_hold_receipt_consumes_before_context_revalidation():
    source = inspect.getsource(
        TrustedMouseHoldReceiptStore.claim
    )

    consume = source.find(
        "self._receipt = None"
    )

    pointer = source.find(
        "self.pointer_revalidate("
    )

    body = source.find(
        "self.body_snapshot_get()"
    )

    assert consume >= 0
    assert pointer > consume
    assert body > consume


def test_release_receipt_consumes_before_body_revalidation():
    source = inspect.getsource(
        TrustedMouseReleaseReceiptStore.claim
    )

    consume = source.find(
        "self._receipt = None"
    )

    body = source.find(
        "self.body_snapshot_get()"
    )

    assert consume >= 0
    assert body > consume


def test_hold_mission_uses_pointer_and_receipt_chain():
    source = inspect.getsource(
        MissionService._execute_trusted_hold_mouse
    )

    for marker in (
        "derive_exact_mouse_hold_intent_evidence(",
        "collect_pointer_desktop_provenance()",
        "TRUSTED_MOUSE_HOLD_RECEIPT_PRODUCER.produce(",
        ".execute_trusted_hold_mouse(",
    ):
        assert marker in source


def test_release_mission_never_accepts_planner_button():
    source = inspect.getsource(
        MissionService._execute_trusted_release_mouse
    )

    assert (
        "arguments"
        in source
    )

    assert (
        "arguments.get"
        not in source
    )

    assert (
        ".execute_trusted_release_mouse("
        in source
    )


def test_hold_and_release_route_before_generic_executor():
    source = inspect.getsource(
        MissionService._execute_single_mission_step
    )

    generic = source.find(
        "self.kuma.executor.execute("
    )

    assert (
        source.find(
            'elif tool_name == "hold_mouse":'
        )
        < generic
    )

    assert (
        source.find(
            'elif tool_name == "release_mouse":'
        )
        < generic
    )
