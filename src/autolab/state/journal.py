"""Journal helpers — read/write JOURNAL.md."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Journal:
    """Helpers for reading and appending to JOURNAL.md."""

    def __init__(self, project_dir: str | Path):
        self.path = Path(project_dir) / "JOURNAL.md"

    def exists(self) -> bool:
        return self.path.exists()

    def read(self) -> str:
        """Read the full journal."""
        if not self.path.exists():
            return ""
        return self.path.read_text()

    def read_latest_iteration(self) -> str | None:
        """Read the most recent iteration entry."""
        text = self.read()
        parts = re.split(r"(?=^## Iteration \d+)", text, flags=re.MULTILINE)
        iterations = [p for p in parts if p.strip().startswith("## Iteration")]
        return iterations[-1].strip() if iterations else None

    def count_iterations(self) -> int:
        """Count the number of iteration entries."""
        text = self.read()
        return len(re.findall(r"^## Iteration \d+", text, re.MULTILINE))

    def append_iteration(
        self,
        iteration: int,
        summary: str,
        hypothesis: str = "",
        campaigns: list[dict[str, Any]] | None = None,
        learnings: list[str] | None = None,
        next_steps: list[str] | None = None,
    ) -> None:
        """Append a new iteration entry to the journal."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            f"\n## Iteration {iteration} — {now}\n",
            f"**Summary for operator:** {summary}\n",
        ]

        if hypothesis:
            lines.append(f"**Hypothesis:** {hypothesis}\n")

        if campaigns:
            lines.append("**Campaigns run:**")
            for c in campaigns:
                name = c.get("name", "unknown")
                count = c.get("experiments", 0)
                best = c.get("best", "N/A")
                lines.append(f"- {name}: {count} experiments, best = {best}")
            lines.append("")

        if learnings:
            lines.append("**Key learnings:**")
            for l in learnings:
                lines.append(f"- {l}")
            lines.append("")

        if next_steps:
            lines.append("**Next steps:**")
            for s in next_steps:
                lines.append(f"- {s}")
            lines.append("")

        lines.append("---\n")

        with open(self.path, "a") as f:
            f.write("\n".join(lines))
