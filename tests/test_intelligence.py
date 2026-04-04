"""Tests for the intelligence layer — escape detection, discovery management, literature, analysis."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from autolab.intelligence.escape import EscapeDetector
from autolab.intelligence.discovery import DiscoveryManager
from autolab.intelligence.literature import LiteratureSearch, PriorArtResult
from autolab.metrics.analysis import TrendAnalysis
from autolab.metrics.db import ResultsDB
from autolab.state.project import ProjectState


class TestEscapeDetector:
    def _setup(self, tmp: Path, no_improvement: int = 0):
        (tmp / ".autolab").mkdir(exist_ok=True)
        state = ProjectState(tmp)
        state.save({"consecutive_no_improvement": no_improvement})
        # Create a DB with some data
        db = ResultsDB(tmp / "results.db")
        return EscapeDetector(tmp)

    def test_not_stuck(self):
        with tempfile.TemporaryDirectory() as tmp:
            det = self._setup(Path(tmp), no_improvement=1)
            assert not det.is_stuck()

    def test_is_stuck(self):
        with tempfile.TemporaryDirectory() as tmp:
            det = self._setup(Path(tmp), no_improvement=3)
            assert det.is_stuck()

    def test_is_stuck_custom_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            det = self._setup(Path(tmp), no_improvement=5)
            assert not det.is_stuck(threshold=10)
            assert det.is_stuck(threshold=5)

    def test_recommend_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            det = self._setup(Path(tmp), no_improvement=5)
            rec = det.recommend_escape()
            assert rec.strategy in [
                "literature_search", "devil_advocate",
                "random_perturbation", "new_question",
            ]
            assert rec.prompt  # non-empty

    def test_get_escape_prompt_when_stuck(self):
        with tempfile.TemporaryDirectory() as tmp:
            det = self._setup(Path(tmp), no_improvement=3)
            prompt = det.get_escape_prompt()
            assert prompt is not None
            assert "improved" in prompt.lower() or "iterations" in prompt.lower()

    def test_get_escape_prompt_when_not_stuck(self):
        with tempfile.TemporaryDirectory() as tmp:
            det = self._setup(Path(tmp), no_improvement=0)
            assert det.get_escape_prompt() is None

    def test_detect_plateau(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = ResultsDB(tmp / "results.db")
            # All values nearly identical -> plateau
            for i in range(10):
                db.store_result({
                    "experiment_name": f"exp{i}",
                    "campaign_name": "test",
                    "metrics": {"score": 100.0 + (i * 0.1)},
                    "status": "completed",
                })
            (tmp / ".autolab").mkdir()
            ProjectState(tmp).save({})
            det = EscapeDetector(tmp)
            assert det.detect_plateau("score", window=10)

    def test_no_plateau_with_variance(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = ResultsDB(tmp / "results.db")
            for i, score in enumerate([10, 50, 20, 80, 30, 90, 15, 75, 40, 60]):
                db.store_result({
                    "experiment_name": f"exp{i}",
                    "campaign_name": "test",
                    "metrics": {"score": score},
                    "status": "completed",
                })
            (tmp / ".autolab").mkdir()
            ProjectState(tmp).save({})
            det = EscapeDetector(tmp)
            assert not det.detect_plateau("score", window=10)


class TestDiscoveryManager:
    def test_count_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DiscoveryManager(tmp)
            assert dm.count() == 0
            assert dm.next_number() == 1

    def test_format_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            dm = DiscoveryManager(tmp)
            entry = dm.format_entry(
                title="Test Discovery",
                discovery="We found something interesting.",
                why_non_obvious="Conventional wisdom says otherwise.",
                prior_art="No prior documentation found.",
                results="| Config | Score |\n|---|---|\n| A | 100 |",
                implications="This changes our approach.",
                campaign="test_campaign",
                category="novel_technique",
            )
            assert "## 1. Test Discovery" in entry
            assert "Autolab" in entry  # attribution
            assert "autonomous research orchestration" in entry
            assert "novel_technique" in entry

    def test_append_and_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "DISCOVERIES.md").write_text("# Discoveries\n\n---\n")
            dm = DiscoveryManager(tmp)
            entry = dm.format_entry(
                title="First", discovery="Found it.",
                why_non_obvious="Surprising.", prior_art="None.",
                results="Good.", implications="Big.",
            )
            num = dm.append_entry(entry)
            assert num == 1
            assert dm.count() == 1

            entry2 = dm.format_entry(
                title="Second", discovery="Another one.",
                why_non_obvious="Also surprising.", prior_art="None.",
                results="Better.", implications="Bigger.",
            )
            num2 = dm.append_entry(entry2)
            assert num2 == 2
            assert dm.count() == 2

    def test_get_all_titles(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "DISCOVERIES.md").write_text("# Discoveries\n\n---\n")
            dm = DiscoveryManager(tmp)
            for title in ["Alpha", "Beta", "Gamma"]:
                entry = dm.format_entry(
                    title=title, discovery=".", why_non_obvious=".",
                    prior_art=".", results=".", implications=".",
                )
                dm.append_entry(entry)
            titles = dm.get_all_titles()
            assert titles == ["Alpha", "Beta", "Gamma"]

    def test_has_attribution(self):
        dm = DiscoveryManager("/tmp")
        assert dm.has_attribution("Found with Autolab — autonomous research orchestration")
        assert not dm.has_attribution("Found with some other tool")


class TestLiteratureSearch:
    def test_queries_for_hypothesis(self):
        queries = LiteratureSearch.queries_for_hypothesis("transformer inference optimization")
        assert len(queries) >= 3
        assert all(q.purpose == "inform_hypothesis" for q in queries)
        assert any("state of the art" in q.query for q in queries)

    def test_queries_for_novelty(self):
        queries = LiteratureSearch.queries_for_novelty("per-stage INT4 shards outperform monolithic")
        assert len(queries) >= 3
        assert all(q.purpose == "verify_novelty" for q in queries)

    def test_queries_for_approaches(self):
        queries = LiteratureSearch.queries_for_approaches(
            "reduce activation transfer overhead",
            tried=["compression", "quantization"],
        )
        assert len(queries) >= 3
        assert any("-compression" in q.query or "-quantization" in q.query for q in queries)

    def test_format_prior_art_section(self):
        result = PriorArtResult(
            query="test finding",
            sources_checked=[
                {"source": "ArXiv", "finding": "No papers found"},
                {"source": "GitHub", "finding": "No issues found"},
            ],
            is_novel=True,
            summary="This is genuinely new.",
        )
        text = LiteratureSearch.format_prior_art_section(result)
        assert "### Prior art search" in text
        assert "ArXiv" in text
        assert "novel" in text.lower()

    def test_format_approach_suggestions(self):
        text = LiteratureSearch.format_approach_suggestions(
            "reduce latency",
            [
                {"name": "Speculative decoding", "source": "ArXiv 2023",
                 "description": "Run multiple forward passes"},
                {"name": "KV cache compression", "source": "GitHub",
                 "description": "Compress key-value cache"},
            ],
        )
        assert "Speculative decoding" in text
        assert "KV cache compression" in text


class TestTrendAnalysis:
    def _make_db(self, tmp: Path, data: list[tuple[str, str, dict]]) -> ResultsDB:
        db = ResultsDB(tmp / "results.db")
        for exp_name, campaign, metrics in data:
            db.store_result({
                "experiment_name": exp_name,
                "campaign_name": campaign,
                "metrics": metrics,
                "status": "completed",
            })
        return db

    def test_metric_trend_increasing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = self._make_db(tmp, [
                (f"e{i}", "c1", {"score": i * 10}) for i in range(10)
            ])
            analysis = TrendAnalysis(db)
            trend = analysis.metric_trend("score", "c1")
            assert trend["direction"] == "increasing"
            assert trend["count"] == 10

    def test_metric_trend_flat(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = self._make_db(tmp, [
                (f"e{i}", "c1", {"score": 50.0}) for i in range(10)
            ])
            analysis = TrendAnalysis(db)
            trend = analysis.metric_trend("score", "c1")
            assert trend["direction"] == "flat"

    def test_metric_trend_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = self._make_db(tmp, [("e0", "c1", {"score": 10})])
            analysis = TrendAnalysis(db)
            trend = analysis.metric_trend("score", "c1")
            assert trend["direction"] == "insufficient_data"

    def test_compare_campaigns(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = self._make_db(tmp, [
                ("e1", "fast", {"throughput": 100}),
                ("e2", "fast", {"throughput": 120}),
                ("e3", "slow", {"throughput": 50}),
                ("e4", "slow", {"throughput": 60}),
            ])
            analysis = TrendAnalysis(db)
            comparison = analysis.compare_campaigns("throughput", ["fast", "slow"])
            assert comparison[0]["campaign"] == "fast"
            assert comparison[0]["best_value"] == 120.0

    def test_improvement_over_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = self._make_db(tmp, [
                ("base", "baseline", {"throughput": 100}),
                ("test", "optimized", {"throughput": 150}),
            ])
            analysis = TrendAnalysis(db)
            imp = analysis.improvement_over_baseline(
                "throughput", "baseline", "optimized",
            )
            assert imp["is_better"]
            assert imp["relative_improvement"] == 0.5
            assert "+50.0%" in imp["percentage"]

    def test_overall_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = self._make_db(tmp, [
                ("e1", "c1", {"x": 1}),
                ("e2", "c1", {"x": 2}),
                ("e3", "c2", {"x": 3}),
            ])
            analysis = TrendAnalysis(db)
            progress = analysis.overall_progress()
            assert progress["total_experiments"] == 3
            assert progress["total_campaigns"] == 2
            assert progress["success_rate"] == 1.0
