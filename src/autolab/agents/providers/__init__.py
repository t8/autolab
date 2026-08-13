"""Provider profiles — modular, swappable model configuration.

Autolab's architecture (campaigns, runners, metrics, state) is independent of
which model drives the research loop. A ProviderProfile is the seam: it declares
where a provider lives, which env var holds its key, which backend speaks its
wire format, and any request quirks — so switching the executing model is a
config change, not a code change.

Importing this package registers the built-in profiles.
"""

from __future__ import annotations

from .base import CHAT_COMPLETIONS, EXTERNAL, MESSAGES, ProviderProfile
from .registry import (
    get_provider,
    list_providers,
    load_external_providers,
    load_provider_dir,
    profile_for_model,
    provider_names,
    register_provider,
)

# Registers the built-ins as a side effect. Kept last so the registry helpers
# above are importable from a profile module without a circular import.
from . import builtin  # noqa: E402,F401

__all__ = [
    "CHAT_COMPLETIONS",
    "EXTERNAL",
    "MESSAGES",
    "ProviderProfile",
    "get_provider",
    "list_providers",
    "load_external_providers",
    "load_provider_dir",
    "profile_for_model",
    "provider_names",
    "register_provider",
]
