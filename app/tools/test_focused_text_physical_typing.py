import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.agent.focused_text_receipt as receipt_module
import app.tools.computer_tools as computer_tools
from app.agent.tool_result import ToolResult


class SingleUseReceiptStore:
    def __init__(
        self,
        receipt,
    ):
        self.receipt = receipt
        self.active = True
        self.claim_attempts = 0

    def claim(
        self,
        receipt,
    ):
        self.claim_attempts += 1

        active = self.receipt

        self.active = False
        self.receipt = None

        if (
            not active
            or receipt
            is not active
        ):
            raise ValueError(
                "receipt unavailable"
            )

        return active


def receipt_with_text(
    text,
):
    return SimpleNamespace(
        text_evidence=(
            SimpleNamespace(
                raw_text=text
            )
        )
    )


def install_store(
    monkeypatch,
    receipt,
):
    store = (
        SingleUseReceiptStore(
            receipt
        )
    )

    monkeypatch.setattr(
        receipt_module,
        "FOCUSED_TEXT_RECEIPTS",
        store,
    )

    return store


def test_signature_has_no_caller_supplied_text_parameter():
    signature = (
        inspect.signature(
            computer_tools
            .type_text_focused
        )
    )

    assert tuple(
        signature.parameters
    ) == (
        "receipt",
        "interval",
    )

    assert (
        "text"
        not in signature.parameters
    )


def test_unknown_text_keyword_is_rejected_before_execution():
    with pytest.raises(
        TypeError
    ):
        computer_tools.type_text_focused(
            object(),
            text="forged",
        )


def test_claim_failure_never_reaches_raw_typing(
    monkeypatch,
):
    real = (
        receipt_with_text(
            "authorized"
        )
    )

    wrong = (
        receipt_with_text(
            "forged"
        )
    )

    store = install_store(
        monkeypatch,
        real,
    )

    calls = []

    monkeypatch.setattr(
        computer_tools,
        "type_text",
        lambda *args, **kwargs: (
            calls.append(
                (
                    args,
                    kwargs,
                )
            )
            or ToolResult.ok(
                "unexpected"
            )
        ),
    )

    result = (
        computer_tools
        .type_text_focused(
            wrong
        )
    )

    assert not result.success
    assert calls == []
    assert store.claim_attempts == 1
    assert store.active is False


def test_exact_whitespace_payload_reaches_raw_typing_unchanged(
    monkeypatch,
):
    payload = (
        "  hello   world\n\t  "
    )

    receipt = (
        receipt_with_text(
            payload
        )
    )

    store = install_store(
        monkeypatch,
        receipt,
    )

    calls = []

    def fake_type_text(
        text,
        interval=0.01,
    ):
        calls.append(
            (
                text,
                interval,
            )
        )

        return ToolResult.ok(
            "typed"
        )

    monkeypatch.setattr(
        computer_tools,
        "type_text",
        fake_type_text,
    )

    result = (
        computer_tools
        .type_text_focused(
            receipt,
            interval=0.07,
        )
    )

    assert result.success

    assert calls == [
        (
            payload,
            0.07,
        )
    ]

    assert store.claim_attempts == 1
    assert store.active is False


def test_caller_cannot_substitute_text_after_claim(
    monkeypatch,
):
    payload = "Alice"

    receipt = (
        receipt_with_text(
            payload
        )
    )

    install_store(
        monkeypatch,
        receipt,
    )

    seen = []

    monkeypatch.setattr(
        computer_tools,
        "type_text",
        lambda text, interval=0.01: (
            seen.append(
                text
            )
            or ToolResult.ok(
                "typed"
            )
        ),
    )

    result = (
        computer_tools
        .type_text_focused(
            receipt
        )
    )

    assert result.success
    assert seen == [
        "Alice"
    ]


def test_raw_typing_failure_does_not_restore_receipt(
    monkeypatch,
):
    receipt = (
        receipt_with_text(
            "Alice"
        )
    )

    store = install_store(
        monkeypatch,
        receipt,
    )

    physical_calls = []

    def fail_type_text(
        text,
        interval=0.01,
    ):
        physical_calls.append(
            text
        )

        return ToolResult.fail(
            "host write failed"
        )

    monkeypatch.setattr(
        computer_tools,
        "type_text",
        fail_type_text,
    )

    first = (
        computer_tools
        .type_text_focused(
            receipt
        )
    )

    second = (
        computer_tools
        .type_text_focused(
            receipt
        )
    )

    assert not first.success
    assert not second.success

    assert physical_calls == [
        "Alice"
    ]

    assert store.claim_attempts == 2
    assert store.active is False


def test_invalid_claimed_payload_fails_after_receipt_is_burned(
    monkeypatch,
):
    receipt = (
        receipt_with_text(
            ""
        )
    )

    store = install_store(
        monkeypatch,
        receipt,
    )

    calls = []

    monkeypatch.setattr(
        computer_tools,
        "type_text",
        lambda *args, **kwargs: (
            calls.append(
                True
            )
            or ToolResult.ok(
                "unexpected"
            )
        ),
    )

    result = (
        computer_tools
        .type_text_focused(
            receipt
        )
    )

    assert not result.success
    assert calls == []
    assert store.active is False


def test_wrapper_delegates_bounds_and_safety_to_existing_raw_boundary(
    monkeypatch,
):
    receipt = (
        receipt_with_text(
            "bounded"
        )
    )

    install_store(
        monkeypatch,
        receipt,
    )

    calls = []

    def fake_raw(
        text,
        interval=0.01,
    ):
        calls.append(
            (
                text,
                interval,
            )
        )

        return ToolResult.fail(
            "raw boundary rejected interval"
        )

    monkeypatch.setattr(
        computer_tools,
        "type_text",
        fake_raw,
    )

    result = (
        computer_tools
        .type_text_focused(
            receipt,
            interval=999.0,
        )
    )

    assert not result.success

    assert calls == [
        (
            "bounded",
            999.0,
        )
    ]


def test_wrapper_contains_no_physical_write_implementation():
    source = (
        inspect.getsource(
            computer_tools
            .type_text_focused
        )
    )

    tree = ast.parse(
        source
    )

    write_calls = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        func = node.func

        if (
            isinstance(
                func,
                ast.Attribute,
            )
            and func.attr
            == "write"
        ):
            write_calls.append(
                node
            )

    assert write_calls == []


def test_repository_keeps_exactly_one_pyautogui_write_site():
    hits = []

    for path in Path(
        "app"
    ).rglob(
        "*.py"
    ):
        if path.name.startswith(
            "test_"
        ):
            continue

        tree = ast.parse(
            path.read_text(
                encoding="utf-8"
            )
        )

        for node in ast.walk(
            tree
        ):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            func = node.func

            if (
                isinstance(
                    func,
                    ast.Attribute,
                )
                and func.attr
                == "write"
                and isinstance(
                    func.value,
                    ast.Name,
                )
                and func.value.id
                == "pyautogui"
            ):
                hits.append(
                    (
                        str(path),
                        node.lineno,
                    )
                )

    assert len(
        hits
    ) == 1

    assert (
        hits[0][0]
        == "app/tools/computer_tools.py"
    )


def test_private_primitive_is_not_registered_as_model_tool():
    registry_path = Path(
        "app/agent/tool_registry.py"
    )

    registry_source = (
        registry_path.read_text(
            encoding="utf-8"
        )
    )

    registry_tree = ast.parse(
        registry_source
    )

    imported_names = set()
    string_literals = set()

    for node in ast.walk(
        registry_tree
    ):
        if isinstance(
            node,
            ast.ImportFrom,
        ):
            for alias in node.names:
                imported_names.add(
                    alias.name
                )

        elif isinstance(
            node,
            ast.Constant,
        ) and isinstance(
            node.value,
            str,
        ):
            string_literals.add(
                node.value
            )

    assert (
        "type_text_focused"
        not in imported_names
    )

    assert (
        "type_text_focused"
        not in string_literals
    )

    assert (
        "type_text_focused"
        not in registry_source
    )

def test_planner_facing_type_text_body_contract_remains_unbound():
    from app.agent.virtual_body import (
        body_action_contract_for,
    )

    contract = (
        body_action_contract_for(
            "type_text"
        )
    )

    assert (
        contract.target_binding
        == "unbound_frontmost_context"
    )

    assert (
        body_action_contract_for(
            "type_text_focused"
        )
        is None
    )
