from __future__ import annotations

from pathlib import Path

import app.agent.model_warmup as model_warmup
import app.ui.window as window_module


class _Agent:
    model = "qwen3:8b"

    @staticmethod
    def _perf3c_synthesis_model_name():
        return "qwen3:4b-instruct"


def test_resolve_models_prefers_synthesis_then_main():
    assert model_warmup._resolve_models(
        _Agent()
    ) == [
        (
            "synthesis",
            "qwen3:4b-instruct",
        ),
        (
            "main",
            "qwen3:8b",
        ),
    ]


def test_warm_one_is_local_zero_tool_and_one_token(
    monkeypatch,
):
    captured = {}

    class _Response:
        load_duration = 1_000_000

    def fake_chat(
        **kwargs,
    ):
        captured.update(
            kwargs
        )
        return _Response()

    monkeypatch.setattr(
        model_warmup,
        "chat",
        fake_chat,
    )

    model_warmup._warm_one(
        "synthesis",
        "qwen3:4b-instruct",
    )

    assert captured[
        "model"
    ] == "qwen3:4b-instruct"

    assert captured[
        "tools"
    ] == []

    assert captured[
        "think"
    ] is False

    assert captured[
        "keep_alive"
    ] == "30m"

    assert captured[
        "options"
    ][
        "num_ctx"
    ] == 2048

    assert captured[
        "options"
    ][
        "num_predict"
    ] == 1

    assert captured[
        "messages"
    ] == [
        {
            "role": "user",
            "content": "Reply OK.",
        }
    ]


def test_window_starts_background_prewarm():
    source = Path(
        window_module.__file__
    ).read_text()

    assert (
        "KUMA PERF-3D — BACKGROUND DUAL-BRAIN PREWARM"
        in source
    )

    assert (
        "start_model_prewarm"
        in source
    )


def test_model_warmup_contains_no_agent_tool_execution():
    source = Path(
        model_warmup.__file__
    ).read_text()

    blocked = (
        ".executor.execute(",
        ".run(",
        "get_current_location(",
        "web_search(",
        "execute_command(",
        "type_text(",
        "click_at(",
    )

    for token in blocked:
        assert token not in source
