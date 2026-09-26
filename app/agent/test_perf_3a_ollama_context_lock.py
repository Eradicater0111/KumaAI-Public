from __future__ import annotations

import ast
from pathlib import Path

import app.agent.kuma_agent as kuma_agent_module


TARGET_CTX = 2048


def _source() -> str:
    return Path(
        kuma_agent_module.__file__
    ).read_text()


def _method(
    source: str,
    name: str,
):
    tree = ast.parse(source)

    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "KumaAgent"
    )

    return next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    )


def _keyword(
    call: ast.Call,
    name: str,
):
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value

    return None


def _chat_call(method):
    calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(
            node.func,
            ast.Name,
        )
        and node.func.id == "chat"
    ]

    assert len(calls) == 1

    return calls[0]


def _dict_values(
    dictionary: ast.Dict,
    key_name: str,
):
    return [
        value
        for key, value in zip(
            dictionary.keys,
            dictionary.values,
        )
        if isinstance(
            key,
            ast.Constant,
        )
        and key.value == key_name
    ]


def test_synthesis_remains_zero_tool_non_thinking():
    source = _source()

    method = _method(
        source,
        "_synthesize_internet_evidence",
    )

    call = _chat_call(method)

    tools = _keyword(
        call,
        "tools",
    )

    assert isinstance(
        tools,
        ast.List,
    )
    assert tools.elts == []

    think = _keyword(
        call,
        "think",
    )

    assert isinstance(
        think,
        ast.Constant,
    )
    assert think.value is False

    keep_alive = _keyword(
        call,
        "keep_alive",
    )

    assert isinstance(
        keep_alive,
        ast.Constant,
    )
    assert keep_alive.value == "30m"


def test_synthesis_uses_locked_context_and_96_output_tokens():
    source = _source()

    method = _method(
        source,
        "_synthesize_internet_evidence",
    )

    call = _chat_call(method)

    options = _keyword(
        call,
        "options",
    )

    assert isinstance(
        options,
        ast.Dict,
    )

    ctx = _dict_values(
        options,
        "num_ctx",
    )

    predict = _dict_values(
        options,
        "num_predict",
    )

    assert len(ctx) == 1
    assert len(predict) == 1

    assert (
        ast.literal_eval(
            ctx[0]
        )
        == TARGET_CTX
    )

    assert (
        ast.literal_eval(
            predict[0]
        )
        == 96
    )


def test_all_ask_model_route_contexts_are_locked():
    source = _source()

    method = _method(
        source,
        "ask_model",
    )

    values = []

    for node in ast.walk(method):
        if not isinstance(
            node,
            ast.Dict,
        ):
            continue

        values.extend(
            _dict_values(
                node,
                "num_ctx",
            )
        )

    assert len(values) >= 3

    assert {
        ast.literal_eval(value)
        for value in values
    } == {
        TARGET_CTX
    }


def test_perf3a_markers_exist():
    source = _source()

    assert (
        "KUMA PERF-3A — OLLAMA CONTEXT LOCK"
        in source
    )

    assert (
        "KUMA PERF-3A OLLAMA METRICS"
        in source
    )
