"""SSH runner — executes experiments on remote nodes via SSH/SCP.

Generalized from Rainier's fabric_ops.py. Works with any OS on the remote
side — command templates are user-provided, not hardcoded to Windows.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from ..core.experiment import RunResult
from .base import RunnerBase


class SSHRunner(RunnerBase):
    """Runs experiments on a remote host via SSH.

    Lifecycle:
    1. setup() — deploy files to the remote host via SCP
    2. run() — execute the command template via SSH (blocking)
    3. cleanup() — optionally run a cleanup command on the remote

    Parameters are injected into the command template via str.format().
    """

    def __init__(
        self,
        host: str,
        command_template: str,
        user: str | None = None,
        key_path: str | None = None,
        port: int = 22,
        deploy_files: list[tuple[str, str]] | None = None,
        working_dir: str | None = None,
        cleanup_command: str | None = None,
        timeout_seconds: int = 3600,
        connect_timeout: int = 10,
        ssh_options: list[str] | None = None,
    ):
        self.host = host
        self.command_template = command_template
        self.user = user or os.environ.get("USER", "root")
        self.key_path = key_path
        self.port = port
        self.deploy_files = deploy_files or []
        self.working_dir = working_dir
        self.cleanup_command = cleanup_command
        self.timeout_seconds = timeout_seconds
        self.connect_timeout = connect_timeout
        self.ssh_options = ssh_options or []

    def _ssh_base(self) -> list[str]:
        """Build the base SSH command prefix."""
        cmd = ["ssh"]
        if self.key_path:
            cmd.extend(["-i", self.key_path])
        cmd.extend([
            "-o", f"ConnectTimeout={self.connect_timeout}",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-p", str(self.port),
        ])
        cmd.extend(self.ssh_options)
        cmd.append(f"{self.user}@{self.host}")
        return cmd

    def _scp_base(self) -> list[str]:
        """Build the base SCP command prefix."""
        cmd = ["scp"]
        if self.key_path:
            cmd.extend(["-i", self.key_path])
        cmd.extend([
            "-o", f"ConnectTimeout={self.connect_timeout}",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-P", str(self.port),
        ])
        return cmd

    def ssh_run(self, command: str, timeout: int | None = None) -> subprocess.CompletedProcess:
        """Run a command on the remote host via SSH."""
        full_cmd = [*self._ssh_base(), command]
        return subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout or self.timeout_seconds,
        )

    def scp_upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file to the remote host via SCP."""
        dest = f"{self.user}@{self.host}:{remote_path}"
        cmd = [*self._scp_base(), local_path, dest]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"SCP to {self.host}:{remote_path} failed: {result.stderr}")

    def scp_download(self, remote_path: str, local_path: str) -> None:
        """Download a file from the remote host via SCP."""
        src = f"{self.user}@{self.host}:{remote_path}"
        cmd = [*self._scp_base(), src, local_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"SCP from {self.host}:{remote_path} failed: {result.stderr}")

    def setup(self, experiment: dict[str, Any]) -> None:
        """Deploy configured files to the remote host."""
        for local_path, remote_path in self.deploy_files:
            try:
                expanded_remote = remote_path.format(**experiment)
            except KeyError:
                expanded_remote = remote_path
            self.scp_upload(local_path, expanded_remote)

    def run(self, experiment: dict[str, Any]) -> RunResult:
        """Execute the experiment command on the remote host."""
        cmd = self._build_command(experiment)
        if self.working_dir:
            try:
                wd = self.working_dir.format(**experiment)
            except KeyError:
                wd = self.working_dir
            cmd = f"cd {wd} && {cmd}"

        t0 = time.monotonic()
        try:
            result = self.ssh_run(cmd, timeout=self.timeout_seconds)
            return RunResult(
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                wall_time_s=time.monotonic() - t0,
            )
        except subprocess.TimeoutExpired as e:
            stdout = ""
            if e.stdout:
                stdout = e.stdout if isinstance(e.stdout, str) else e.stdout.decode(errors="replace")
            return RunResult(
                stdout=stdout,
                stderr=f"SSH timeout after {self.timeout_seconds}s",
                returncode=-1,
                wall_time_s=time.monotonic() - t0,
            )

    def cleanup(self, experiment: dict[str, Any]) -> None:
        """Run cleanup command on the remote host if configured."""
        if self.cleanup_command:
            try:
                cmd = self.cleanup_command.format(**experiment)
            except KeyError:
                cmd = self.cleanup_command
            try:
                self.ssh_run(cmd, timeout=30)
            except (subprocess.TimeoutExpired, Exception):
                pass  # best-effort

    def _build_command(self, experiment: dict[str, Any]) -> str:
        try:
            return self.command_template.format(**experiment)
        except KeyError:
            return self.command_template

    def wait_for_port(self, port: int, timeout: int = 60) -> bool:
        """Poll until a TCP port is listening on the remote host.

        Works cross-platform: tries ss, then netstat, then nc.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                # Try ss first (Linux), then netstat (universal), then nc
                for check_cmd in [
                    f"ss -tln | grep ':{port} '",
                    f"netstat -tln | grep ':{port} '",
                    f"nc -z localhost {port}",
                ]:
                    result = self.ssh_run(check_cmd, timeout=10)
                    if result.returncode == 0:
                        return True
            except (subprocess.TimeoutExpired, Exception):
                pass
            time.sleep(2)
        return False

    @classmethod
    def from_campaign_config(cls, runner_config: dict[str, Any]) -> SSHRunner:
        """Create an SSHRunner from a campaign's runner config."""
        deploy = runner_config.get("deploy_files", [])
        deploy_tuples = [(d["local"], d["remote"]) for d in deploy] if deploy else []

        return cls(
            host=runner_config["host"],
            command_template=runner_config.get("command", "echo 'no command'"),
            user=runner_config.get("user"),
            key_path=runner_config.get("key_path"),
            port=runner_config.get("port", 22),
            deploy_files=deploy_tuples,
            working_dir=runner_config.get("working_dir"),
            cleanup_command=runner_config.get("cleanup_command"),
            timeout_seconds=runner_config.get("timeout_seconds", 3600),
            connect_timeout=runner_config.get("connect_timeout", 10),
            ssh_options=runner_config.get("ssh_options", []),
        )
