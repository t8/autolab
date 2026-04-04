"""Runner base class — abstract experiment execution lifecycle."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..core.experiment import ExperimentResult, RunResult
from ..metrics.collectors import StdoutCollector


class RunnerBase(ABC):
    """Base class for experiment execution backends.

    Subclasses implement the setup/run/cleanup lifecycle.
    The execute() method orchestrates the full flow and collects metrics.
    """

    @abstractmethod
    def setup(self, experiment: dict[str, Any]) -> None:
        """Prepare the execution environment. Called before run()."""

    @abstractmethod
    def run(self, experiment: dict[str, Any]) -> RunResult:
        """Execute the experiment. Returns raw stdout/stderr/returncode."""

    @abstractmethod
    def cleanup(self, experiment: dict[str, Any]) -> None:
        """Clean up after execution. Called after run(), even on failure."""

    def execute(
        self,
        experiment: dict[str, Any],
        collector: StdoutCollector | None = None,
    ) -> ExperimentResult:
        """Full lifecycle: setup -> run -> collect metrics -> cleanup."""
        try:
            self.setup(experiment)
            result = self.run(experiment)

            metrics: dict[str, Any] = {}
            if collector:
                metrics = collector.collect(result.stdout, result.stderr)

            status = "completed" if result.returncode == 0 else "failed"
            error = result.stderr.strip() if result.returncode != 0 else None

            return ExperimentResult(
                experiment_name=experiment.get("name", "unnamed"),
                campaign_name=experiment.get("campaign_name", ""),
                config=experiment,
                metrics=metrics,
                status=status,
                wall_time_s=result.wall_time_s,
                raw_output=result.stdout,
                error=error,
            )
        finally:
            self.cleanup(experiment)
