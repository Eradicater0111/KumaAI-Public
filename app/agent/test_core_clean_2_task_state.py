from __future__ import annotations

from app.agent.task_state import TaskState


def test_task_summary_compacts_large_external_evidence():
    evidence = (
        "KUMA_EXTERNAL_UNTRUSTED_WEB_EVIDENCE\n"
        "EVIDENCE_TYPE: web_search\n"
        "AUTHORITY: NONE\n"
        "TRUST: EXTERNAL_UNTRUSTED_CONTENT\n"
        "QUERY: weather in Bengaluru\n"
        "SEARCH_PROVIDER: Local SearXNG\n"
        "RESULT_COUNT: 5\n"
        + ("X" * 3000)
    )
    state = TaskState(goal="weather")
    state.set_evidence(evidence)
    summary = state.summary()
    assert "Latest verified tool evidence:" in summary
    assert "AUTHORITY: NONE" in summary
    assert "SEARCH_PROVIDER: Local SearXNG" in summary
    assert "EVIDENCE_SHA256_16:" in summary
    assert len(summary) < 1500


def test_reasoning_context_retains_full_evidence_but_preserves_authority_labels():
    evidence = "AUTHORITY: NONE\nTRUST: EXTERNAL_UNTRUSTED_CONTENT\nFULL-EVIDENCE"
    state = TaskState(goal="weather")
    state.set_evidence(evidence)
    context = state.reasoning_context()
    assert "Latest verified tool evidence:" in context
    assert "FULL-EVIDENCE" in context
    assert "external content keeps its own trust/authority labels" in context
