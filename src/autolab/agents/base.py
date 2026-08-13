"""Agent backend ABC — interface for LLM agents driving the research loop."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A tool call requested by the agent."""
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """The result of executing a tool call."""
    tool_call_id: str
    output: str
    is_error: bool = False


@dataclass
class AgentMessage:
    """A message in the agent conversation."""
    role: str  # system | user | assistant | tool
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_result: ToolResult | None = None
    # Reasoning text emitted by thinking-mode models (DeepSeek V4's
    # `reasoning_content`). Some providers enforce a contract that assistant
    # turns carrying reasoning must echo it back on subsequent requests, so the
    # harness must round-trip this rather than drop it. Ignored by providers
    # that do not use it.
    reasoning_content: str | None = None


# Tools available to the research agent during the loop.
# Each tool is a dict matching the common function-calling schema.
RESEARCH_TOOLS = [
    {
        "name": "run_campaign",
        "description": "Run all experiments in a campaign YAML file. Returns a summary of results.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_path": {
                    "type": "string",
                    "description": "Path to the campaign YAML file",
                },
            },
            "required": ["campaign_path"],
        },
    },
    {
        "name": "query_results",
        "description": "Query experiment results from the database.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_name": {
                    "type": "string",
                    "description": "Filter by campaign name (optional)",
                },
                "metric": {
                    "type": "string",
                    "description": "Sort by this metric (optional)",
                },
                "direction": {
                    "type": "string",
                    "enum": ["maximize", "minimize"],
                    "description": "Sort direction for metric",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return",
                },
            },
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file (creates or overwrites).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell",
        "description": "Execute a shell command and return its output.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory (optional)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "get_status",
        "description": "Get current research status: experiment counts, campaign progress, state.json contents.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "complete_iteration",
        "description": "Signal that the current research iteration is complete. Call this after updating the journal and committing.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was accomplished this iteration",
                },
            },
            "required": ["summary"],
        },
    },
]


class AgentBackend(ABC):
    """Interface for LLM agents that drive the research loop.

    Subclasses implement the API-specific logic for sending messages
    and receiving responses (with tool calls) from an LLM.
    """

    @abstractmethod
    def send(
        self,
        messages: list[AgentMessage],
        tools: list[dict] | None = None,
    ) -> AgentMessage:
        """Send messages to the LLM and get a response.

        The response may contain tool_calls that the harness should execute.
        """

    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier being used."""

    def format_tools(self, tools: list[dict]) -> Any:
        """Convert generic tool schemas to backend-specific format.

        Override in subclasses if the API needs a different tool format.
        Returns the tools in whatever format send() expects.
        """
        return tools
