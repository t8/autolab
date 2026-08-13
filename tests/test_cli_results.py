"""Tests for `autolab results` metric direction resolution.

Regression coverage for a bug where `results` always sorted DESCENDING and
labelled every query "(maximize)", ignoring the campaign's declared
`metrics.direction`. For a minimize metric such as latency it reported the
*worst* experiment first under a "Top N" heading.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml
from click.testing import CliRunner

from autolab.cli import main, _resolve_metric_direction
from autolab.metrics.db import ResultsDB


def _write_campaign(tmp: Path, name: str, metric: str, direction: str, filename: str):
    campaigns = tmp / "campaigns"
    campaigns.mkdir(exist_ok=True)
    config = {
        "name": name,
        "hypothesis": "test",
        "runner": {"backend": "local", "command": "echo test"},
        "grid": {"x": [1, 2]},
        "metrics": {
            "primary": metric,
            "direction": direction,
            "collect": [{"name": metric, "pattern": r"M: ([\d.]+)"}],
        },
    }
    (campaigns / filename).write_text(yaml.dump(config))


def _store(db: ResultsDB, campaign: str, name: str, metric: str, value: float):
    db.store_result({
        "campaign_name": campaign,
        "experiment_name": name,
        "config": {},
        "metrics": {metric: value},
        "status": "completed",
    })


def test_resolve_direction_from_campaign():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_campaign(tmp, "fast", "latency", "minimize", "001_fast.yaml")
        assert _resolve_metric_direction(tmp, "latency", "fast") == ("minimize", "fast")


def test_resolve_direction_defaults_to_maximize_when_undeclared():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_campaign(tmp, "fast", "latency", "minimize", "001_fast.yaml")
        # metric not declared primary by any campaign
        assert _resolve_metric_direction(tmp, "throughput", "fast") == ("maximize", None)


def test_resolve_direction_no_campaigns_dir():
    with tempfile.TemporaryDirectory() as d:
        assert _resolve_metric_direction(Path(d), "latency", None) == ("maximize", None)


def test_resolve_direction_unfiltered_requires_agreement():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_campaign(tmp, "a", "latency", "minimize", "001_a.yaml")
        _write_campaign(tmp, "b", "latency", "minimize", "002_b.yaml")
        # unanimous -> inferred
        assert _resolve_metric_direction(tmp, "latency", None) == ("minimize", None)

        # conflicting -> fall back rather than guess
        _write_campaign(tmp, "c", "latency", "maximize", "003_c.yaml")
        assert _resolve_metric_direction(tmp, "latency", None) == ("maximize", None)


def test_resolve_direction_ignores_malformed_yaml():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_campaign(tmp, "fast", "latency", "minimize", "001_fast.yaml")
        (tmp / "campaigns" / "002_broken.yaml").write_text("{[not: valid yaml")
        assert _resolve_metric_direction(tmp, "latency", "fast") == ("minimize", "fast")


def test_results_sorts_minimize_metric_best_first():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_campaign(tmp, "fast", "latency", "minimize", "001_fast.yaml")
        db = ResultsDB(tmp / "results.db")
        _store(db, "fast", "slow_run", "latency", 262.9)
        _store(db, "fast", "quick_run", "latency", 156.4)

        result = CliRunner().invoke(
            main,
            ["results", "--db", str(tmp / "results.db"),
             "--campaign", "fast", "--metric", "latency"],
        )
        assert result.exit_code == 0
        assert "minimize" in result.output
        # best (lowest) latency must be listed first
        assert result.output.index("quick_run") < result.output.index("slow_run")


def test_results_explicit_direction_overrides_campaign():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_campaign(tmp, "fast", "latency", "minimize", "001_fast.yaml")
        db = ResultsDB(tmp / "results.db")
        _store(db, "fast", "slow_run", "latency", 262.9)
        _store(db, "fast", "quick_run", "latency", 156.4)

        result = CliRunner().invoke(
            main,
            ["results", "--db", str(tmp / "results.db"), "--campaign", "fast",
             "--metric", "latency", "--direction", "maximize"],
        )
        assert result.exit_code == 0
        assert result.output.index("slow_run") < result.output.index("quick_run")


def test_results_maximize_metric_unchanged():
    """A maximize campaign must behave exactly as before the fix."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_campaign(tmp, "big", "throughput", "maximize", "001_big.yaml")
        db = ResultsDB(tmp / "results.db")
        _store(db, "big", "low", "throughput", 190.2)
        _store(db, "big", "high", "throughput", 319.7)

        result = CliRunner().invoke(
            main,
            ["results", "--db", str(tmp / "results.db"),
             "--campaign", "big", "--metric", "throughput"],
        )
        assert result.exit_code == 0
        assert result.output.index("high") < result.output.index("low")
