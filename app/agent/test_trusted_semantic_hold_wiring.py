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
from app.agent.trusted_semantic_hold_receipt import (
    TrustedSemanticHoldReceiptStore,
)
from app.tools.computer_tools import (
    hold_mouse_vision_trusted,
)


def test_private_semantic_hold_bridge_not_registered():
    assert (
        "hold_mouse_vision_trusted"
        not in KUMA_TOOLS
    )


def test_private_semantic_hold_bridge_accepts_receipt_only():
    assert list(
        inspect.signature(
            hold_mouse_vision_trusted
        ).parameters
    ) == [
        "receipt"
    ]


def test_executor_accepts_no_raw_target_or_button():
    signature = inspect.signature(
        ActionExecutor.execute_trusted_hold_mouse_vision
    )

    for forbidden in (
        "x",
        "y",
        "observation_id",
        "button",
        "arguments",
    ):
        assert (
            forbidden
            not in signature.parameters
        )


def test_semantic_hold_claim_consumes_before_revalidation():
    source = inspect.getsource(
        TrustedSemanticHoldReceiptStore.claim
    )

    consume = source.find(
        "self._receipt = None"
    )

    authority = source.find(
        "RUNTIME_GUI_STEP_AUTHORITY"
    )

    body = source.find(
        "self.body_snapshot_get()"
    )

    assert consume >= 0
    assert authority > consume
    assert body > consume


def test_mission_semantic_hold_uses_existing_target_verification():
    source = inspect.getsource(
        MissionService._execute_trusted_hold_mouse_vision
    )

    for marker in (
        "target_verification",
        "derive_exact_mouse_hold_vision_intent_evidence(",
        "TRUSTED_SEMANTIC_HOLD_RECEIPT_PRODUCER.produce(",
        ".execute_trusted_hold_mouse_vision(",
    ):
        assert marker in source


def test_mission_semantic_hold_routes_before_generic_executor():
    source = inspect.getsource(
        MissionService._execute_single_mission_step
    )

    trusted = source.find(
        'elif tool_name == "hold_mouse_vision":'
    )

    generic = source.find(
        "self.kuma.executor.execute("
    )

    assert trusted >= 0
    assert generic >= 0
    assert trusted < generic


def test_private_bridge_recovers_target_only_from_receipt():
    source = inspect.getsource(
        hold_mouse_vision_trusted
    )

    assert (
        "claimed.vision_x"
        in source
    )

    assert (
        "claimed.vision_y"
        in source
    )

    assert (
        "claimed.observation_id"
        in source
    )

    assert (
        "claimed.button"
        in source
    )
