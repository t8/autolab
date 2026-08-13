"""Tests for the provider registry — the seam that makes the executing model swappable.

Autolab's architecture (campaigns, runners, metrics, state) is independent of
which model drives the loop. These tests pin that separation: adding or swapping
a provider is config or a dropped-in file, never a core edit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from autolab.agents.providers import (
    CHAT_COMPLETIONS,
    EXTERNAL,
    MESSAGES,
    ProviderProfile,
    get_provider,
    list_providers,
    load_provider_dir,
    profile_for_model,
    provider_names,
    register_provider,
)


def test_builtin_providers_registered():
    names = provider_names()
    for expected in ("anthropic", "openai", "openai-compatible",
                     "deepseek", "openrouter", "ollama", "agent-driven"):
        assert expected in names, f"missing built-in provider: {expected}"


def test_lookup_by_alias_and_case():
    assert get_provider("claude") is get_provider("anthropic")
    assert get_provider("  DeepSeek  ") is get_provider("deepseek")
    assert get_provider("nope") is None
    assert get_provider(None) is None


def test_api_modes():
    assert get_provider("anthropic").api_mode == MESSAGES
    assert get_provider("deepseek").api_mode == CHAT_COMPLETIONS
    # agent-driven means a harness owns the loop and picks the model
    assert get_provider("agent-driven").api_mode == EXTERNAL
    # legacy/harness-specific aliases resolve to the same profile
    assert get_provider("claude-code") is get_provider("agent-driven")
    assert get_provider("hermes") is get_provider("agent-driven")


def test_profiles_declare_key_env_and_defaults():
    ds = get_provider("deepseek")
    assert ds.api_key_env == "DEEPSEEK_API_KEY"
    assert ds.base_url == "https://api.deepseek.com/v1"
    assert ds.default_model == "deepseek-v4-pro"

    anthropic = get_provider("anthropic")
    assert anthropic.api_key_env == "ANTHROPIC_API_KEY"
    assert anthropic.default_model == "claude-opus-5"


def test_anthropic_default_model_is_current():
    """Guards against the default drifting back to a retired model id."""
    anthropic = get_provider("anthropic")
    assert not anthropic.default_model.startswith("claude-sonnet-4-2025")
    for model in anthropic.fallback_models:
        # Current Claude aliases carry no date suffix.
        assert not model[-9:].lstrip("-").isdigit(), f"dated model id: {model}"


# ── Wire quirks follow the model, not the route ──────────────────────────────

@pytest.mark.parametrize("model,owned", [
    ("deepseek-v4-pro", True),
    ("deepseek-v4-flash", True),
    ("deepseek-v5-pro", True),
    ("deepseek/deepseek-v4-pro", True),    # routed via OpenRouter
    ("deepseek-v3", False),                # V3 wire format must not change
    ("deepseek-v3-chat", False),
    ("gpt-4o", False),
    ("meta-llama/llama-3-70b", False),
    ("claude-opus-5", False),
    ("", False),
    (None, False),
])
def test_profile_for_model(model, owned):
    profile = profile_for_model(model)
    assert (profile is not None and profile.name == "deepseek") is owned


def test_routed_deepseek_gets_deepseek_quirks():
    """A DeepSeek model over OpenRouter must still send the thinking flag."""
    deepseek = get_provider("deepseek")
    extra_body, _ = deepseek.build_api_kwargs_extras(model="deepseek/deepseek-v4-pro")
    assert extra_body == {"thinking": {"type": "enabled"}}


def test_plain_profile_has_no_quirks():
    """Providers without quirks leave the wire format untouched."""
    for name in ("openai", "openrouter", "ollama", "openai-compatible"):
        profile = get_provider(name)
        assert profile.build_api_kwargs_extras(model="gpt-4o") == ({}, {})
        assert profile.owns_model("gpt-4o") is False


def test_deepseek_profile_ignores_foreign_models():
    """The DeepSeek profile must not stamp quirks onto another provider's model."""
    deepseek = get_provider("deepseek")
    assert deepseek.build_api_kwargs_extras(model="gpt-4o") == ({}, {})


# ── External profiles: adding a model without editing autolab ────────────────

PROFILE_SOURCE = '''
from autolab.agents.providers import ProviderProfile, register_provider

register_provider(ProviderProfile(
    name="test-local-llm",
    aliases=("tll",),
    display_name="Test Local LLM",
    env_vars=("TEST_LLM_KEY",),
    base_url="http://localhost:9999/v1",
    default_model="test-model-1",
))
'''


def test_external_profile_is_loaded_from_directory():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "local_llm.py").write_text(PROFILE_SOURCE)
        loaded = load_provider_dir(d)
        assert loaded == ["local_llm.py"]

        profile = get_provider("test-local-llm")
        assert profile is not None
        assert profile.base_url == "http://localhost:9999/v1"
        assert profile.default_model == "test-model-1"
        assert get_provider("tll") is profile


def test_missing_provider_dir_is_not_an_error():
    assert load_provider_dir("/nonexistent/path/for/providers") == []


def test_broken_profile_is_skipped_not_fatal(capsys):
    """One bad profile must not take down an unrelated research run."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "broken.py").write_text("raise RuntimeError('boom')")
        (Path(d) / "good.py").write_text(PROFILE_SOURCE.replace(
            "test-local-llm", "test-still-loads").replace('("tll",)', "()"))

        loaded = load_provider_dir(d)
        assert "good.py" in loaded
        assert "broken.py" not in loaded
        assert get_provider("test-still-loads") is not None
        assert "skipped provider profile" in capsys.readouterr().err


def test_underscore_files_are_ignored():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "_helper.py").write_text("raise RuntimeError('should not run')")
        assert load_provider_dir(d) == []


def test_registering_same_name_overrides():
    """An external profile can deliberately override a built-in."""
    original = get_provider("ollama")
    try:
        register_provider(ProviderProfile(
            name="ollama",
            base_url="http://elsewhere:1234/v1",
            default_model="pinned-model",
        ))
        assert get_provider("ollama").default_model == "pinned-model"
        # no duplicate canonical entry
        assert provider_names().count("ollama") == 1
    finally:
        register_provider(original)
    assert get_provider("ollama") is original


def test_list_providers_is_deduplicated_and_sorted():
    profiles = list_providers()
    names = [p.name for p in profiles]
    assert names == sorted(names)
    assert len(names) == len(set(names))
