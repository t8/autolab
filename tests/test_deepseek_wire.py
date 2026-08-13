"""Tests for DeepSeek V4 wire-format handling in the OpenAI-compatible backend.

DeepSeek's V4 family defaults thinking ON when `extra_body.thinking` is unset.
The API then returns `reasoning_content` and enforces that later turns echo it
back. Because AgentHarness replays the entire message history on every tool
round, an agent that drops `reasoning_content` gets HTTP 400
"reasoning_content must be passed back" immediately after its first tool call —
which for the research loop is the first thing it does.

These tests pin the wire format with a fake client. They do NOT exercise the
live DeepSeek API.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest

from autolab.agents.base import AgentMessage, ToolCall, ToolResult
from autolab.agents.openai_agent import _model_supports_thinking


@dataclass
class _FakeFunction:
    name: str
    arguments: str


@dataclass
class _FakeToolCall:
    id: str
    function: _FakeFunction
    type: str = "function"


class _FakeMessage:
    def __init__(self, content="", tool_calls=None, reasoning_content=None):
        self.content = content
        self.tool_calls = tool_calls or []
        if reasoning_content is not None:
            self.reasoning_content = reasoning_content


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


class _FakeCompletions:
    def __init__(self, reply):
        self._reply = reply
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._reply)


class _FakeClient:
    def __init__(self, reply):
        self.chat = types.SimpleNamespace(completions=_FakeCompletions(reply))


def _make_agent(model, reply, **kwargs):
    """Build an OpenAIAgent with its client swapped for a fake."""
    # The openai package may not be installed; stub the import it performs.
    if "openai" not in sys.modules:
        stub = types.ModuleType("openai")
        stub.OpenAI = lambda **_: None
        sys.modules["openai"] = stub

    from autolab.agents.openai_agent import OpenAIAgent

    agent = OpenAIAgent(model=model, api_key="test-key", **kwargs)
    client = _FakeClient(reply)
    agent._client = client
    return agent, client


@pytest.mark.parametrize("model,expected", [
    ("deepseek-v4-pro", True),
    ("deepseek-v4-flash", True),
    ("deepseek-v5-pro", True),
    ("deepseek/deepseek-v4-pro", True),   # routed (OpenRouter-style) id
    ("deepseek-v3", False),               # V3 wire format must not change
    ("deepseek-v3-chat", False),
    ("gpt-4o", False),
    ("", False),
    (None, False),
])
def test_thinking_detection(model, expected):
    assert _model_supports_thinking(model) is expected


def test_deepseek_sets_thinking_explicitly():
    """The flag must be sent, not left to the server default."""
    agent, client = _make_agent("deepseek-v4-pro", _FakeMessage(content="ok"))
    agent.send([AgentMessage(role="user", content="hi")])
    kwargs = client.chat.completions.calls[0]
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


def test_deepseek_thinking_can_be_disabled():
    agent, client = _make_agent(
        "deepseek-v4-pro", _FakeMessage(content="ok"), thinking=False
    )
    agent.send([AgentMessage(role="user", content="hi")])
    kwargs = client.chat.completions.calls[0]
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    # effort is meaningless without thinking
    assert "reasoning_effort" not in kwargs


@pytest.mark.parametrize("effort,expected", [
    ("low", "low"),
    ("medium", "medium"),
    ("high", "high"),
    ("xhigh", "max"),
    ("max", "max"),
    ("ultra", "max"),
])
def test_reasoning_effort_mapping(effort, expected):
    agent, client = _make_agent(
        "deepseek-v4-pro", _FakeMessage(content="ok"), reasoning_effort=effort
    )
    agent.send([AgentMessage(role="user", content="hi")])
    assert client.chat.completions.calls[0]["reasoning_effort"] == expected


def test_reasoning_effort_omitted_when_unset():
    """Omitted, so the provider applies its own default."""
    agent, client = _make_agent("deepseek-v4-pro", _FakeMessage(content="ok"))
    agent.send([AgentMessage(role="user", content="hi")])
    assert "reasoning_effort" not in client.chat.completions.calls[0]


def test_non_deepseek_wire_format_untouched():
    """Regression guard: OpenAI/others must not gain thinking fields."""
    agent, client = _make_agent("gpt-4o", _FakeMessage(content="ok"))
    agent.send([AgentMessage(role="user", content="hi")])
    kwargs = client.chat.completions.calls[0]
    assert "extra_body" not in kwargs
    assert "reasoning_effort" not in kwargs


def test_reasoning_content_captured_from_response():
    reply = _FakeMessage(content="answer", reasoning_content="chain of thought")
    agent, _ = _make_agent("deepseek-v4-pro", reply)
    msg = agent.send([AgentMessage(role="user", content="hi")])
    assert msg.reasoning_content == "chain of thought"


def test_reasoning_content_echoed_back_on_replay():
    """The core fix: a replayed assistant turn keeps its reasoning_content.

    Without this the second round of any tool-using iteration is rejected.
    """
    agent, client = _make_agent("deepseek-v4-pro", _FakeMessage(content="done"))

    history = [
        AgentMessage(role="user", content="run the campaign"),
        AgentMessage(
            role="assistant",
            content="",
            reasoning_content="I should call run_campaign",
            tool_calls=[ToolCall(id="call_1", name="run_campaign",
                                 arguments={"campaign_path": "c.yaml"})],
        ),
        AgentMessage(
            role="tool",
            tool_result=ToolResult(tool_call_id="call_1", output="5 completed"),
        ),
    ]
    agent.send(history)

    sent = client.chat.completions.calls[0]["messages"]
    assistant = [m for m in sent if m["role"] == "assistant"][0]
    assert assistant["reasoning_content"] == "I should call run_campaign"
    assert assistant["tool_calls"][0]["id"] == "call_1"

    tool_msg = [m for m in sent if m["role"] == "tool"][0]
    assert tool_msg["tool_call_id"] == "call_1"


def test_plain_assistant_turn_echoes_reasoning():
    """Assistant turns without tool calls must round-trip reasoning too."""
    agent, client = _make_agent("deepseek-v4-pro", _FakeMessage(content="done"))
    agent.send([
        AgentMessage(role="user", content="hi"),
        AgentMessage(role="assistant", content="hello", reasoning_content="think"),
        AgentMessage(role="user", content="again"),
    ])
    sent = client.chat.completions.calls[0]["messages"]
    assistant = [m for m in sent if m["role"] == "assistant"][0]
    assert assistant["reasoning_content"] == "think"


def test_no_reasoning_content_key_when_absent():
    """Providers that don't emit reasoning must not receive an empty field."""
    agent, client = _make_agent("gpt-4o", _FakeMessage(content="done"))
    agent.send([
        AgentMessage(role="user", content="hi"),
        AgentMessage(role="assistant", content="hello"),
    ])
    sent = client.chat.completions.calls[0]["messages"]
    assistant = [m for m in sent if m["role"] == "assistant"][0]
    assert "reasoning_content" not in assistant
