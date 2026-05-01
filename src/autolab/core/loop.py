"""Research loop — runs campaigns and stores results."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .campaign import Campaign
from .experiment import ExperimentResult
from ..metrics.collectors import StdoutCollector
from ..metrics.db import ResultsDB
from ..runners.base import RunnerBase
from ..runners.local import LocalRunner
from ..runners.ssh import SSHRunner


RUNNER_BACKENDS: dict[str, type] = {
    "local": LocalRunner,
    "ssh": SSHRunner,
}

try:
    from cascadia_fleet.autolab import FleetRunner  # type: ignore
    RUNNER_BACKENDS["fleet"] = FleetRunner
except Exception:
    pass


def get_runner(campaign: Campaign) -> RunnerBase:
    """Create a runner from a campaign's runner config."""
    backend = campaign.runner_config.get("backend", "local")
    runner_cls = RUNNER_BACKENDS.get(backend)
    if runner_cls is None:
        raise ValueError(f"Unknown runner backend: {backend!r}. Available: {list(RUNNER_BACKENDS)}")

    # Resolve working_dir relative to the project root (campaign file's grandparent,
    # since campaigns are typically in a campaigns/ subdirectory)
    config = dict(campaign.runner_config)
    if "working_dir" in config:
        wd = Path(config["working_dir"])
        if not wd.is_absolute():
            # Try project root (parent of campaigns/) first, fall back to campaign dir
            project_root = campaign.campaign_path.parent.parent
            resolved = project_root / wd
            if not resolved.exists():
                resolved = campaign.campaign_path.parent / wd
            config["working_dir"] = str(resolved)

    return runner_cls.from_campaign_config(config)


class ResearchLoop:
    """Runs experiment campaigns and tracks results.

    This is the core engine that drives the research cycle:
    load campaign -> get next experiment -> run -> store -> check stopping -> repeat.
    """

    def __init__(self, db_path: str | Path = "results.db"):
        self.db = ResultsDB(db_path)

    def run_campaign(self, campaign_path: str | Path) -> list[ExperimentResult]:
        """Run a full campaign loop. Returns all results."""
        campaign = Campaign(campaign_path)
        runner = get_runner(campaign)
        collector = StdoutCollector.from_campaign_config(campaign.metrics_config)

        total = campaign.experiment_count()
        print(f"\n{'#' * 60}")
        print(f"# Campaign: {campaign.name}")
        print(f"# Hypothesis: {campaign.hypothesis}")
        print(f"# Experiments: {total}")
        print(f"# Backend: {campaign.runner_config.get('backend', 'local')}")
        print(f"{'#' * 60}\n")

        history = self.db.load_history(campaign.name)
        print(f"Loaded {len(history)} previous results for this campaign.\n")

        results: list[ExperimentResult] = []
        max_failures = campaign.stopping_config.get("max_failures", 3)
        consecutive_failures = 0

        while True:
            experiment = campaign.get_next_experiment(history)
            if experiment is None:
                print("\nAll experiments in campaign have been completed.")
                break

            run_num = len(history) + 1
            print(f"\n--- Experiment {run_num}/{total}: {experiment['name']} ---")

            try:
                result = runner.execute(experiment, collector)
                consecutive_failures = 0 if result.status == "completed" else consecutive_failures + 1
            except Exception as e:
                print(f"EXPERIMENT FAILED: {e}")
                result = ExperimentResult(
                    experiment_name=experiment["name"],
                    campaign_name=campaign.name,
                    config=experiment,
                    status="failed",
                    error=str(e),
                )
                consecutive_failures += 1

            run_id = self.db.store_result(result.to_dict())
            print(f"Stored as {run_id} [{result.status}]")

            if result.metrics:
                for k, v in result.metrics.items():
                    print(f"  {k}: {v}")

            results.append(result)
            history.append(result.to_dict())

            if consecutive_failures >= max_failures:
                print(f"\n{max_failures} consecutive failures — stopping campaign.")
                break

            if campaign.check_diminishing_returns(history):
                print("\nDiminishing returns detected — stopping early.")
                break

        self._print_summary(campaign, history)
        return results

    def _print_summary(self, campaign: Campaign, history: list[dict]) -> None:
        """Print a campaign summary."""
        print(f"\n{'=' * 60}")
        print(f"Campaign Summary: {campaign.name}")
        print(f"{'=' * 60}")

        summary = self.db.campaign_summary(campaign.name)
        print(f"Total: {summary['total']} ({summary['completed']} completed, {summary['failed']} failed)")

        if campaign.primary_metric:
            completed = [r for r in history if r.get("status") == "completed"]
            best = campaign.best_result(completed)
            if best:
                best_val = best.get("metrics", {}).get(campaign.primary_metric, "N/A")
                print(f"\nBest {campaign.primary_metric}: {best_val}")
                print(f"  Experiment: {best.get('experiment_name')}")

        print(f"{'=' * 60}\n")
