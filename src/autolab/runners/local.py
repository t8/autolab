"""Local runner — executes experiments as subprocesses."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from ..core.experiment import RunResult
from .base import RunnerBase


class LocalRunner(RunnerBase):
    """Runs experiments as local subprocesses.

    Parameters are injected into the command template via str.format().
    """

    def __init__(
        self,
        command_template: str,
        working_dir: str = ".",
        timeout_seconds: int = 3600,
        env: dict[str, str] | None = None,
    ):
        self.command_template = command_template
        self.working_dir = working_dir
        self.timeout_seconds = timeout_seconds
        self.extra_env = env or {}

    def setup(self, experiment: dict[str, Any]) -> None:
        pass

    def run(self, experiment: dict[str, Any]) -> RunResult:
        cmd = self._build_command(experiment)
        env = {**os.environ, **self.extra_env, **self._param_env(experiment)}

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.working_dir,
                timeout=self.timeout_seconds,
                env=env,
            )
            return RunResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
                wall_time_s=time.monotonic() - t0,
            )
        except subprocess.TimeoutExpired as e:
            return RunResult(
                stdout=e.stdout or "" if isinstance(e.stdout, str) else (e.stdout or b"").decode(errors="replace"),
                stderr=f"Timeout after {self.timeout_seconds}s",
                returncode=-1,
                wall_time_s=time.monotonic() - t0,
            )

    def cleanup(self, experiment: dict[str, Any]) -> None:
        pass

    def _build_command(self, experiment: dict[str, Any]) -> str:
        try:
            return self.command_template.format(**experiment)
        except KeyError:
            return self.command_template

    def _param_env(self, experiment: dict[str, Any]) -> dict[str, str]:
        """Export experiment params as AUTOLAB_PARAM_* env vars."""
        env = {}
        for k, v in experiment.items():
            if k in ("name", "campaign_name"):
                continue
            env[f"AUTOLAB_PARAM_{k.upper()}"] = str(v)
        return env

    @classmethod
    def from_campaign_config(cls, runner_config: dict[str, Any]) -> LocalRunner:
        """Create a LocalRunner from a campaign's runner config."""
        return cls(
            command_template=runner_config.get("command", "echo 'no command'"),
            working_dir=runner_config.get("working_dir", "."),
            timeout_seconds=runner_config.get("timeout_seconds", 3600),
            env=runner_config.get("env"),
        )
