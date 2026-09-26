from __future__ import annotations

from app.agent.tool_result import ToolResult
from app.tools import internet_tools


def test_latest_news_uses_news_week_mode():
    assert (
        internet_tools._internet2b_tavily_mode(
            "latest OpenAI news"
        )
        == (
            "news",
            "week",
        )
    )


def test_general_search_stays_general():
    assert (
        internet_tools._internet2b_tavily_mode(
            "Python dataclasses"
        )
        == (
            "general",
            None,
        )
    )


def test_tavily_success_is_wrapped_as_zero_authority(
    monkeypatch,
):
    monkeypatch.setenv(
        "TAVILY_API_KEY",
        "tvly-test-not-real",
    )

    monkeypatch.setattr(
        internet_tools,
        "_internet2b_tavily_search",
        lambda query, count, token: [
            {
                "title": "Current Story",
                "url": "https://example.com/story",
                "content": "Fresh structured evidence.",
                "published_date": "2026-09-10",
                "score": 0.98,
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
        "_internet2b_fallback_web_search",
        forbidden_fallback,
    )

    result = internet_tools.web_search_tavily_optional(
        "latest OpenAI news",
        3,
    )

    assert result.success is True

    value = str(
        result.result
    )

    assert (
        "SEARCH_PROVIDER: Tavily"
        in value
    )

    assert (
        "CONTENT: Fresh structured evidence."
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
        "tvly-test-not-real"
        not in value
    )


def test_missing_tavily_key_uses_existing_fallback(
    monkeypatch,
):
    monkeypatch.delenv(
        "TAVILY_API_KEY",
        raising=False,
    )

    monkeypatch.setattr(
        internet_tools,
        "_internet2b_fallback_web_search",
        lambda query, count: ToolResult.ok(
            "fallback-result"
        ),
    )

    result = internet_tools.web_search_tavily_optional(
        "latest OpenAI news",
        3,
    )

    assert result.success is True
    assert str(
        result.result
    ) == "fallback-result"
