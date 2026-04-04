"""Experiment result data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RunResult:
    """Raw result from a runner execution."""
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    wall_time_s: float = 0.0


@dataclass
class ExperimentResult:
    """Processed experiment result with metrics."""
    experiment_name: str
    campaign_name: str
    config: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    status: str = "completed"  # completed | failed
    wall_time_s: float = 0.0
    raw_output: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_name": self.experiment_name,
            "campaign_name": self.campaign_name,
            "config": self.config,
            "metrics": self.metrics,
            "status": self.status,
            "wall_time_s": self.wall_time_s,
            "raw_output": self.raw_output,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentResult:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
