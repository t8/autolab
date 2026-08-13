# Providers — swapping the executing model

Autolab separates **the research architecture** from **the model that executes it**.
Campaigns, runners, metrics, the journal, the plan, and project state are all
model-independent. The seam between them is a **provider profile**.

Switching from Claude to DeepSeek to a local model is a config change. Adding a
provider autolab has never heard of is a dropped-in file. Neither requires
editing autolab.

```bash
autolab providers        # backends, default models, and whether each key is set
```

## Switching the model

One line in `autolab.yaml`:

```yaml
agent:
  backend: deepseek        # deepseek-v4-pro via the native DeepSeek API
```

Each backend supplies its own endpoint, key environment variable, and default
model. Anything you set explicitly overrides those defaults:

```yaml
agent:
  backend: openrouter
  model: deepseek/deepseek-v4-pro
  reasoning_effort: high
```

| Backend | Default model | Key |
|---|---|---|
| `anthropic` | `claude-opus-5` | `ANTHROPIC_API_KEY` |
| `deepseek` | `deepseek-v4-pro` | `DEEPSEEK_API_KEY` |
| `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| `openrouter` | *(name the routed model)* | `OPENROUTER_API_KEY` |
| `ollama` | *(name the local model)* | — |
| `openai-compatible` | *(supply `base_url` + `model`)* | `OPENAI_API_KEY` |
| `claude-code` | — | driven by the plugin, not `autolab loop` |

## Wire quirks follow the model, not the route

A provider's request quirks are declared on its profile and matched against the
**model id**, so a model reached through a router still gets its own provider's
handling:

```
backend: deepseek      model: deepseek-v4-pro           -> DeepSeek thinking flags
backend: openrouter    model: deepseek/deepseek-v4-pro  -> DeepSeek thinking flags
backend: openrouter    model: meta-llama/llama-3-70b    -> untouched
```

This matters because DeepSeek's V4 family defaults thinking ON when
`extra_body.thinking` is unset, then requires later turns to echo
`reasoning_content` back. Since the agent harness replays the full message
history every tool round, a backend that ignores this fails with HTTP 400
immediately after the first tool call — routed or not.

## Adding a provider without touching autolab

Drop a `.py` file into either directory:

```
~/.autolab/providers/*.py     # user-wide
<project>/providers/*.py      # this research project only
```

```python
from autolab.agents.providers import ProviderProfile, register_provider

register_provider(ProviderProfile(
    name="my-cluster",
    display_name="Internal vLLM cluster",
    env_vars=("MY_CLUSTER_KEY",),
    base_url="https://llm.internal.example/v1",
    default_model="qwen-72b",
))
```

`autolab providers` now lists it and `backend: my-cluster` works. Registering an
existing name deliberately overrides the built-in — useful for pinning a
different default model org-wide. A profile that raises is skipped with a
warning rather than taking down the run.

For a provider with request quirks, subclass and override two methods:

```python
class MyProfile(ProviderProfile):
    def owns_model(self, model):
        return (model or "").startswith("my-")

    def build_api_kwargs_extras(self, *, model=None, thinking=True, reasoning_effort=None):
        return {"custom_flag": True}, {}   # (extra_body, top_level)
```

## Profile fields

| Field | Purpose |
|---|---|
| `name`, `aliases` | Lookup keys for `backend:` |
| `api_mode` | `chat_completions` (OpenAI-compatible), `messages` (Anthropic), or `external` |
| `env_vars` | Key environment variables; the first is primary |
| `base_url` | Endpoint; omit for providers with a fixed SDK default |
| `default_model`, `fallback_models` | Default and the catalog shown by `autolab providers` |
| `owns_model()` | Which model ids this provider's quirks apply to |
| `build_api_kwargs_extras()` | Returns `(extra_body, top_level)` request extras |

The shape deliberately mirrors Hermes' `providers.base.ProviderProfile`
(`/usr/local/lib/hermes-agent/providers/`), so a profile written for one agent
on a shared machine ports to the other with minimal edits.
