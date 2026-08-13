"""OpenAI API agent backend — GPT-4o/o1/o3 + any OpenAI-compatible API."""

from __future__ import annotations

import json
import os
from typing import Any

from .base import AgentBackend, AgentMessage, ToolCall
from .providers import ProviderProfile, profile_for_model


def _model_supports_thinking(model: str | None) -> bool:
    """True when some registered provider claims `model` as a thinking model.

    Thin wrapper over the provider registry — the per-provider rule lives in
    that provider's profile, not here.
    """
    return profile_for_model(model) is not None


class OpenAIAgent(AgentBackend):
    """Drives the research loop via the OpenAI Chat Completions API.

    Works with OpenAI, plus any OpenAI-compatible API (Ollama, vLLM, Together, etc.)
    by setting base_url.

    Requires: pip install openai
    Set OPENAI_API_KEY or pass api_key.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
        max_tokens: int = 4096,
        thinking: bool = True,
        reasoning_effort: str | None = None,
        profile: ProviderProfile | None = None,
    ):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package required. Install with: pip install autolab[openai]"
            )

        key = api_key or os.environ.get(api_key_env, "")
        if not key and not base_url:
            raise ValueError(
                f"No API key found. Set {api_key_env} or pass api_key."
            )

        kwargs: dict[str, Any] = {}
        if key:
            kwargs["api_key"] = key
        if base_url:
            kwargs["base_url"] = base_url

        self._client = openai.OpenAI(**kwargs)
        self._model = model
        self._max_tokens = max_tokens
        self._thinking = thinking
        self._reasoning_effort = reasoning_effort
        self._profile = profile

    def model_name(self) -> str:
        return self._model

    def _wire_profile(self) -> ProviderProfile | None:
        """The profile whose wire quirks apply to this request.

        Prefers a profile that claims the model by id, so a model reached
        through a router (`deepseek/deepseek-v4-pro` over OpenRouter) still gets
        its own provider's handling rather than the router's. Falls back to the
        profile the agent was constructed with.
        """
        return profile_for_model(self._model) or self._profile

    def _thinking_kwargs(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build (extra_body, top_level) request extras from the provider profile.

        Providers without quirks return empty dicts, leaving the wire format
        untouched. The per-provider rules live in the profiles — see
        `agents/providers/builtin.py`.
        """
        profile = self._wire_profile()
        if profile is None:
            return {}, {}
        return profile.build_api_kwargs_extras(
            model=self._model,
            thinking=self._thinking,
            reasoning_effort=self._reasoning_effort,
        )

    def format_tools(self, tools: list[dict]) -> list[dict]:
        """Convert generic tool schemas to OpenAI function-calling format."""
        formatted = []
        for t in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return formatted

    def send(
        self,
        messages: list[AgentMessage],
        tools: list[dict] | None = None,
    ) -> AgentMessage:
        """Send messages to the OpenAI API and return the response."""
        api_messages = []

        for msg in messages:
            if msg.role == "tool" and msg.tool_result:
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_result.tool_call_id,
                    "content": msg.tool_result.output,
                })
            elif msg.role == "assistant" and msg.tool_calls:
                tc_list = []
                for tc in msg.tool_calls:
                    tc_list.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    })
                entry = {
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": tc_list,
                }
                # Thinking models require their reasoning echoed back verbatim
                # on replay, or the request is rejected.
                if msg.reasoning_content:
                    entry["reasoning_content"] = msg.reasoning_content
                api_messages.append(entry)
            else:
                entry = {
                    "role": msg.role,
                    "content": msg.content,
                }
                if msg.role == "assistant" and msg.reasoning_content:
                    entry["reasoning_content"] = msg.reasoning_content
                api_messages.append(entry)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": self._max_tokens,
        }
        if tools:
            kwargs["tools"] = self.format_tools(tools)

        extra_body, top_level = self._thinking_kwargs()
        kwargs.update(top_level)
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, AttributeError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        return AgentMessage(
            role="assistant",
            content=message.content or "",
            tool_calls=tool_calls,
            # Captured so the next request can echo it back. Providers that
            # don't emit reasoning simply leave this None.
            reasoning_content=getattr(message, "reasoning_content", None),
        )
