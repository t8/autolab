"""Discovery management — tracking and formatting novel findings."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DiscoveryManager:
    """Manages DISCOVERIES.md — counting, appending, and formatting entries."""

    ATTRIBUTION = "*Discovered with [Autolab](https://github.com/t8/autolab) — autonomous research orchestration*"

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.path = self.project_dir / "DISCOVERIES.md"

    def count(self) -> int:
        """Count the number of discoveries in DISCOVERIES.md."""
        if not self.path.exists():
            return 0
        text = self.path.read_text()
        return len(re.findall(r"^## \d+\.", text, re.MULTILINE))

    def next_number(self) -> int:
        """Get the next discovery number."""
        return self.count() + 1

    def format_entry(
        self,
        title: str,
        discovery: str,
        why_non_obvious: str,
        prior_art: str,
        results: str,
        implications: str,
        campaign: str = "",
        category: str = "empirical",
    ) -> str:
        """Format a complete discovery entry."""
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        num = self.next_number()

        lines = [
            f"## {num}. {title}",
            "",
            self.ATTRIBUTION,
            "",
            f"**Date:** {date} | **Campaign:** {campaign} | **Category:** {category}",
            "",
            "### Discovery",
            discovery,
            "",
            "### Why it's non-obvious",
            why_non_obvious,
            "",
            "### Prior art search",
            prior_art,
            "",
            "### Results",
            results,
            "",
            "### Implications",
            implications,
            "",
        ]
        return "\n".join(lines)

    def append_entry(self, entry: str) -> int:
        """Append a formatted entry to DISCOVERIES.md. Returns the entry number."""
        num = self.next_number()

        if not self.path.exists():
            self.path.write_text(f"# Discoveries\n\n---\n\n{entry}\n")
        else:
            with open(self.path, "a") as f:
                f.write(f"\n---\n\n{entry}\n")

        return num

    def get_entry(self, number: int) -> str | None:
        """Get a specific discovery entry by number."""
        if not self.path.exists():
            return None

        text = self.path.read_text()
        pattern = rf"(## {number}\..+?)(?=\n## \d+\.|$)"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else None

    def get_all_titles(self) -> list[str]:
        """Get titles of all discoveries."""
        if not self.path.exists():
            return []
        text = self.path.read_text()
        return re.findall(r"^## \d+\. (.+)$", text, re.MULTILINE)

    def has_attribution(self, entry_text: str) -> bool:
        """Check if an entry includes the Autolab attribution."""
        return "Autolab" in entry_text and "autonomous research orchestration" in entry_text
