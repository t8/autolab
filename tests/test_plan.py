"""Tests for research plan management."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from autolab.core.plan import ResearchPlan


def _make_plan(tmp: Path, questions: list[dict] | None = None) -> ResearchPlan:
    plan_data = {
        "directive": "Test research goal",
        "status": "active",
        "questions": questions or [],
    }
    (tmp / "research_plan.yaml").write_text(yaml.dump(plan_data))
    return ResearchPlan(tmp)


class TestResearchPlan:
    def test_load_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = ResearchPlan(tmp)
            data = plan.load()
            assert data["questions"] == []

    def test_add_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp)
            q = plan.add_question("q1", "What is the effect of X?", priority="high")
            assert q.id == "q1"
            assert q.status == "active"
            assert q.priority == "high"

            questions = plan.get_questions()
            assert len(questions) == 1

    def test_add_duplicate_question_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp)
            plan.add_question("q1", "First")
            try:
                plan.add_question("q1", "Duplicate")
                assert False, "Should have raised"
            except ValueError:
                pass

    def test_get_active_questions_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp, [
                {"id": "q1", "text": "Low", "status": "active", "priority": "low"},
                {"id": "q2", "text": "High", "status": "active", "priority": "high"},
                {"id": "q3", "text": "Med", "status": "active", "priority": "medium"},
                {"id": "q4", "text": "Done", "status": "answered", "priority": "high"},
            ])
            active = plan.get_active_questions()
            assert len(active) == 3
            assert active[0].id == "q2"  # high first
            assert active[1].id == "q3"  # medium
            assert active[2].id == "q1"  # low

    def test_answer_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp, [
                {"id": "q1", "text": "Test?", "status": "active", "priority": "high"},
            ])
            q = plan.answer_question("q1", "Yes, confirmed by experiments")
            assert q.status == "answered"
            assert q.finding == "Yes, confirmed by experiments"

            reloaded = plan.get_question("q1")
            assert reloaded.is_answered

    def test_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp, [
                {"id": "q1", "text": "First", "status": "active", "priority": "high"},
                {"id": "q2", "text": "Depends on q1", "status": "active",
                 "priority": "high", "depends_on": ["q1"]},
            ])
            blocked = plan.get_blocked_questions()
            assert len(blocked) == 1
            assert blocked[0].id == "q2"

            runnable = plan.get_runnable_questions()
            assert len(runnable) == 1
            assert runnable[0].id == "q1"

    def test_dependencies_satisfied(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp, [
                {"id": "q1", "text": "First", "status": "answered", "priority": "high",
                 "finding": "Done"},
                {"id": "q2", "text": "Depends on q1", "status": "active",
                 "priority": "high", "depends_on": ["q1"]},
            ])
            blocked = plan.get_blocked_questions()
            assert len(blocked) == 0

            runnable = plan.get_runnable_questions()
            assert len(runnable) == 1
            assert runnable[0].id == "q2"

    def test_add_campaign_to_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp, [
                {"id": "q1", "text": "Test", "status": "active", "priority": "high"},
            ])
            plan.add_campaign_to_question("q1", "batch_sweep")
            plan.add_campaign_to_question("q1", "lr_sweep")
            plan.add_campaign_to_question("q1", "batch_sweep")  # duplicate — no-op

            q = plan.get_question("q1")
            assert q.campaigns == ["batch_sweep", "lr_sweep"]

    def test_spawn_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp, [
                {"id": "q1", "text": "Parent", "status": "active", "priority": "high"},
            ])
            child = plan.spawn_question("q1", "q1a", "Sub-question of q1")
            assert child.id == "q1a"
            assert child.depends_on == ["q1"]

            parent = plan.get_question("q1")
            assert "q1a" in parent.spawned

    def test_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp, [
                {"id": "q1", "text": "A", "status": "active", "priority": "high"},
                {"id": "q2", "text": "B", "status": "answered", "priority": "medium"},
                {"id": "q3", "text": "C", "status": "abandoned", "priority": "low"},
            ])
            s = plan.summary()
            assert s["total_questions"] == 3
            assert s["active"] == 1
            assert s["answered"] == 1
            assert s["abandoned"] == 1

    def test_directive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plan = _make_plan(tmp)
            assert plan.directive == "Test research goal"
