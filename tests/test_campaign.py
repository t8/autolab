"""Tests for campaign grid expansion and sequencing."""

import tempfile
from pathlib import Path

import yaml

from autolab.core.campaign import Campaign


def _write_campaign(tmp: Path, config: dict) -> Path:
    path = tmp / "campaign.yaml"
    path.write_text(yaml.dump(config))
    return path


def test_grid_expansion():
    """Cartesian product of grid params produces correct number of experiments."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "test_sweep",
            "hypothesis": "Testing grid expansion",
            "grid": {
                "lr": [0.01, 0.001],
                "batch_size": [16, 32, 64],
            },
            "defaults": {"epochs": 10},
            "runner": {"backend": "local", "command": "echo test"},
            "metrics": {"primary": "loss", "direction": "minimize"},
        })
        campaign = Campaign(path)
        exps = campaign.get_all_experiments()
        assert len(exps) == 6  # 2 * 3


def test_experiment_names_unique():
    """Each experiment gets a unique name."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "test",
            "grid": {"x": [1, 2, 3], "y": ["a", "b"]},
            "runner": {"backend": "local", "command": "echo test"},
        })
        campaign = Campaign(path)
        names = [e["name"] for e in campaign.get_all_experiments()]
        assert len(names) == len(set(names))


def test_defaults_merged():
    """Default params are present in each experiment."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "test",
            "defaults": {"seed": 42, "epochs": 5},
            "grid": {"lr": [0.01]},
            "runner": {"backend": "local", "command": "echo test"},
        })
        campaign = Campaign(path)
        exp = campaign.get_all_experiments()[0]
        assert exp["seed"] == 42
        assert exp["epochs"] == 5
        assert exp["lr"] == 0.01


def test_get_next_experiment():
    """get_next_experiment skips already-run experiments."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "test",
            "grid": {"x": [1, 2, 3]},
            "runner": {"backend": "local", "command": "echo test"},
        })
        campaign = Campaign(path)
        exps = campaign.get_all_experiments()

        # No history — returns first
        nxt = campaign.get_next_experiment([])
        assert nxt["name"] == exps[0]["name"]

        # First done — returns second
        history = [{"experiment_name": exps[0]["name"]}]
        nxt = campaign.get_next_experiment(history)
        assert nxt["name"] == exps[1]["name"]

        # All done — returns None
        history = [{"experiment_name": e["name"]} for e in exps]
        nxt = campaign.get_next_experiment(history)
        assert nxt is None


def test_diminishing_returns_not_triggered_early():
    """Diminishing returns needs enough history."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "test",
            "grid": {"x": [1, 2, 3, 4, 5]},
            "runner": {"backend": "local", "command": "echo test"},
            "metrics": {"primary": "score", "direction": "maximize"},
            "stopping": {"window": 3, "threshold": 0.05},
        })
        campaign = Campaign(path)
        # Too few results
        history = [
            {"experiment_name": "test_x=1", "status": "completed", "metrics": {"score": 10}},
        ]
        assert campaign.check_diminishing_returns(history) is False


def test_diminishing_returns_triggered():
    """Diminishing returns triggers when recent results plateau."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "test",
            "grid": {"x": [1, 2, 3, 4, 5]},
            "runner": {"backend": "local", "command": "echo test"},
            "metrics": {"primary": "score", "direction": "maximize"},
            "stopping": {"window": 3, "threshold": 0.05},
        })
        campaign = Campaign(path)
        # 5 results, last 3 within 5% of best
        history = [
            {"experiment_name": "test_x=1", "status": "completed", "metrics": {"score": 10}},
            {"experiment_name": "test_x=2", "status": "completed", "metrics": {"score": 100}},
            {"experiment_name": "test_x=3", "status": "completed", "metrics": {"score": 99}},
            {"experiment_name": "test_x=4", "status": "completed", "metrics": {"score": 98}},
            {"experiment_name": "test_x=5", "status": "completed", "metrics": {"score": 97}},
        ]
        assert campaign.check_diminishing_returns(history) is True


def test_best_result_maximize():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "test",
            "grid": {"x": [1, 2]},
            "runner": {"backend": "local", "command": "echo test"},
            "metrics": {"primary": "score", "direction": "maximize"},
        })
        campaign = Campaign(path)
        history = [
            {"metrics": {"score": 5}},
            {"metrics": {"score": 15}},
            {"metrics": {"score": 10}},
        ]
        best = campaign.best_result(history)
        assert best["metrics"]["score"] == 15


def test_best_result_minimize():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "test",
            "grid": {"x": [1, 2]},
            "runner": {"backend": "local", "command": "echo test"},
            "metrics": {"primary": "loss", "direction": "minimize"},
        })
        campaign = Campaign(path)
        history = [
            {"metrics": {"loss": 5}},
            {"metrics": {"loss": 1}},
            {"metrics": {"loss": 3}},
        ]
        best = campaign.best_result(history)
        assert best["metrics"]["loss"] == 1


def test_get_command():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "test",
            "grid": {"lr": [0.01], "bs": [32]},
            "runner": {
                "backend": "local",
                "command": "python train.py --lr {lr} --bs {bs}",
            },
        })
        campaign = Campaign(path)
        exp = campaign.get_all_experiments()[0]
        cmd = campaign.get_command(exp)
        assert cmd == "python train.py --lr 0.01 --bs 32"


def test_empty_grid():
    """Campaign with no grid produces one experiment."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "single",
            "runner": {"backend": "local", "command": "echo test"},
        })
        campaign = Campaign(path)
        assert campaign.experiment_count() == 1


def test_moonshot_flag():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_campaign(Path(tmp), {
            "name": "moonshot_test",
            "moonshot": True,
            "grid": {"x": [1]},
            "runner": {"backend": "local", "command": "echo test"},
        })
        campaign = Campaign(path)
        assert campaign.moonshot is True
