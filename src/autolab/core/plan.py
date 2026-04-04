"""Research plan management — question decomposition and tracking."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml


class ResearchQuestion:
    """A single research question in the plan."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.text: str = data["text"]
        self.status: str = data.get("status", "active")
        self.priority: str = data.get("priority", "medium")
        self.campaigns: list[str] = data.get("campaigns", [])
        self.finding: str = data.get("finding", "")
        self.spawned: list[str] = data.get("spawned", [])
        self.depends_on: list[str] = data.get("depends_on", [])

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "status": self.status,
            "priority": self.priority,
        }
        if self.campaigns:
            d["campaigns"] = self.campaigns
        if self.finding:
            d["finding"] = self.finding
        if self.spawned:
            d["spawned"] = self.spawned
        if self.depends_on:
            d["depends_on"] = self.depends_on
        return d

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_answered(self) -> bool:
        return self.status == "answered"

    @property
    def priority_score(self) -> int:
        return {"high": 3, "medium": 2, "low": 1}.get(self.priority, 2)


class ResearchPlan:
    """Manages research_plan.yaml — question decomposition and status tracking."""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.plan_path = self.project_dir / "research_plan.yaml"

    def load(self) -> dict[str, Any]:
        """Load the research plan from disk."""
        if not self.plan_path.exists():
            return {"directive": "", "status": "active", "questions": []}
        return yaml.safe_load(self.plan_path.read_text()) or {}

    def save(self, plan: dict[str, Any]) -> None:
        """Save the research plan to disk."""
        self.plan_path.write_text(yaml.dump(plan, default_flow_style=False, sort_keys=False))

    @property
    def directive(self) -> str:
        return self.load().get("directive", "")

    def get_questions(self) -> list[ResearchQuestion]:
        """Get all research questions."""
        plan = self.load()
        return [ResearchQuestion(q) for q in plan.get("questions", [])]

    def get_question(self, question_id: str) -> Optional[ResearchQuestion]:
        """Get a specific question by ID."""
        for q in self.get_questions():
            if q.id == question_id:
                return q
        return None

    def get_active_questions(self) -> list[ResearchQuestion]:
        """Get all active questions, sorted by priority (high first)."""
        active = [q for q in self.get_questions() if q.is_active]
        return sorted(active, key=lambda q: q.priority_score, reverse=True)

    def get_blocked_questions(self) -> list[ResearchQuestion]:
        """Get questions whose dependencies aren't yet answered."""
        questions = {q.id: q for q in self.get_questions()}
        blocked = []
        for q in questions.values():
            if q.status != "active":
                continue
            for dep_id in q.depends_on:
                dep = questions.get(dep_id)
                if dep and not dep.is_answered:
                    blocked.append(q)
                    break
        return blocked

    def get_runnable_questions(self) -> list[ResearchQuestion]:
        """Get active questions with all dependencies satisfied."""
        blocked_ids = {q.id for q in self.get_blocked_questions()}
        return [
            q for q in self.get_active_questions()
            if q.id not in blocked_ids
        ]

    def add_question(
        self,
        question_id: str,
        text: str,
        priority: str = "medium",
        depends_on: list[str] | None = None,
    ) -> ResearchQuestion:
        """Add a new research question."""
        plan = self.load()
        questions = plan.get("questions", [])

        if any(q["id"] == question_id for q in questions):
            raise ValueError(f"Question {question_id} already exists")

        q_data = {
            "id": question_id,
            "text": text,
            "status": "active",
            "priority": priority,
        }
        if depends_on:
            q_data["depends_on"] = depends_on

        questions.append(q_data)
        plan["questions"] = questions
        self.save(plan)
        return ResearchQuestion(q_data)

    def update_question(self, question_id: str, **updates: Any) -> Optional[ResearchQuestion]:
        """Update fields on a question."""
        plan = self.load()
        questions = plan.get("questions", [])
        for q in questions:
            if q["id"] == question_id:
                q.update(updates)
                plan["questions"] = questions
                self.save(plan)
                return ResearchQuestion(q)
        return None

    def answer_question(self, question_id: str, finding: str) -> Optional[ResearchQuestion]:
        """Mark a question as answered with a finding."""
        return self.update_question(question_id, status="answered", finding=finding)

    def add_campaign_to_question(self, question_id: str, campaign_name: str) -> None:
        """Link a campaign to a question."""
        plan = self.load()
        for q in plan.get("questions", []):
            if q["id"] == question_id:
                campaigns = q.get("campaigns", [])
                if campaign_name not in campaigns:
                    campaigns.append(campaign_name)
                    q["campaigns"] = campaigns
                    self.save(plan)
                return
        raise ValueError(f"Question {question_id} not found")

    def spawn_question(
        self,
        parent_id: str,
        child_id: str,
        text: str,
        priority: str = "medium",
    ) -> ResearchQuestion:
        """Spawn a sub-question from a parent question."""
        plan = self.load()
        for q in plan.get("questions", []):
            if q["id"] == parent_id:
                spawned = q.get("spawned", [])
                if child_id not in spawned:
                    spawned.append(child_id)
                    q["spawned"] = spawned
                break

        child = self.add_question(child_id, text, priority, depends_on=[parent_id])
        self.save(plan)
        return child

    def summary(self) -> dict[str, Any]:
        """Get a summary of the research plan status."""
        questions = self.get_questions()
        return {
            "directive": self.directive,
            "total_questions": len(questions),
            "active": sum(1 for q in questions if q.status == "active"),
            "answered": sum(1 for q in questions if q.status == "answered"),
            "blocked": len(self.get_blocked_questions()),
            "abandoned": sum(1 for q in questions if q.status == "abandoned"),
        }
