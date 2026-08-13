"""Anthropic API agent backend — Claude via the Anthropic SDK."""

from __future__ import annotations

import json
import os
from typing import Any

from .base import AgentBackend, AgentMessage, ToolCall


class AnthropicAgent(AgentBackend):
    """Drives the research loop via the Anthropic Messages API.

    Requires: pip install anthropic
    Set ANTHROPIC_API_KEY or pass api_key.
    """

    def __init__(
        self,
        model: str = "claude-opus-5",
        api_key: str | None = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        # Current Claude models think by default, and max_tokens caps thinking
        # plus response text together — 4096 truncates research turns mid-answer.
        max_tokens: int = 16000,
    ):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install autolab[anthropic]"
            )

        key = api_key or os.environ.get(api_key_env, "")
        if not key:
            raise ValueError(
                f"No API key found. Set {api_key_env} or pass api_key."
            )

        self._client = anthropic.Anthropic(api_key=key)
        self._model = model
        self._max_tokens = max_tokens

    def model_name(self) -> str:
        return self._model

    def format_tools(self, tools: list[dict]) -> list[dict]:
        """Convert generic tool schemas to Anthropic's tool format."""
        formatted = []
        for t in tools:
            formatted.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
            })
        return formatted

    def send(
        self,
        messages: list[AgentMessage],
        tools: list[dict] | None = None,
    ) -> AgentMessage:
        """Send messages to Claude and return the response."""
        # Separate system message from conversation
        system_text = ""
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_text = msg.content
            elif msg.role == "assistant":
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                api_messages.append({"role": "assistant", "content": content or msg.content})
            elif msg.role == "tool" and msg.tool_result:
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_result.tool_call_id,
                        "content": msg.tool_result.output,
                        "is_error": msg.tool_result.is_error,
                    }],
                })
            else:
                api_messages.append({"role": msg.role, "content": msg.content})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": api_messages,
        }
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = self.format_tools(tools)

        response = self._client.messages.create(**kwargs)

        # Parse response into AgentMessage
        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))

        return AgentMessage(
            role="assistant",
            content="\n".join(text_parts),
            tool_calls=tool_calls,
        )
