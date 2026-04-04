"""Tests for agent backends — ABC, tool formatting, message handling."""

from __future__ import annotations

from typing import Optional, List

from autolab.agents.base import (
    AgentBackend, AgentMessage, ToolCall, ToolResult, RESEARCH_TOOLS,
)


class MockAgent(AgentBackend):
    """Test agent that returns canned responses."""

    def __init__(self, responses: Optional[List[AgentMessage]] = None):
        self._responses = list(responses or [])
        self._call_count = 0
        self.sent_messages: List[List[AgentMessage]] = []

    def send(self, messages, tools=None):
        self.sent_messages.append(messages)
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return AgentMessage(role="assistant", content="Done.")

    def model_name(self):
        return "mock-agent"


def test_research_tools_exist():
    """RESEARCH_TOOLS has the expected tool names."""
    names = {t["name"] for t in RESEARCH_TOOLS}
    assert "run_campaign" in names
    assert "query_results" in names
    assert "read_file" in names
    assert "write_file" in names
    assert "run_shell" in names
    assert "get_status" in names
    assert "complete_iteration" in names


def test_research_tools_have_schemas():
    """Each tool has name, description, and parameters."""
    for tool in RESEARCH_TOOLS:
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool
        assert tool["parameters"]["type"] == "object"


def test_mock_agent_send():
    agent = MockAgent([
        AgentMessage(role="assistant", content="Hello"),
    ])
    resp = agent.send([AgentMessage(role="user", content="Hi")])
    assert resp.content == "Hello"
    assert agent.model_name() == "mock-agent"


def test_mock_agent_with_tool_calls():
    agent = MockAgent([
        AgentMessage(
            role="assistant",
            content="Let me check status",
            tool_calls=[ToolCall(id="tc1", name="get_status", arguments={})],
        ),
        AgentMessage(role="assistant", content="Done!"),
    ])
    resp1 = agent.send([AgentMessage(role="user", content="Check status")])
    assert len(resp1.tool_calls) == 1
    assert resp1.tool_calls[0].name == "get_status"

    resp2 = agent.send([
        AgentMessage(role="user", content="Check status"),
        resp1,
        AgentMessage(role="tool", tool_result=ToolResult(tool_call_id="tc1", output="OK")),
    ])
    assert resp2.content == "Done!"


def test_default_format_tools():
    agent = MockAgent()
    tools = agent.format_tools(RESEARCH_TOOLS)
    # Default implementation returns tools unchanged
    assert tools == RESEARCH_TOOLS
