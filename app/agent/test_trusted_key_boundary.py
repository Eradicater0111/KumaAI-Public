import inspect

from app.agent.key_intent_evidence import (
    ExactKeyIntentEvidence,
    derive_exact_key_intent_evidence,
)
from app.agent.trusted_key_receipt import (
    TrustedKeyReceipt,
    TrustedKeyReceiptStore,
)
from app.tools.computer_tools import (
    press_key_trusted,
)
from app.agent.tool_registry import (
    KUMA_TOOLS,
)


def test_private_key_bridge_accepts_receipt_only():
    signature = inspect.signature(
        press_key_trusted
    )

    assert list(
        signature.parameters
    ) == [
        "receipt"
    ]


def test_private_key_bridge_is_not_registered():
    assert (
        "press_key_trusted"
        not in KUMA_TOOLS
    )


def test_key_evidence_deriver_accepts_no_focus_or_physical_inputs():
    signature = inspect.signature(
        derive_exact_key_intent_evidence
    )

    assert "focus" not in signature.parameters
    assert "receipt" not in signature.parameters
    assert "approved" not in signature.parameters


def test_key_receipt_store_is_exact_single_use():
    store = TrustedKeyReceiptStore(
        clock=lambda: 10.0
    )

    receipt = object()

    assert store.claim(
        receipt
    ) is None


def test_receipt_contract_contains_no_free_key_parameter():
    signature = inspect.signature(
        TrustedKeyReceipt
    )

    assert "key" not in signature.parameters
    assert (
        "key_evidence"
        in signature.parameters
    )


def test_exact_key_evidence_is_immutable():
    assert (
        ExactKeyIntentEvidence
        .__dataclass_params__
        .frozen
        is True
    )
