"""Statistical trend analysis for experiment results."""

from __future__ import annotations

from typing import Any, Optional

from .db import ResultsDB


class TrendAnalysis:
    """Analyzes experiment result trends for the research loop."""

    def __init__(self, db: ResultsDB):
        self.db = db

    def metric_trend(
        self,
        metric_name: str,
        campaign_name: Optional[str] = None,
        window: int = 10,
    ) -> dict[str, Any]:
        """Analyze the trend of a metric over recent experiments.

        Returns: {direction, slope, mean, std, min, max, count, improving}
        """
        history = self.db.load_history(campaign_name)
        values = []
        for r in history:
            val = r.get("metrics", {}).get(metric_name)
            if val is not None and isinstance(val, (int, float)):
                values.append(float(val))

        values = values[-window:] if window else values

        if len(values) < 2:
            return {
                "direction": "insufficient_data",
                "count": len(values),
                "improving": None,
            }

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = variance ** 0.5

        # Simple linear trend: compare first half mean to second half mean
        mid = len(values) // 2
        first_half = values[:mid]
        second_half = values[mid:]
        first_mean = sum(first_half) / len(first_half) if first_half else 0
        second_mean = sum(second_half) / len(second_half) if second_half else 0

        if abs(first_mean) > 0:
            slope = (second_mean - first_mean) / abs(first_mean)
        else:
            slope = 0.0

        if abs(slope) < 0.02:
            direction = "flat"
        elif slope > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        return {
            "direction": direction,
            "slope": round(slope, 4),
            "mean": round(mean, 4),
            "std": round(std, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "count": len(values),
            "improving": None,  # Caller must set based on maximize/minimize
        }

    def compare_campaigns(
        self,
        metric_name: str,
        campaign_names: list[str],
        direction: str = "maximize",
    ) -> list[dict[str, Any]]:
        """Compare campaigns by a metric. Returns sorted list of summaries."""
        summaries = []
        for cname in campaign_names:
            best_rows = self.db.best_by_metric(metric_name, direction, cname, limit=1)
            if best_rows:
                summaries.append({
                    "campaign": cname,
                    "best_value": best_rows[0].get("metric_value"),
                    "best_experiment": best_rows[0].get("experiment_name"),
                })
            else:
                summaries.append({
                    "campaign": cname,
                    "best_value": None,
                    "best_experiment": None,
                })

        reverse = direction == "maximize"
        summaries.sort(
            key=lambda s: s["best_value"] if s["best_value"] is not None else float("-inf"),
            reverse=reverse,
        )
        return summaries

    def improvement_over_baseline(
        self,
        metric_name: str,
        baseline_campaign: str,
        test_campaign: str,
        direction: str = "maximize",
    ) -> dict[str, Any]:
        """Calculate improvement of one campaign over a baseline."""
        baseline_rows = self.db.best_by_metric(metric_name, direction, baseline_campaign, 1)
        test_rows = self.db.best_by_metric(metric_name, direction, test_campaign, 1)

        if not baseline_rows or not test_rows:
            return {"improvement": None, "error": "insufficient data"}

        baseline_val = baseline_rows[0].get("metric_value", 0)
        test_val = test_rows[0].get("metric_value", 0)

        if baseline_val == 0:
            return {"improvement": None, "error": "baseline is zero"}

        abs_improvement = test_val - baseline_val
        rel_improvement = abs_improvement / abs(baseline_val)

        better = (
            (direction == "maximize" and test_val > baseline_val) or
            (direction == "minimize" and test_val < baseline_val)
        )

        return {
            "baseline_value": baseline_val,
            "test_value": test_val,
            "absolute_improvement": round(abs_improvement, 4),
            "relative_improvement": round(rel_improvement, 4),
            "percentage": f"{rel_improvement * 100:+.1f}%",
            "is_better": better,
        }

    def overall_progress(self) -> dict[str, Any]:
        """Get high-level progress stats."""
        total = self.db.count_experiments()
        history = self.db.load_history()
        campaigns = set(r.get("campaign_name") for r in history if r.get("campaign_name"))
        completed = sum(1 for r in history if r.get("status") == "completed")
        failed = sum(1 for r in history if r.get("status") == "failed")

        return {
            "total_experiments": total,
            "completed": completed,
            "failed": failed,
            "success_rate": round(completed / total, 2) if total > 0 else 0,
            "total_campaigns": len(campaigns),
            "campaigns": sorted(campaigns),
        }
