"""Campaign scheduler — advisory priority queue with moonshot ratio enforcement."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .campaign import Campaign
from .plan import ResearchPlan, ResearchQuestion
from ..metrics.db import ResultsDB
from ..state.project import ProjectState


class SchedulerRecommendation:
    """A ranked campaign recommendation with rationale."""

    def __init__(self, campaign_path: str, score: float, rationale: str):
        self.campaign_path = campaign_path
        self.score = score
        self.rationale = rationale

    def __repr__(self) -> str:
        return f"Recommendation({self.campaign_path}, score={self.score:.1f}, {self.rationale})"


class CampaignScheduler:
    """Advisory scheduler that ranks campaigns by priority, diversity, and moonshot ratio.

    The agent (Claude/GPT) sees the ranked list and makes the final call.
    This is advisory, not mandatory.
    """

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.plan = ResearchPlan(project_dir)
        self.state = ProjectState(project_dir)
        self.db = ResultsDB(self.project_dir / "results.db")

    def get_moonshot_config(self) -> dict[str, Any]:
        """Load moonshot strategy config from autolab.yaml."""
        config = self.state.load_config()
        strategy = config.get("strategy", {})
        return {
            "ratio": strategy.get("moonshot_ratio", 0.5),
            "enforce": strategy.get("enforce", "soft"),
            "definition": strategy.get("moonshot_definition", ""),
        }

    def current_moonshot_ratio(self) -> float:
        """Calculate the current moonshot/total campaign ratio."""
        state = self.state.load()
        moonshot = state.get("moonshot_count", 0)
        non_moonshot = state.get("non_moonshot_count", 0)
        total = moonshot + non_moonshot
        if total == 0:
            return 0.0
        return moonshot / total

    def moonshot_deficit(self) -> float:
        """How far below the target moonshot ratio we are. Positive = need more moonshots."""
        config = self.get_moonshot_config()
        target = config["ratio"]
        current = self.current_moonshot_ratio()
        return target - current

    def rank_campaigns(self, campaign_paths: list[str | Path]) -> list[SchedulerRecommendation]:
        """Rank a list of campaign files by priority.

        Scoring factors:
        1. Question priority (high=30, medium=20, low=10)
        2. Dependency bonus (deps newly satisfied = +15)
        3. Diversity bonus (question not recently tested = +10)
        4. Moonshot bonus/penalty (based on ratio deficit)
        5. Efficiency bonus (fewer experiments = +5 when near targets)
        """
        runnable_ids = {q.id for q in self.plan.get_runnable_questions()}
        history = self.db.load_history()
        recent_questions = self._recent_question_ids(history, window=5)
        moonshot_gap = self.moonshot_deficit()

        recommendations = []
        for path in campaign_paths:
            try:
                campaign = Campaign(path)
            except Exception:
                continue

            score = 0.0
            rationale_parts = []

            # 1. Question priority
            question = self.plan.get_question(campaign.question) if campaign.question else None
            if question:
                score += question.priority_score * 10
                rationale_parts.append(f"priority={question.priority}")

                # 2. Dependency bonus
                if question.id in runnable_ids and question.depends_on:
                    score += 15
                    rationale_parts.append("deps-satisfied")

                # 3. Diversity bonus
                if question.id not in recent_questions:
                    score += 10
                    rationale_parts.append("diverse")
            else:
                score += 20  # no question linked — medium priority default
                rationale_parts.append("no-question")

            # 4. Moonshot ratio
            if campaign.moonshot and moonshot_gap > 0:
                score += moonshot_gap * 30  # bonus for needed moonshots
                rationale_parts.append(f"moonshot-needed(gap={moonshot_gap:.0%})")
            elif not campaign.moonshot and moonshot_gap > 0.2:
                score -= 10  # penalty for non-moonshot when ratio is way off
                rationale_parts.append("moonshot-deficit")

            # 5. Efficiency (fewer experiments when near targets)
            state = self.state.load()
            config = self.state.load_config()
            exp_target = config.get("targets", {}).get("min_experiments", 0)
            if exp_target > 0:
                progress = state.get("total_experiments_run", 0) / exp_target
                if progress > 0.8 and campaign.experiment_count() <= 10:
                    score += 5
                    rationale_parts.append("efficient")

            rationale = ", ".join(rationale_parts) or "default"
            recommendations.append(SchedulerRecommendation(str(path), score, rationale))

        recommendations.sort(key=lambda r: r.score, reverse=True)
        return recommendations

    def next_campaign(self, campaign_paths: list[str | Path]) -> Optional[SchedulerRecommendation]:
        """Get the top-ranked campaign recommendation."""
        ranked = self.rank_campaigns(campaign_paths)
        if not ranked:
            return None

        # Hard enforcement: if moonshot ratio requires it, pick first moonshot
        config = self.get_moonshot_config()
        if config["enforce"] == "hard" and self.moonshot_deficit() > 0:
            for r in ranked:
                try:
                    c = Campaign(r.campaign_path)
                    if c.moonshot:
                        return r
                except Exception:
                    continue

        return ranked[0] if ranked else None

    def check_moonshot_warning(self) -> Optional[str]:
        """Return a warning string if moonshot ratio is below target, None otherwise."""
        gap = self.moonshot_deficit()
        if gap <= 0:
            return None
        config = self.get_moonshot_config()
        current = self.current_moonshot_ratio()
        target = config["ratio"]
        return (
            f"Moonshot ratio is {current:.0%}, target is {target:.0%}. "
            f"Consider running more moonshot campaigns."
        )

    def _recent_question_ids(self, history: list[dict], window: int = 5) -> set[str]:
        """Get question IDs from recently run campaigns."""
        recent_campaigns = set()
        for r in history[-window * 10:]:  # look at last N*10 experiments
            cname = r.get("campaign_name", "")
            if cname:
                recent_campaigns.add(cname)

        # Map campaigns to questions via plan
        question_ids = set()
        for q in self.plan.get_questions():
            for cname in q.campaigns:
                if cname in recent_campaigns:
                    question_ids.add(q.id)
        return question_ids
