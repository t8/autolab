"""Project state management — .autolab/state.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProjectState:
    """Manages .autolab/state.json — machine-readable loop state."""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.state_dir = self.project_dir / ".autolab"
        self.state_path = self.state_dir / "state.json"

    def load(self) -> dict[str, Any]:
        """Load state from disk. Returns defaults if file doesn't exist."""
        if not self.state_path.exists():
            return self._defaults()
        try:
            return json.loads(self.state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return self._defaults()

    def save(self, state: dict[str, Any]) -> None:
        """Save state to disk."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2) + "\n")

    def update(self, **kwargs: Any) -> dict[str, Any]:
        """Load, update specific keys, save, and return the new state."""
        state = self.load()
        state.update(kwargs)
        self.save(state)
        return state

    def increment(self, key: str, amount: int = 1) -> int:
        """Increment a numeric counter and return the new value."""
        state = self.load()
        state[key] = state.get(key, 0) + amount
        self.save(state)
        return state[key]

    def _defaults(self) -> dict[str, Any]:
        return {
            "iteration": 0,
            "total_campaigns_created": 0,
            "total_experiments_run": 0,
            "total_discoveries": 0,
            "active_questions": [],
            "last_campaign": None,
            "consecutive_no_improvement": 0,
            "moonshot_count": 0,
            "non_moonshot_count": 0,
        }

    def load_config(self) -> dict[str, Any]:
        """Load autolab.yaml project config."""
        config_path = self.project_dir / "autolab.yaml"
        if not config_path.exists():
            return {}
        import yaml
        return yaml.safe_load(config_path.read_text()) or {}

    def check_targets(self) -> dict[str, Any]:
        """Check progress against configured targets."""
        config = self.load_config()
        targets = config.get("targets", {})
        state = self.load()

        min_campaigns = targets.get("min_campaigns", 0)
        min_experiments = targets.get("min_experiments", 0)

        return {
            "campaigns_target": min_campaigns,
            "campaigns_current": state.get("total_campaigns_created", 0),
            "campaigns_met": state.get("total_campaigns_created", 0) >= min_campaigns,
            "experiments_target": min_experiments,
            "experiments_current": state.get("total_experiments_run", 0),
            "experiments_met": state.get("total_experiments_run", 0) >= min_experiments,
            "all_met": (
                state.get("total_campaigns_created", 0) >= min_campaigns
                and state.get("total_experiments_run", 0) >= min_experiments
            ),
        }
