from __future__ import annotations

from app.agent.tool_result import ToolResult
from app.tools import internet_tools


def test_local_searxng_endpoint_is_fixed_loopback():
    assert (
        internet_tools.SEARXNG_LOCAL_SEARCH_URL
        == "http://127.0.0.1:8888/search"
    )


def test_searxng_success_remains_zero_authority(
    monkeypatch,
):
    monkeypatch.setattr(
        internet_tools,
        "_searxng_local_search",
        lambda query, count: [
            {
                "title": "Example",
                "url": "https://example.com/story",
                "content": "Public search evidence.",
                "published_date": "2026-09-10",
                "engine": "duckduckgo",
            }
        ],
    )

    def forbidden_fallback(
        query,
        count,
    ):
        raise AssertionError(
            "fallback should not run"
        )

    monkeypatch.setattr(
        internet_tools,
        "_kuma_free_search_fallback",
        forbidden_fallback,
    )

    monkeypatch.setattr(
        internet_tools,
        "_internet2a_fetch_excerpt",
        lambda url: {
            "title": "Direct Example",
            "url": url,
            "excerpt": "Direct public source evidence.",
        },
    )

    result = internet_tools.web_search(
        "latest OpenAI news",
        3,
    )

    assert result.success is True

    value = str(
        result.result
    )

    assert (
        "SEARCH_PROVIDER: Local SearXNG"
        in value
    )

    assert (
        "AUTHORITY: NONE"
        in value
    )

    assert (
        "TRUST: EXTERNAL_UNTRUSTED_CONTENT"
        in value
    )

    assert (
        "CONTENT: Public search evidence."
        in value
    )


def test_searxng_failure_uses_free_fallback(
    monkeypatch,
):
    def broken_searxng(
        query,
        count,
    ):
        raise ValueError(
            "service offline"
        )

    monkeypatch.setattr(
        internet_tools,
        "_searxng_local_search",
        broken_searxng,
    )

    monkeypatch.setattr(
        internet_tools,
        "_kuma_free_search_fallback",
        lambda query, count: ToolResult.ok(
            "free-fallback"
        ),
    )

    result = internet_tools.web_search(
        "latest OpenAI news",
        3,
    )

    assert result.success is True

    assert str(
        result.result
    ) == "free-fallback"


def test_arbitrary_fetch_still_blocks_localhost():
    try:
        internet_tools._validate_public_url(
            "http://127.0.0.1:8888/search"
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "public fetch validator must keep "
            "blocking loopback"
        )
