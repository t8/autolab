"""Metric collectors — extract metrics from experiment output."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class MetricPattern:
    """A single metric extraction pattern."""

    def __init__(self, name: str, pattern: str, type: str = "float", source: str = "stdout"):
        self.name = name
        self.pattern = pattern
        self.source = source
        self._type = {"float": float, "int": int, "str": str}.get(type, float)

    def extract(self, text: str) -> Any | None:
        m = re.search(self.pattern, text)
        if m:
            try:
                return self._type(m.group(1))
            except (ValueError, IndexError):
                return None
        return None


class StdoutCollector:
    """Parses metrics from experiment stdout using regex patterns."""

    def __init__(self, patterns: list[dict[str, Any]]):
        self.patterns = [
            MetricPattern(
                name=p["name"],
                pattern=p["pattern"],
                type=p.get("type", "float"),
                source=p.get("source", "stdout"),
            )
            for p in patterns
        ]

    def collect(self, stdout: str, stderr: str = "") -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        for p in self.patterns:
            text = stderr if p.source == "stderr" else stdout
            val = p.extract(text)
            if val is not None:
                metrics[p.name] = val
        return metrics

    @classmethod
    def from_campaign_config(cls, metrics_config: dict) -> StdoutCollector:
        """Create a collector from a campaign's metrics.collect config."""
        patterns = metrics_config.get("collect", [])
        return cls(patterns)


class FileCollector:
    """Reads metrics from a JSON file written by the experiment."""

    def __init__(self, output_path: str, format: str = "json"):
        self.output_path = Path(output_path)
        self.format = format

    def collect(self, stdout: str = "", stderr: str = "") -> dict[str, Any]:
        if not self.output_path.exists():
            return {}
        text = self.output_path.read_text()
        if self.format == "json":
            return json.loads(text)
        return {}
