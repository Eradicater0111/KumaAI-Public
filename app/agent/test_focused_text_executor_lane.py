import inspect

import app.tools.computer_tools as computer_tools

from app.agent.executor import ActionExecutor
from app.agent.focused_text_receipt import FocusedTextReceipt
from app.agent.tool_result import ToolResult


def skeletal_receipt():
    return object.__new__(
        FocusedTextReceipt
    )


def executor_with_type_text(
    raw_tool=None,
):
    if raw_tool is None:
        raw_tool = lambda **_kwargs: ToolResult.ok(
            "raw"
        )

    return ActionExecutor(
        {
            "type_text": raw_tool,
        }
    )


def test_signature_accepts_no_text_or_arguments():
    signature = inspect.signature(
        ActionExecutor.execute_focused_text
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
        "receipt",
        "approved",
    )

    assert "text" not in signature.parameters
    assert "arguments" not in signature.parameters


def test_rejects_non_receipt_before_physical_bridge(
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        computer_tools,
        "type_text_focused",
        lambda receipt: (
            calls.append(receipt)
            or ToolResult.ok("unexpected")
        ),
    )

    result = (
        executor_with_type_text()
        .execute_focused_text(
            object()
        )
    )

    assert not result.success
    assert result.tool == "type_text"
    assert calls == []


def test_requires_logical_type_text_registration(
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        computer_tools,
        "type_text_focused",
        lambda receipt: (
            calls.append(receipt)
            or ToolResult.ok("unexpected")
        ),
    )

    result = (
        ActionExecutor({})
        .execute_focused_text(
            skeletal_receipt()
        )
    )

    assert not result.success
    assert "Unknown tool" in result.error
    assert calls == []


def test_never_calls_registered_raw_type_text(
    monkeypatch,
):
    receipt = skeletal_receipt()

    raw_calls = []
    focused_calls = []

    def raw_type_text(**kwargs):
        raw_calls.append(kwargs)
        return ToolResult.ok("raw")

    def focused(received):
        focused_calls.append(received)

        return ToolResult.ok(
            "typed",
            effect_started=True,
        )

    monkeypatch.setattr(
        computer_tools,
        "type_text_focused",
        focused,
    )

    result = (
        executor_with_type_text(
            raw_type_text
        )
        .execute_focused_text(
            receipt
        )
    )

    assert result.success
    assert result.tool == "type_text"
    assert result.result == "typed"
    assert result.effect_started is True

    assert focused_calls == [
        receipt
    ]

    assert raw_calls == []


def test_preserves_failure_effect_started(
    monkeypatch,
):
    monkeypatch.setattr(
        computer_tools,
        "type_text_focused",
        lambda _receipt: ToolResult.fail(
            "host write failed",
            effect_started=True,
        ),
    )

    result = (
        executor_with_type_text()
        .execute_focused_text(
            skeletal_receipt()
        )
    )

    assert not result.success
    assert result.error == "host write failed"
    assert result.effect_started is True


def test_preserves_pre_effect_failure(
    monkeypatch,
):
    monkeypatch.setattr(
        computer_tools,
        "type_text_focused",
        lambda _receipt: ToolResult.fail(
            "receipt rejected",
            effect_started=False,
        ),
    )

    result = (
        executor_with_type_text()
        .execute_focused_text(
            skeletal_receipt()
        )
    )

    assert not result.success
    assert result.effect_started is False


def test_serialization_preserves_effect_started(
    monkeypatch,
):
    monkeypatch.setattr(
        computer_tools,
        "type_text_focused",
        lambda _receipt: ToolResult.ok(
            "typed",
            effect_started=True,
        ),
    )

    result = (
        executor_with_type_text()
        .execute_focused_text(
            skeletal_receipt()
        )
    )

    assert (
        result.to_dict()[
            "effect_started"
        ]
        is True
    )


def test_generic_executor_remains_separate():
    calls = []

    def raw_type_text(text):
        calls.append(text)

        return ToolResult.ok(
            "raw typed"
        )

    result = (
        executor_with_type_text(
            raw_type_text
        )
        .execute(
            tool_name="type_text",
            arguments={
                "text": "ordinary caller",
            },
        )
    )

    assert result.success

    assert calls == [
        "ordinary caller"
    ]
