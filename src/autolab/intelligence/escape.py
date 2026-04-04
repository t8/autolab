"""Local minima detection and escape strategies.

Detects when the research loop is stuck and recommends escape strategies.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..metrics.db import ResultsDB
from ..state.project import ProjectState


@dataclass
class EscapeRecommendation:
    """A recommendation for escaping a local minimum."""
    strategy: str  # literature_search | devil_advocate | random_perturbation | new_question
    description: str
    prompt: str  # Instruction for the agent to follow


class EscapeDetector:
    """Detects when the research loop is stuck and suggests escape strategies."""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.state = ProjectState(project_dir)
        self.db = ResultsDB(self.project_dir / "results.db")

    def is_stuck(self, threshold: int = 3) -> bool:
        """Check if the research loop is stuck.

        Returns True if consecutive_no_improvement >= threshold.
        """
        state = self.state.load()
        return state.get("consecutive_no_improvement", 0) >= threshold

    def detect_plateau(self, metric_name: str, window: int = 10) -> bool:
        """Detect if a metric has plateaued across recent experiments.

        Returns True if the standard deviation of the last `window` values
        is less than 5% of the mean.
        """
        history = self.db.load_history()
        values = []
        for r in history[-window:]:
            val = r.get("metrics", {}).get(metric_name)
            if val is not None and isinstance(val, (int, float)):
                values.append(float(val))

        if len(values) < window // 2:
            return False

        mean = sum(values) / len(values)
        if mean == 0:
            return False

        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = variance ** 0.5
        cv = std / abs(mean)  # coefficient of variation

        return cv < 0.05

    def detect_diversity_collapse(self, window: int = 5) -> bool:
        """Detect if recent campaigns are all testing the same question.

        Returns True if the last `window` campaigns all target the same question.
        """
        history = self.db.load_history()
        recent_campaigns = []
        seen = set()
        for r in reversed(history):
            cname = r.get("campaign_name", "")
            if cname and cname not in seen:
                seen.add(cname)
                recent_campaigns.append(cname)
                if len(recent_campaigns) >= window:
                    break

        if len(recent_campaigns) < window:
            return False

        # Check if all campaigns share a common prefix (heuristic for same question)
        # A more precise check would use research_plan.yaml
        prefixes = set()
        for name in recent_campaigns:
            parts = name.split("_")
            if len(parts) >= 2:
                prefixes.add(parts[0])
            else:
                prefixes.add(name)

        return len(prefixes) <= 1

    def recommend_escape(self) -> EscapeRecommendation:
        """Recommend an escape strategy based on current state."""
        strategies = [
            EscapeRecommendation(
                strategy="literature_search",
                description="Search the literature for alternative approaches",
                prompt=(
                    "You have not improved on any metric for 3+ iterations. "
                    "Before designing your next campaign, search the web for "
                    "alternative approaches to your current research question. "
                    "Look for techniques you haven't tried yet. Document what you "
                    "find in the journal before proceeding."
                ),
            ),
            EscapeRecommendation(
                strategy="devil_advocate",
                description="Write a devil's advocate argument against current approach",
                prompt=(
                    "You have not improved on any metric for 3+ iterations. "
                    "Write a journal entry arguing that your current approach is "
                    "fundamentally wrong. What assumptions are you making that "
                    "might not hold? What would you do differently if you started "
                    "from scratch? Then design a campaign based on the opposite "
                    "of your current assumptions."
                ),
            ),
            EscapeRecommendation(
                strategy="random_perturbation",
                description="Design a campaign with random parameter values outside explored range",
                prompt=(
                    "You have not improved on any metric for 3+ iterations. "
                    "Design a moonshot campaign that explores parameter values "
                    "well outside the ranges you've tested so far. Use at least "
                    "2x the maximum values and 0.5x the minimum values you've "
                    "tried. The goal is to explore a completely different part "
                    "of the parameter space."
                ),
            ),
            EscapeRecommendation(
                strategy="new_question",
                description="Add a new research question and pivot",
                prompt=(
                    "You have not improved on any metric for 3+ iterations. "
                    "Step back from your current question and add a new research "
                    "question to research_plan.yaml that approaches the directive "
                    "from a completely different angle. Design a campaign for "
                    "this new question."
                ),
            ),
        ]

        return random.choice(strategies)

    def get_escape_prompt(self) -> str | None:
        """Get an escape prompt if stuck, or None if not stuck."""
        if not self.is_stuck():
            return None
        rec = self.recommend_escape()
        return rec.prompt
