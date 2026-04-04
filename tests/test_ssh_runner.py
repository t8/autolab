"""Tests for SSH runner — unit tests that don't require actual SSH access."""

from __future__ import annotations

from autolab.runners.ssh import SSHRunner


def test_ssh_base_command():
    runner = SSHRunner(
        host="192.168.1.100",
        command_template="echo test",
        user="researcher",
        key_path="/home/user/.ssh/id_ed25519",
        port=2222,
    )
    base = runner._ssh_base()
    assert "ssh" in base[0]
    assert "-i" in base
    assert "/home/user/.ssh/id_ed25519" in base
    assert "-p" in base
    assert "2222" in base
    assert "researcher@192.168.1.100" in base


def test_scp_base_command():
    runner = SSHRunner(
        host="server.lab",
        command_template="echo test",
        user="admin",
        key_path="/keys/lab",
        port=22,
    )
    base = runner._scp_base()
    assert "scp" in base[0]
    assert "-i" in base
    assert "/keys/lab" in base


def test_build_command_with_params():
    runner = SSHRunner(
        host="host",
        command_template="python train.py --lr {lr} --bs {batch_size}",
    )
    cmd = runner._build_command({"lr": 0.001, "batch_size": 32})
    assert cmd == "python train.py --lr 0.001 --bs 32"


def test_build_command_missing_param():
    runner = SSHRunner(
        host="host",
        command_template="echo {missing_param}",
    )
    cmd = runner._build_command({"other": "val"})
    assert cmd == "echo {missing_param}"  # falls back to raw template


def test_from_campaign_config():
    config = {
        "backend": "ssh",
        "host": "gpu-server.lab",
        "user": "researcher",
        "key_path": "~/.ssh/lab_key",
        "port": 22,
        "command": "python train.py --lr {lr}",
        "working_dir": "/home/researcher/experiments",
        "cleanup_command": "rm -f /tmp/experiment_*",
        "timeout_seconds": 7200,
        "deploy_files": [
            {"local": "train.py", "remote": "/home/researcher/train.py"},
            {"local": "config.yaml", "remote": "/home/researcher/config.yaml"},
        ],
    }
    runner = SSHRunner.from_campaign_config(config)
    assert runner.host == "gpu-server.lab"
    assert runner.user == "researcher"
    assert runner.key_path == "~/.ssh/lab_key"
    assert runner.timeout_seconds == 7200
    assert len(runner.deploy_files) == 2
    assert runner.cleanup_command == "rm -f /tmp/experiment_*"
    assert runner.working_dir == "/home/researcher/experiments"


def test_from_campaign_config_minimal():
    config = {
        "backend": "ssh",
        "host": "server",
        "command": "echo hi",
    }
    runner = SSHRunner.from_campaign_config(config)
    assert runner.host == "server"
    assert runner.deploy_files == []
    assert runner.cleanup_command is None


def test_ssh_options():
    runner = SSHRunner(
        host="host",
        command_template="echo test",
        ssh_options=["-o", "ProxyJump=bastion"],
    )
    base = runner._ssh_base()
    assert "-o" in base
    assert "ProxyJump=bastion" in base
