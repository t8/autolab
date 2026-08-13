"""Built-in provider profiles.

Each entry is data, not code, except where a provider has a genuine wire-format
quirk (DeepSeek). Adding a model to an existing provider is a one-line edit
here; adding a whole provider is a new `register_provider(...)` call — in this
file, or in an external profile directory (see `registry.load_external_providers`).
"""

from __future__ import annotations

from typing import Any

from .base import CHAT_COMPLETIONS, EXTERNAL, MESSAGES, ProviderProfile
from .registry import register_provider


# ── Anthropic ────────────────────────────────────────────────────────────────

register_provider(ProviderProfile(
    name="anthropic",
    api_mode=MESSAGES,
    aliases=("claude",),
    display_name="Anthropic",
    description="Claude models via the native Anthropic Messages API",
    signup_url="https://console.anthropic.com/",
    env_vars=("ANTHROPIC_API_KEY",),
    default_model="claude-opus-5",
    fallback_models=(
        "claude-opus-5",
        "claude-fable-5",
        "claude-sonnet-5",
        "claude-haiku-4-5",
    ),
))


# ── Claude Code (driven by the plugin, not by `autolab loop`) ────────────────

register_provider(ProviderProfile(
    name="claude-code",
    api_mode=EXTERNAL,
    display_name="Claude Code",
    description="Driven by the Claude Code plugin via /autolab:research-loop",
    metadata={
        "external_hint": (
            "The 'claude-code' backend is driven by the Claude Code plugin, not "
            "by `autolab loop`.\nStart it from a Claude Code session in the "
            "project directory with:\n  /autolab:research-loop"
        ),
    },
))


# ── OpenAI and generic OpenAI-compatible endpoints ──────────────────────────

register_provider(ProviderProfile(
    name="openai",
    display_name="OpenAI",
    signup_url="https://platform.openai.com/",
    env_vars=("OPENAI_API_KEY",),
    default_model="gpt-4o",
))

register_provider(ProviderProfile(
    name="openai-compatible",
    aliases=("compatible", "custom"),
    display_name="OpenAI-compatible",
    description="Any OpenAI-compatible endpoint — supply base_url and model",
    env_vars=("OPENAI_API_KEY",),
))

register_provider(ProviderProfile(
    name="openrouter",
    display_name="OpenRouter",
    description="Model router — model ids are namespaced, e.g. deepseek/deepseek-v4-pro",
    signup_url="https://openrouter.ai/",
    env_vars=("OPENROUTER_API_KEY",),
    base_url="https://openrouter.ai/api/v1",
))

register_provider(ProviderProfile(
    name="ollama",
    display_name="Ollama",
    description="Local models served by Ollama",
    base_url="http://localhost:11434/v1",
))


# ── DeepSeek (thinking-mode wire quirks) ─────────────────────────────────────

class DeepSeekProfile(ProviderProfile):
    """DeepSeek — explicit `extra_body.thinking` plus top-level `reasoning_effort`.

    DeepSeek's V4 family defaults thinking ON when `extra_body.thinking` is
    unset. The API then returns `reasoning_content` and enforces that later
    turns echo it back, which lands on HTTP 400 "reasoning_content must be
    passed back" after the first tool call. Sending the flag explicitly — either
    value — makes the behavior deterministic instead of implicit.

    Mirrors the profile in Hermes' `plugins/model-providers/deepseek` so both
    agents on this machine speak the same wire format.
    """

    def owns_model(self, model: str | None) -> bool:
        """True for DeepSeek V4+ models, native or routed.

        Substring-based on purpose so a routed id (`deepseek/deepseek-v4-pro`
        over OpenRouter) is detected like a native one. V3 is excluded — its
        wire format has no thinking block and must not be perturbed.
        """
        m = (model or "").strip().lower()
        if not m or "deepseek" not in m:
            return False
        tail = m.rsplit("/", 1)[-1]
        if tail.startswith("deepseek-v3"):
            return False
        return tail.startswith("deepseek-v")

    def build_api_kwargs_extras(
        self,
        *,
        model: str | None = None,
        thinking: bool = True,
        reasoning_effort: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        extra_body: dict[str, Any] = {}
        top_level: dict[str, Any] = {}

        if not self.owns_model(model):
            return extra_body, top_level

        extra_body["thinking"] = {"type": "enabled" if thinking else "disabled"}
        if not thinking:
            return extra_body, top_level

        effort = (reasoning_effort or "").strip().lower()
        if effort in {"xhigh", "max", "ultra"}:
            top_level["reasoning_effort"] = "max"
        elif effort in {"low", "medium", "high"}:
            top_level["reasoning_effort"] = effort
        # unset -> omit, letting the provider apply its own default

        return extra_body, top_level


register_provider(DeepSeekProfile(
    name="deepseek",
    api_mode=CHAT_COMPLETIONS,
    display_name="DeepSeek",
    description="DeepSeek V4 family via the native DeepSeek API",
    signup_url="https://platform.deepseek.com/",
    env_vars=("DEEPSEEK_API_KEY",),
    base_url="https://api.deepseek.com/v1",
    default_model="deepseek-v4-pro",
    fallback_models=("deepseek-v4-pro", "deepseek-v4-flash"),
))
