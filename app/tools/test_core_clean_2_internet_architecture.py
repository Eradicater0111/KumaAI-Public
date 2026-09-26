from __future__ import annotations

import ast
from pathlib import Path

from app.agent.tool_result import ToolResult
from app.tools import internet_tools


def test_internet_tools_has_one_public_web_search_definition():
    source = Path(internet_tools.__file__).read_text()
    tree = ast.parse(source)
    defs = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "web_search"
    ]
    assert len(defs) == 1


def test_searxng_success_flows_through_provider_independent_enrichment(monkeypatch):
    monkeypatch.setattr(
        internet_tools,
        "_searxng_local_search",
        lambda query, count: [
            {
                "title": "Example",
                "url": "https://example.com/story",
                "content": "Search snippet.",
                "published_date": "2026-09-10",
                "engine": "test",
            }
        ],
    )
    monkeypatch.setattr(
        internet_tools,
        "_internet2a_fetch_excerpt",
        lambda url: {
            "title": "Direct Example",
            "url": url,
            "excerpt": "Direct source evidence.",
        },
    )

    result = internet_tools.web_search("example", 3)
    assert result.success is True
    value = str(result.result)
    assert "SEARCH_PROVIDER: Local SearXNG" in value
    assert "SOURCE_PAGE_EVIDENCE" in value
    assert "SOURCE_EXCERPT: Direct source evidence." in value
    assert "AUTHORITY: NONE" in value


def test_canonical_web_search_never_calls_optional_tavily(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-not-real")
    monkeypatch.setattr(
        internet_tools,
        "_searxng_local_search",
        lambda query, count: [
            {
                "title": "Local",
                "url": "https://example.com/local",
                "content": "Local evidence.",
                "published_date": "",
                "engine": "local-test",
            }
        ],
    )
    monkeypatch.setattr(
        internet_tools,
        "_internet2a_fetch_excerpt",
        lambda url: {
            "title": "Local",
            "url": url,
            "excerpt": "Local source.",
        },
    )
    monkeypatch.setattr(
        internet_tools,
        "_internet2b_tavily_search",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("canonical core search must not call Tavily")
        ),
    )

    result = internet_tools.web_search("latest news", 3)
    assert result.success is True
    assert "SEARCH_PROVIDER: Local SearXNG" in str(result.result)
