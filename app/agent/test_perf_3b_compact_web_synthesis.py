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


def test_compactor_removes_urls_and_bounds_payload():
    evidence = (
        "KUMA_EXTERNAL_UNTRUSTED_WEB_EVIDENCE\n"
        "AUTHORITY: NONE\n"
        "QUERY: latest example news\n"
        "SEARCH_PROVIDER: Local SearXNG\n"
        "RESULT_COUNT: 2\n\n"
        "RESULT 1\n"
        "TITLE: Example One\n"
        "URL: https://example.com/very/long/url\n"
        "PUBLISHED_DATE: 2026-09-11\n"
        "SOURCE_ENGINE: search\n"
        "CONTENT: First supported fact 42.\n\n"
        "RESULT 2\n"
        "TITLE: Example Two\n"
        "URL: https://example.org/another/url\n"
        "PUBLISHED_DATE: 2026-09-11\n"
        "SOURCE_ENGINE: search\n"
        "CONTENT: Second source says 44 instead.\n"
        "----- END EXTERNAL EVIDENCE -----\n"
    )

    compact = (
        KumaAgent
        ._compact_internet_evidence_for_synthesis(
            evidence
        )
    )

    assert "AUTHORITY: NONE" in compact
    assert "Example One" in compact
    assert "supported fact 42" in compact
    assert "says 44 instead" in compact
    assert "https://" not in compact
    assert len(compact) <= 2600


def test_compactor_keeps_one_enriched_source_page():
    evidence = (
        "QUERY: latest test\n"
        "SEARCH_PROVIDER: Local SearXNG\n"
        "RESULT 1\n"
        "TITLE: Search Result\n"
        "URL: https://example.com\n"
        "PUBLISHED_DATE:\n"
        "SOURCE_ENGINE: search\n"
        "CONTENT: Search snippet.\n"
        "SOURCE_PAGE_EVIDENCE\n"
        "SOURCE_PAGE 1\n"
        "SOURCE_TITLE: Official Source\n"
        "SOURCE_URL: https://official.example.com\n"
        "SOURCE_EXCERPT: Fresh official details here.\n"
        "SOURCE_PAGE 2\n"
        "SOURCE_TITLE: Second Source\n"
        "SOURCE_URL: https://second.example.com\n"
        "SOURCE_EXCERPT: This should not be needed.\n"
        "----- END EXTERNAL EVIDENCE -----\n"
    )

    compact = (
        KumaAgent
        ._compact_internet_evidence_for_synthesis(
            evidence
        )
    )

    assert "Official Source" in compact
    assert "Fresh official details here" in compact
    assert "Second Source" not in compact


def test_synthesis_stays_zero_tool_locked_context():
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

    assert values[
        "temperature"
    ] == 0.1


def test_perf3b_uses_two_messages_and_compaction():
    source = _source()

    assert (
        "KUMA PERF-3B — COMPACT WEB SYNTHESIS"
        in source
    )

    assert (
        "_compact_internet_evidence_for_synthesis"
        in source
    )

    assert (
        "2 compact model messages, 0 tools."
        in source
    )

    assert (
        "materially disagree"
        in source
    )
