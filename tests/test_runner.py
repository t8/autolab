"""Tests for runner abstraction and local runner."""

from autolab.runners.local import LocalRunner
from autolab.metrics.collectors import StdoutCollector


def test_local_runner_echo():
    runner = LocalRunner(
        command_template="echo 'Score: 42.5'",
        working_dir=".",
    )
    result = runner.run({})
    assert result.returncode == 0
    assert "Score: 42.5" in result.stdout
    assert result.wall_time_s > 0


def test_local_runner_param_injection():
    runner = LocalRunner(
        command_template="echo 'lr={lr} bs={bs}'",
        working_dir=".",
    )
    result = runner.run({"lr": 0.01, "bs": 32, "name": "test", "campaign_name": "c"})
    assert result.returncode == 0
    assert "lr=0.01" in result.stdout
    assert "bs=32" in result.stdout


def test_local_runner_execute_with_collector():
    runner = LocalRunner(
        command_template="echo 'Throughput: 99.5 samples/sec'",
        working_dir=".",
    )
    collector = StdoutCollector([
        {"name": "throughput", "pattern": r"Throughput: ([\d.]+)", "type": "float"},
    ])
    result = runner.execute(
        {"name": "test_exp", "campaign_name": "test_camp"},
        collector=collector,
    )
    assert result.status == "completed"
    assert result.metrics["throughput"] == 99.5
    assert result.experiment_name == "test_exp"


def test_local_runner_failure():
    runner = LocalRunner(
        command_template="exit 1",
        working_dir=".",
    )
    result = runner.execute(
        {"name": "fail_exp", "campaign_name": "test"},
    )
    assert result.status == "failed"


def test_local_runner_timeout():
    runner = LocalRunner(
        command_template="sleep 10",
        working_dir=".",
        timeout_seconds=1,
    )
    result = runner.run({"name": "timeout_test"})
    assert result.returncode == -1
    assert "Timeout" in result.stderr


def test_local_runner_from_config():
    runner = LocalRunner.from_campaign_config({
        "command": "echo hello",
        "working_dir": "/tmp",
        "timeout_seconds": 60,
    })
    assert runner.command_template == "echo hello"
    assert runner.working_dir == "/tmp"
    assert runner.timeout_seconds == 60


def test_local_runner_env_vars():
    runner = LocalRunner(
        command_template="env | grep AUTOLAB_PARAM",
        working_dir=".",
    )
    result = runner.run({"name": "t", "campaign_name": "c", "lr": 0.01, "bs": 32})
    assert "AUTOLAB_PARAM_LR=0.01" in result.stdout
    assert "AUTOLAB_PARAM_BS=32" in result.stdout
