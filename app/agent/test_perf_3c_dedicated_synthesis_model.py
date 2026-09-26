from __future__ import annotations

import ast
from pathlib import Path

import app.agent.kuma_agent as kuma_agent_module
from app.agent.kuma_agent import KumaAgent


def _source():
    return Path(
        kuma_agent_module.__file__
    ).read_text()


def _method(
    source,
    name,
):
    tree = ast.parse(
        source
    )

    cls = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.ClassDef,
        )
        and node.name == "KumaAgent"
    )

    return next(
        node
        for node in cls.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == name
    )


def _chat_call(
    method,
):
    calls = [
        node
        for node in ast.walk(
            method
        )
        if isinstance(
            node,
            ast.Call,
        )
        and isinstance(
            node.func,
            ast.Name,
        )
        and node.func.id == "chat"
    ]

    assert len(
        calls
    ) == 1

    return calls[
        0
    ]


def _keyword(
    call,
    name,
):
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value

    return None


def test_perf3c_default_synthesis_model():
    assert (
        KumaAgent._perf3c_synthesis_model_name()
        == "qwen3:4b-instruct"
    )


def test_perf3c_synthesis_model_env_override(
    monkeypatch,
):
    monkeypatch.setenv(
        "KUMA_SYNTHESIS_MODEL",
        "example-local-model:latest",
    )

    assert (
        KumaAgent._perf3c_synthesis_model_name()
        == "example-local-model:latest"
    )


def test_synthesis_chat_uses_dedicated_model_helper():
    source = _source()

    method = _method(
        source,
        "_synthesize_internet_evidence",
    )

    call = _chat_call(
        method
    )

    model = _keyword(
        call,
        "model",
    )

    assert isinstance(
        model,
        ast.Call,
    )

    assert isinstance(
        model.func,
        ast.Attribute,
    )

    assert (
        model.func.attr
        == "_perf3c_synthesis_model_name"
    )


def test_synthesis_safety_and_perf_invariants_survive():
    source = _source()

    method = _method(
        source,
        "_synthesize_internet_evidence",
    )

    call = _chat_call(
        method
    )

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

    options = _keyword(
        call,
        "options",
    )

    assert isinstance(
        options,
        ast.Dict,
    )

    values = {
        key.value: ast.literal_eval(
            value
        )
        for key, value in zip(
            options.keys,
            options.values,
        )
        if isinstance(
            key,
            ast.Constant,
        )
    }

    assert values[
        "num_ctx"
    ] == 2048

    assert values[
        "num_predict"
    ] == 96

    assert (
        "KUMA PERF-3B — COMPACT WEB SYNTHESIS"
        in source
    )

    assert (
        "KUMA PERF-3A OLLAMA METRICS"
        in source
    )

    assert (
        "KUMA PERF-3C — DEDICATED LOCAL SYNTHESIS MODEL"
        in source
    )
