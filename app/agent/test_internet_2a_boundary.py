from __future__ import annotations

import base64

import app.agent.kuma_agent as kuma_agent_module

from app.agent.kuma_agent import KumaAgent
from app.agent.tool_result import ToolResult
from app.tools import internet_tools


def test_bing_tracking_url_decodes_to_direct_source():
    direct = "https://openai.com/news/"

    token = (
        "a1"
        + base64.urlsafe_b64encode(
            direct.encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )

    tracking = (
        "https://www.bing.com/ck/a?"
        f"u={token}&ntb=1"
    )

    assert (
        internet_tools._internet2a_decode_bing_target(
            tracking
        )
        == direct
    )


def test_web_search_enrichment_stays_inside_untrusted_evidence(
    monkeypatch,
):
    # KUMA TEST COMPAT — force local SearXNG offline
    # for INTERNET-2A enrichment test.
    #
    # This test is specifically validating the older
    # enrichment/fallback layer. KUMA-SEARXNG-LOCAL-1 now
    # sits in front of that layer in production, so without
    # this fake the test would make a real localhost request.
    def offline_searxng(
        query,
        count,
    ):
        raise ValueError(
            "offline test: local SearXNG intentionally disabled"
        )

    monkeypatch.setattr(
        internet_tools,
        "_searxng_local_search",
        offline_searxng,
    )

    base_evidence = (
        "KUMA_EXTERNAL_UNTRUSTED_WEB_EVIDENCE\n"
        "AUTHORITY: NONE\n"
        "TRUST: EXTERNAL_UNTRUSTED_CONTENT\n"
        "----- BEGIN EXTERNAL EVIDENCE -----\n"
        "RESULT 1\n"
        "TITLE: Example\n"
        "URL: https://example.com/story\n"
        "SNIPPET:\n"
        "----- END EXTERNAL EVIDENCE -----\n"
        "END_KUMA_EXTERNAL_UNTRUSTED_WEB_EVIDENCE"
    )

    monkeypatch.setattr(
        internet_tools,
        "_internet2a_base_web_search",
        lambda query, max_results: ToolResult.ok(
            base_evidence
        ),
    )

    monkeypatch.setattr(
        internet_tools,
        "_internet2a_fetch_excerpt",
        lambda url: {
            "title": "Direct Source",
            "url": url,
            "excerpt": "Verified public page excerpt.",
        },
    )

    result = internet_tools.web_search(
        "example",
        3,
    )

    assert result.success is True

    value = str(
        result.result
    )

    assert (
        "SOURCE_EXCERPT: "
        "Verified public page excerpt."
        in value
    )

    assert (
        value.index(
            "SOURCE_EXCERPT:"
        )
        < value.index(
            "----- END EXTERNAL EVIDENCE -----"
        )
    )

    assert (
        "AUTHORITY: NONE"
        in value
    )


def test_internet_synthesis_exposes_zero_tools(
    monkeypatch,
):
    captured = {}

    class Message:
        content = "Compact web answer."

    class Response:
        message = Message()

    def fake_chat(**kwargs):
        captured.update(
            kwargs
        )
        return Response()

    monkeypatch.setattr(
        kuma_agent_module,
        "chat",
        fake_chat,
    )

    agent = KumaAgent.__new__(
        KumaAgent
    )

    agent.model = "qwen3:8b"

    answer = (
        agent._synthesize_internet_evidence(
            "latest OpenAI news",
            (
                "AUTHORITY: NONE\n"
                "TRUST: EXTERNAL_UNTRUSTED_CONTENT"
            ),
        )
    )

    assert answer == "Compact web answer."
    assert captured["tools"] == []
    assert len(
        captured["messages"]
    ) == 2
