"""Tests for the campaign scheduler — priority ranking and moonshot ratio."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from autolab.core.scheduler import CampaignScheduler
from autolab.core.plan import ResearchPlan
from autolab.state.project import ProjectState


def _setup_project(tmp: Path, questions=None, moonshot_ratio=0.5, enforce="soft"):
    """Create a minimal project with config, plan, and state."""
    config = {
        "directive": "Test",
        "strategy": {
            "moonshot_ratio": moonshot_ratio,
            "enforce": enforce,
        },
        "targets": {"min_campaigns": 10, "min_experiments": 100},
    }
    (tmp / "autolab.yaml").write_text(yaml.dump(config))

    plan_data = {
        "directive": "Test",
        "status": "active",
        "questions": questions or [],
    }
    (tmp / "research_plan.yaml").write_text(yaml.dump(plan_data))

    state = ProjectState(tmp)
    state.save({
        "iteration": 0,
        "moonshot_count": 0,
        "non_moonshot_count": 0,
        "total_experiments_run": 0,
    })


def _write_campaign(tmp: Path, name: str, question: str = "", moonshot: bool = False, grid_size: int = 3):
    campaigns_dir = tmp / "campaigns"
    campaigns_dir.mkdir(exist_ok=True)
    campaign = {
        "name": name,
        "hypothesis": f"Test {name}",
        "question": question,
        "moonshot": moonshot,
        "grid": {"x": list(range(grid_size))},
        "runner": {"backend": "local", "command": "echo test"},
    }
    path = campaigns_dir / f"{name}.yaml"
    path.write_text(yaml.dump(campaign))
    return str(path)


class TestScheduler:
    def test_rank_by_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_project(tmp, questions=[
                {"id": "q1", "text": "Low", "status": "active", "priority": "low"},
                {"id": "q2", "text": "High", "status": "active", "priority": "high"},
            ])
            c1 = _write_campaign(tmp, "low_camp", question="q1")
            c2 = _write_campaign(tmp, "high_camp", question="q2")

            scheduler = CampaignScheduler(tmp)
            ranked = scheduler.rank_campaigns([c1, c2])
            assert ranked[0].campaign_path == c2  # high priority first

    def test_moonshot_bonus(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_project(tmp, moonshot_ratio=0.5)

            # State: 0 moonshots, 0 non-moonshots -> deficit = 0.5
            c1 = _write_campaign(tmp, "normal", moonshot=False)
            c2 = _write_campaign(tmp, "moon", moonshot=True)

            scheduler = CampaignScheduler(tmp)
            ranked = scheduler.rank_campaigns([c1, c2])
            # Moonshot should rank higher due to deficit bonus
            assert ranked[0].campaign_path == c2

    def test_moonshot_ratio_calculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_project(tmp, moonshot_ratio=0.5)

            state = ProjectState(tmp)
            state.save({"moonshot_count": 3, "non_moonshot_count": 7})

            scheduler = CampaignScheduler(tmp)
            assert scheduler.current_moonshot_ratio() == 0.3
            assert scheduler.moonshot_deficit() == 0.2  # 0.5 - 0.3

    def test_moonshot_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_project(tmp, moonshot_ratio=0.5)

            state = ProjectState(tmp)
            state.save({"moonshot_count": 1, "non_moonshot_count": 9})

            scheduler = CampaignScheduler(tmp)
            warning = scheduler.check_moonshot_warning()
            assert warning is not None
            assert "10%" in warning

    def test_no_moonshot_warning_when_met(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_project(tmp, moonshot_ratio=0.5)

            state = ProjectState(tmp)
            state.save({"moonshot_count": 5, "non_moonshot_count": 5})

            scheduler = CampaignScheduler(tmp)
            assert scheduler.check_moonshot_warning() is None

    def test_hard_enforce_picks_moonshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_project(tmp, moonshot_ratio=0.5, enforce="hard")

            # State: 0 moonshots -> deficit
            c1 = _write_campaign(tmp, "normal1", moonshot=False)
            c2 = _write_campaign(tmp, "normal2", moonshot=False)
            c3 = _write_campaign(tmp, "moon", moonshot=True)

            scheduler = CampaignScheduler(tmp)
            rec = scheduler.next_campaign([c1, c2, c3])
            assert "moon" in rec.campaign_path

    def test_next_campaign_returns_top(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_project(tmp, questions=[
                {"id": "q1", "text": "Test", "status": "active", "priority": "high"},
            ])
            c1 = _write_campaign(tmp, "camp1", question="q1")

            scheduler = CampaignScheduler(tmp)
            rec = scheduler.next_campaign([c1])
            assert rec is not None
            assert rec.campaign_path == c1

    def test_empty_campaigns_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_project(tmp)
            scheduler = CampaignScheduler(tmp)
            assert scheduler.next_campaign([]) is None

    def test_diversity_bonus(self):
        """Campaigns for questions not recently tested get a diversity bonus."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_project(tmp, questions=[
                {"id": "q1", "text": "Tested", "status": "active", "priority": "medium",
                 "campaigns": ["recent_camp"]},
                {"id": "q2", "text": "Fresh", "status": "active", "priority": "medium"},
            ])

            # Simulate recent history with q1's campaign
            from autolab.metrics.db import ResultsDB
            db = ResultsDB(tmp / "results.db")
            db.store_result({
                "experiment_name": "recent_camp_x=1",
                "campaign_name": "recent_camp",
                "metrics": {},
                "status": "completed",
            })

            c1 = _write_campaign(tmp, "tested_camp", question="q1")
            c2 = _write_campaign(tmp, "fresh_camp", question="q2")

            scheduler = CampaignScheduler(tmp)
            ranked = scheduler.rank_campaigns([c1, c2])
            # fresh_camp should rank higher due to diversity bonus
            assert ranked[0].campaign_path == c2
