"""Git integration — auto-commit after research iterations."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitOps:
    """Helpers for git operations in the research project."""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)

    def is_git_repo(self) -> bool:
        """Check if the project directory is a git repository."""
        return (self.project_dir / ".git").exists()

    def init(self) -> bool:
        """Initialize a git repo if one doesn't exist. Returns True if created."""
        if self.is_git_repo():
            return False
        self._run("git init")
        return True

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        result = self._run("git status --porcelain")
        return bool(result.strip())

    def commit_iteration(self, iteration: int, summary: str) -> str | None:
        """Stage all changes and commit with a research message.

        Returns the commit hash, or None if nothing to commit.
        """
        if not self.is_git_repo():
            return None
        if not self.has_changes():
            return None

        self._run("git add -A")
        message = f"research: iteration {iteration} — {summary}"
        self._run(f'git commit -m "{message}"')

        result = self._run("git rev-parse --short HEAD")
        return result.strip() or None

    def log(self, n: int = 20) -> str:
        """Get recent commit log."""
        if not self.is_git_repo():
            return "(not a git repository)"
        return self._run(f"git log --oneline -{n}")

    def _run(self, cmd: str) -> str:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=30,
            )
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""
