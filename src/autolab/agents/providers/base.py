"""Provider profile base class.

A ProviderProfile declares everything about an inference provider in one place:
which agent backend speaks its wire format, where its endpoint is, which env var
holds its key, and any request-time quirks it needs.

Profiles are DECLARATIVE — they describe the provider. They do not construct
clients or own credentials; that stays on the agent backends.

The shape deliberately mirrors Hermes' `providers.base.ProviderProfile`
(`/usr/local/lib/hermes-agent/providers/`) so a profile written for one agent on
this machine ports to the other with minimal edits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# api_mode values — which agent backend can drive this provider.
CHAT_COMPLETIONS = "chat_completions"  # OpenAI-compatible /v1/chat/completions
MESSAGES = "messages"                  # Anthropic Messages API
EXTERNAL = "external"                  # driven by an outside harness, not `autolab loop`


@dataclass
class ProviderProfile:
    """Base provider profile — instantiate with overrides, or subclass for quirks."""

    # ── Identity ─────────────────────────────────────────────
    name: str
    api_mode: str = CHAT_COMPLETIONS
    aliases: tuple[str, ...] = ()

    # ── Human-readable metadata ──────────────────────────────
    display_name: str = ""
    description: str = ""
    signup_url: str = ""

    # ── Auth & endpoint ──────────────────────────────────────
    # env_vars[0] is the primary key variable; the rest are accepted fallbacks.
    env_vars: tuple[str, ...] = ()
    base_url: str = ""

    # ── Model catalog ────────────────────────────────────────
    # default_model is used when neither the CLI nor autolab.yaml names one.
    default_model: str = ""
    fallback_models: tuple[str, ...] = ()

    # ── Escape hatch ─────────────────────────────────────────
    # Free-form provider metadata for profiles that need it. Never interpreted
    # by the registry.
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def api_key_env(self) -> str | None:
        """Primary environment variable holding this provider's key."""
        return self.env_vars[0] if self.env_vars else None

    def owns_model(self, model: str | None) -> bool:
        """True when `model` belongs to this provider's family.

        Used to apply wire-format quirks to a model reached through a *router*
        rather than through its native endpoint — e.g. `deepseek/deepseek-v4-pro`
        served over OpenRouter still needs DeepSeek's thinking handling.

        Default False: a plain profile claims no models by id.
        """
        return False

    def build_api_kwargs_extras(
        self,
        *,
        model: str | None = None,
        thinking: bool = True,
        reasoning_effort: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (extra_body, top_level) request extras for this provider.

        `extra_body` is passed through as the SDK's `extra_body`; `top_level` is
        merged into the request kwargs. Default is no extras, leaving the wire
        format untouched — override only for providers with real quirks.
        """
        return {}, {}
