"""Tests for the research loop — end-to-end campaign execution."""

import tempfile
from pathlib import Path

import yaml

from autolab.core.loop import ResearchLoop


def test_run_campaign_end_to_end():
    """Full loop: create campaign -> run -> verify results in DB."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # Write a campaign that echoes metrics
        campaign = {
            "name": "e2e_test",
            "hypothesis": "Echo commands produce parseable metrics",
            "grid": {"val": [10, 20, 30]},
            "runner": {
                "backend": "local",
                "command": "echo 'Score: {val}.0'",
                "working_dir": ".",
            },
            "metrics": {
                "primary": "score",
                "direction": "maximize",
                "collect": [
                    {"name": "score", "pattern": r"Score: ([\d.]+)", "type": "float"},
                ],
            },
            "stopping": {"window": 3, "threshold": 0.05, "max_failures": 3},
        }
        campaign_path = tmp / "campaign.yaml"
        campaign_path.write_text(yaml.dump(campaign))

        db_path = tmp / "results.db"
        loop = ResearchLoop(db_path)
        results = loop.run_campaign(str(campaign_path))

        assert len(results) == 3
        assert all(r.status == "completed" for r in results)
        assert results[0].metrics["score"] == 10.0
        assert results[2].metrics["score"] == 30.0

        # Verify DB
        history = loop.db.load_history("e2e_test")
        assert len(history) == 3
        assert loop.db.count_experiments() == 3


def test_run_campaign_resumes():
    """Running a campaign twice doesn't re-run completed experiments."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        campaign = {
            "name": "resume_test",
            "grid": {"x": [1, 2, 3]},
            "runner": {"backend": "local", "command": "echo 'Score: {x}'"},
            "metrics": {
                "primary": "score",
                "direction": "maximize",
                "collect": [{"name": "score", "pattern": r"Score: (\d+)", "type": "int"}],
            },
        }
        path = tmp / "campaign.yaml"
        path.write_text(yaml.dump(campaign))

        db_path = tmp / "results.db"
        loop = ResearchLoop(db_path)

        # First run
        results1 = loop.run_campaign(str(path))
        assert len(results1) == 3

        # Second run — should find all completed and run nothing new
        results2 = loop.run_campaign(str(path))
        assert len(results2) == 0

        # DB should still have exactly 3
        assert loop.db.count_experiments() == 3


def test_campaign_failure_handling():
    """Failed experiments are stored and counted."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        campaign = {
            "name": "fail_test",
            "grid": {"x": [1]},
            "runner": {"backend": "local", "command": "exit 1"},
            "metrics": {"collect": []},
            "stopping": {"max_failures": 1},
        }
        path = tmp / "campaign.yaml"
        path.write_text(yaml.dump(campaign))

        loop = ResearchLoop(tmp / "results.db")
        results = loop.run_campaign(str(path))
        assert len(results) == 1
        assert results[0].status == "failed"
