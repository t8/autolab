"""Tests for research tree visualization."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from autolab.viz.tree import build_tree, render_terminal, render_dot
from autolab.metrics.db import ResultsDB


def _setup_project(tmp: Path):
    """Create a minimal project with plan, campaigns, and results."""
    config = {"directive": "Test directive", "strategy": {"moonshot_ratio": 0.5}}
    (tmp / "autolab.yaml").write_text(yaml.dump(config))

    plan = {
        "directive": "Test directive",
        "status": "active",
        "questions": [
            {"id": "q1", "text": "Does X affect Y?", "status": "active",
             "priority": "high", "campaigns": ["camp_a"]},
            {"id": "q2", "text": "Is Z better than W?", "status": "active",
             "priority": "medium", "campaigns": ["camp_b"]},
        ],
    }
    (tmp / "research_plan.yaml").write_text(yaml.dump(plan))

    (tmp / "campaigns").mkdir()

    # Campaign A — non-moonshot
    camp_a = {
        "name": "camp_a",
        "hypothesis": "X improves Y by 20%",
        "question": "q1",
        "moonshot": False,
        "grid": {"x": [1, 2, 3]},
        "runner": {"backend": "local", "command": "echo test"},
        "metrics": {"primary": "score", "direction": "maximize",
                    "collect": [{"name": "score", "pattern": r"Score: ([\d.]+)"}]},
    }
    (tmp / "campaigns" / "001_camp_a.yaml").write_text(yaml.dump(camp_a))

    # Campaign B — moonshot
    camp_b = {
        "name": "camp_b",
        "hypothesis": "Z is fundamentally better",
        "question": "q2",
        "moonshot": True,
        "grid": {"z": [10, 20]},
        "runner": {"backend": "local", "command": "echo test"},
        "metrics": {"primary": "score", "direction": "maximize",
                    "collect": [{"name": "score", "pattern": r"Score: ([\d.]+)"}]},
    }
    (tmp / "campaigns" / "050_camp_b.yaml").write_text(yaml.dump(camp_b))

    # Results
    db = ResultsDB(tmp / "results.db")
    for x, score in [(1, 50), (2, 80), (3, 60)]:
        db.store_result({
            "experiment_name": f"camp_a_x={x}",
            "campaign_name": "camp_a",
            "metrics": {"score": score},
            "status": "completed",
        })
    for z, score in [(10, 90), (20, 70)]:
        db.store_result({
            "experiment_name": f"camp_b_z={z}",
            "campaign_name": "camp_b",
            "metrics": {"score": score},
            "status": "completed",
        })
    db.store_result({
        "experiment_name": "camp_a_x=4",
        "campaign_name": "camp_a",
        "metrics": {},
        "status": "failed",
        "error": "crashed",
    })


def test_build_tree():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _setup_project(tmp)
        root = build_tree(tmp)

        assert root.directive == "Test directive"
        assert len(root.questions) == 2
        assert root.global_best_value == 90.0
        assert root.global_best_metric == "score"

        # q1 has camp_a
        q1 = root.questions[0]
        assert q1.id == "q1"
        assert len(q1.campaigns) == 1
        assert q1.campaigns[0].name == "camp_a"
        assert q1.campaigns[0].completed == 3
        assert q1.campaigns[0].failed == 1

        # q2 has camp_b (moonshot, on best path)
        q2 = root.questions[1]
        assert q2.id == "q2"
        assert q2.campaigns[0].moonshot is True
        assert q2.is_on_best_path is True
        assert q2.campaigns[0].is_on_best_path is True


def test_best_path_marked():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _setup_project(tmp)
        root = build_tree(tmp)

        # The global best is camp_b z=10 (score=90)
        q2 = [q for q in root.questions if q.id == "q2"][0]
        assert q2.is_on_best_path
        camp_b = q2.campaigns[0]
        assert camp_b.is_on_best_path
        best_exp = [e for e in camp_b.experiments if e.is_global_best]
        assert len(best_exp) == 1
        assert best_exp[0].primary_value == 90.0


def test_render_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _setup_project(tmp)
        root = build_tree(tmp)
        output = render_terminal(root, color=False)

        assert "Test directive" in output
        assert "q1" in output
        assert "q2" in output
        assert "camp_a" in output
        assert "camp_b" in output
        assert "BEST" in output
        assert "🌙" in output


def test_render_terminal_no_color():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _setup_project(tmp)
        root = build_tree(tmp)
        output = render_terminal(root, color=False)
        # No ANSI escape codes
        assert "\033[" not in output


def test_render_dot():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _setup_project(tmp)
        root = build_tree(tmp)
        dot = render_dot(root)

        assert "digraph autolab" in dot
        assert "Test directive" in dot
        assert "camp_a" in dot
        assert "camp_b" in dot
        assert "#2E7D32" in dot  # best path green color
        assert "penwidth=3" in dot  # global best thick border


def test_empty_project():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config = {"directive": "Empty project"}
        (tmp / "autolab.yaml").write_text(yaml.dump(config))
        (tmp / "research_plan.yaml").write_text(yaml.dump({"questions": []}))
        (tmp / "campaigns").mkdir()

        root = build_tree(tmp)
        assert root.directive == "Empty project"
        assert root.global_best_experiment is None

        output = render_terminal(root, color=False)
        assert "Empty project" in output


def test_metric_override():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _setup_project(tmp)
        # Override metric — both campaigns have "score" so this works
        root = build_tree(tmp, metric_override="score")
        assert root.global_best_metric == "score"


def test_top_n_limits_experiments():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _setup_project(tmp)
        root = build_tree(tmp, top_n=2)

        # camp_a has 3 completed but top_n=2 should limit display
        q1 = root.questions[0]
        assert len(q1.campaigns[0].experiments) == 2
