from __future__ import annotations

import time

from app.agent.kuma_agent import KumaAgent
from app.agent.task_state import TaskState


def test_weather_continuation_restores_semantic_parent_goal():
    agent = KumaAgent.__new__(KumaAgent)
    agent.tool_registry = {"web_search": lambda **kwargs: kwargs}
    agent._successful_actions = {}
    agent.task_state = TaskState(goal="Bengaluru")
    agent._pending_weather_location = True
    agent._pending_weather_location_started_at = time.monotonic()
    agent._pending_weather_original_goal = "hows the weather"
    agent._pending_grounded_web_query = ""

    response = agent.ask_model([{"role": "user", "content": "Bengaluru"}])
    call = response.message.tool_calls[0]
    assert call.function.arguments["query"] == "weather in Bengaluru"
    assert agent.task_state.goal == "hows the weather in Bengaluru"
    assert agent._pending_grounded_web_query == "weather in Bengaluru"


def test_internet_synthesis_prompt_requires_disagreement_disclosure(monkeypatch):
    import app.agent.kuma_agent as module

    captured = {}

    class Message:
        content = "answer"

    class Response:
        message = Message()

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(module, "chat", fake_chat)
    agent = KumaAgent.__new__(KumaAgent)
    agent.model = "qwen3:8b"
    assert agent._synthesize_internet_evidence("weather", "evidence") == "answer"
    prompt = captured["messages"][0]["content"]
    assert "materially disagree" in prompt
    assert captured["tools"] == []
    assert captured["options"]["num_ctx"] == 2048
    assert captured["options"]["num_predict"] == 96
