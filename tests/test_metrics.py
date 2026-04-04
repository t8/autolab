"""Tests for metric collectors and results DB."""

import tempfile
from pathlib import Path

from autolab.metrics.collectors import StdoutCollector, FileCollector
from autolab.metrics.db import ResultsDB


def test_stdout_collector_basic():
    collector = StdoutCollector([
        {"name": "throughput", "pattern": r"Throughput: ([\d.]+)", "type": "float"},
        {"name": "loss", "pattern": r"Loss: ([\d.]+)", "type": "float"},
        {"name": "epochs", "pattern": r"Epochs: (\d+)", "type": "int"},
    ])
    stdout = "Throughput: 123.45 samples/sec\nLoss: 0.0023\nEpochs: 10"
    metrics = collector.collect(stdout)
    assert metrics["throughput"] == 123.45
    assert metrics["loss"] == 0.0023
    assert metrics["epochs"] == 10


def test_stdout_collector_missing_metric():
    collector = StdoutCollector([
        {"name": "throughput", "pattern": r"Throughput: ([\d.]+)"},
        {"name": "missing", "pattern": r"NotHere: ([\d.]+)"},
    ])
    metrics = collector.collect("Throughput: 42.0")
    assert metrics["throughput"] == 42.0
    assert "missing" not in metrics


def test_stdout_collector_from_campaign_config():
    config = {
        "primary": "throughput",
        "direction": "maximize",
        "collect": [
            {"name": "throughput", "pattern": r"T: ([\d.]+)", "type": "float"},
        ],
    }
    collector = StdoutCollector.from_campaign_config(config)
    metrics = collector.collect("T: 99.9")
    assert metrics["throughput"] == 99.9


def test_file_collector_json():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "metrics.json"
        p.write_text('{"accuracy": 0.95, "f1": 0.92}')
        collector = FileCollector(str(p))
        metrics = collector.collect()
        assert metrics["accuracy"] == 0.95
        assert metrics["f1"] == 0.92


def test_file_collector_missing():
    collector = FileCollector("/nonexistent/path.json")
    metrics = collector.collect()
    assert metrics == {}


class TestResultsDB:
    def test_store_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = ResultsDB(Path(tmp) / "test.db")
            run_id = db.store_result({
                "experiment_name": "exp1",
                "campaign_name": "camp1",
                "config": {"lr": 0.01},
                "metrics": {"loss": 0.5, "acc": 0.9},
                "status": "completed",
                "wall_time_s": 10.0,
            })
            assert "exp1" in run_id

            history = db.load_history("camp1")
            assert len(history) == 1
            assert history[0]["metrics"]["loss"] == 0.5
            assert history[0]["config"]["lr"] == 0.01

    def test_count_experiments(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = ResultsDB(Path(tmp) / "test.db")
            for i in range(5):
                db.store_result({
                    "experiment_name": f"exp{i}",
                    "campaign_name": "camp1",
                    "metrics": {"score": i * 10},
                    "status": "completed",
                })
            assert db.count_experiments() == 5
            assert db.count_experiments("camp1") == 5
            assert db.count_experiments("camp2") == 0

    def test_best_by_metric(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = ResultsDB(Path(tmp) / "test.db")
            for score in [10, 50, 30, 20, 40]:
                db.store_result({
                    "experiment_name": f"exp_s{score}",
                    "campaign_name": "camp1",
                    "metrics": {"score": score},
                    "status": "completed",
                })
            best = db.best_by_metric("score", "maximize", limit=3)
            assert len(best) == 3
            assert best[0]["metric_value"] == 50.0

    def test_campaign_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = ResultsDB(Path(tmp) / "test.db")
            db.store_result({
                "experiment_name": "ok",
                "campaign_name": "c1",
                "metrics": {},
                "status": "completed",
            })
            db.store_result({
                "experiment_name": "fail",
                "campaign_name": "c1",
                "metrics": {},
                "status": "failed",
            })
            summary = db.campaign_summary("c1")
            assert summary["total"] == 2
            assert summary["completed"] == 1
            assert summary["failed"] == 1

    def test_load_history_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = ResultsDB(Path(tmp) / "test.db")
            db.store_result({
                "experiment_name": "a",
                "campaign_name": "c1",
                "metrics": {},
                "status": "completed",
            })
            db.store_result({
                "experiment_name": "b",
                "campaign_name": "c2",
                "metrics": {},
                "status": "completed",
            })
            all_history = db.load_history()
            assert len(all_history) == 2
