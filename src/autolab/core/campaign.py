"""Campaign management — parameter grids and experiment sequencing."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any, Optional

import yaml


class Campaign:
    """Manages a parameter-grid campaign, tracking which experiments to run next.

    A campaign defines a hypothesis, a parameter grid, and how to run experiments.
    The grid is expanded into a Cartesian product of experiment configs.
    """

    def __init__(self, campaign_path: str | Path):
        self.campaign_path = Path(campaign_path)
        with open(self.campaign_path) as f:
            self.config = yaml.safe_load(f)

        self.name: str = self.config["name"]
        self.hypothesis: str = self.config.get("hypothesis", "")
        self.question: str = self.config.get("question", "")
        self.moonshot: bool = self.config.get("moonshot", False)
        self.grid: dict[str, list] = self.config.get("grid", {})
        self.defaults: dict[str, Any] = self.config.get("defaults", {})
        self.runner_config: dict[str, Any] = self.config.get("runner", {})
        self.metrics_config: dict[str, Any] = self.config.get("metrics", {})
        self.stopping_config: dict[str, Any] = self.config.get("stopping", {})
        self._experiments = self._expand_grid()

    @property
    def primary_metric(self) -> str:
        return self.metrics_config.get("primary", "")

    @property
    def metric_direction(self) -> str:
        return self.metrics_config.get("direction", "maximize")

    def _expand_grid(self) -> list[dict]:
        """Expand the parameter grid into a list of experiment configs."""
        if not self.grid:
            return [self._build_experiment({}, 0)]

        keys = sorted(self.grid.keys())
        value_lists = [self.grid[k] for k in keys]

        experiments = []
        for combo in itertools.product(*value_lists):
            params = dict(zip(keys, combo))
            exp = self._build_experiment(params, len(experiments))
            experiments.append(exp)
        return experiments

    def _build_experiment(self, params: dict, index: int) -> dict:
        """Build a full experiment config from grid parameters."""
        name_parts = [self.name]
        for k, v in sorted(params.items()):
            if isinstance(v, str) and len(v) > 40:
                name_parts.append(f"{k}={hash(v) % 10000:04d}")
            else:
                name_parts.append(f"{k}={v}")
        exp_name = "_".join(str(p) for p in name_parts)

        experiment: dict = {
            **self.defaults,
            **params,
            "name": exp_name,
            "campaign_name": self.name,
        }
        return experiment

    def get_all_experiments(self) -> list[dict]:
        """Return the full list of expanded experiments."""
        return list(self._experiments)

    def get_next_experiment(self, history: list[dict]) -> Optional[dict]:
        """Return the next experiment that hasn't been run yet."""
        completed_names = {r.get("experiment_name") for r in history}
        for exp in self._experiments:
            if exp["name"] not in completed_names:
                return exp
        return None

    def check_diminishing_returns(self, history: list[dict]) -> bool:
        """Check if recent experiments show diminishing returns.

        Uses configurable window and threshold. Returns True if we should stop.
        """
        window = self.stopping_config.get("window", 3)
        threshold = self.stopping_config.get("threshold", 0.05)

        if not self.primary_metric:
            return False

        campaign_results = [
            r for r in history
            if r.get("experiment_name", "").startswith(self.name)
            and r.get("status") == "completed"
        ]
        if len(campaign_results) < window + 1:
            return False

        best = self.best_result(campaign_results)
        if best is None:
            return False

        best_val = best.get("metrics", {}).get(self.primary_metric, 0)
        if best_val == 0:
            return False

        recent = campaign_results[-window:]
        for r in recent:
            val = r.get("metrics", {}).get(self.primary_metric, 0)
            improvement = abs(val - best_val) / abs(best_val)
            if improvement >= threshold:
                return False

        return True

    def best_result(self, history: list[dict]) -> Optional[dict]:
        """Return the best result from history by primary metric."""
        if not self.primary_metric:
            return None

        valid = [
            r for r in history
            if r.get("metrics", {}).get(self.primary_metric) is not None
        ]
        if not valid:
            return None

        reverse = self.metric_direction == "maximize"
        return sorted(
            valid,
            key=lambda r: r.get("metrics", {}).get(self.primary_metric, 0),
            reverse=reverse,
        )[0]

    def get_command(self, experiment: dict) -> str:
        """Build the shell command for an experiment by injecting parameters."""
        template = self.runner_config.get("command", "")
        try:
            return template.format(**experiment)
        except KeyError:
            return template

    def experiment_count(self) -> int:
        return len(self._experiments)

    def __repr__(self) -> str:
        return (
            f"Campaign(name={self.name!r}, "
            f"experiments={self.experiment_count()}, "
            f"hypothesis={self.hypothesis[:60]!r})"
        )
