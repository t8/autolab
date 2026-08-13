"""Provider registry — name/alias lookup plus external profile loading.

Adding a model should not mean editing autolab. Drop a `.py` file that calls
`register_provider(...)` into one of the profile directories and it is picked up
at startup:

    ~/.autolab/providers/*.py          (user-wide)
    <project>/providers/*.py           (per research project)

That is the whole extension mechanism — same registration call the built-in
profiles use.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .base import ProviderProfile

# name/alias -> profile. Aliases and canonical names share one namespace so
# lookup is a single dict hit.
_REGISTRY: dict[str, ProviderProfile] = {}
_CANONICAL: dict[str, ProviderProfile] = {}


def register_provider(profile: ProviderProfile) -> ProviderProfile:
    """Register a profile under its name and every alias.

    Re-registering a name replaces the previous profile, so an external file can
    deliberately override a built-in (e.g. to pin a different default model).
    """
    _CANONICAL[profile.name] = profile
    _REGISTRY[profile.name] = profile
    for alias in profile.aliases:
        _REGISTRY[alias] = profile
    return profile


def get_provider(name: str | None) -> ProviderProfile | None:
    """Look up a profile by name or alias. Returns None when unknown."""
    if not name:
        return None
    return _REGISTRY.get(name.strip().lower())


def list_providers() -> list[ProviderProfile]:
    """All registered profiles, deduplicated, sorted by canonical name."""
    return [_CANONICAL[n] for n in sorted(_CANONICAL)]


def provider_names() -> list[str]:
    """Canonical provider names, sorted — for CLI help and error messages."""
    return sorted(_CANONICAL)


def profile_for_model(model: str | None) -> ProviderProfile | None:
    """Find the profile that claims `model`, regardless of how it is routed.

    Lets a DeepSeek model reached over OpenRouter still receive DeepSeek's
    wire-format handling. Returns None when no profile claims it.
    """
    if not model:
        return None
    for profile in list_providers():
        if profile.owns_model(model):
            return profile
    return None


def load_provider_dir(directory: str | Path) -> list[str]:
    """Execute every `*.py` in `directory` so it can register profiles.

    Returns the filenames loaded. Missing directories are not an error — the
    common case is that a user has no custom profiles. A file that raises is
    skipped with a warning rather than taking down the run, so one bad profile
    cannot block an unrelated research loop.
    """
    path = Path(directory).expanduser()
    if not path.is_dir():
        return []

    loaded: list[str] = []
    for file in sorted(path.glob("*.py")):
        if file.name.startswith("_"):
            continue
        module_name = f"autolab_provider_{file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            loaded.append(file.name)
        except Exception as exc:  # noqa: BLE001 - a bad profile must not be fatal
            print(f"[autolab] skipped provider profile {file}: {exc}", file=sys.stderr)
            sys.modules.pop(module_name, None)
    return loaded


def load_external_providers(project_dir: str | Path | None = None) -> list[str]:
    """Load user-wide and per-project provider profiles."""
    loaded = load_provider_dir(Path.home() / ".autolab" / "providers")
    if project_dir:
        loaded += load_provider_dir(Path(project_dir) / "providers")
    return loaded
