"""Results database — dynamic-schema SQLite storage for experiment results."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class ResultsDB:
    """SQLite database for experiment results with dynamic metrics."""

    def __init__(self, db_path: str | Path = "results.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                run_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                campaign_name TEXT NOT NULL,
                experiment_name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                status TEXT NOT NULL,
                wall_time_s REAL,
                raw_output TEXT,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metric_values (
                run_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL,
                PRIMARY KEY (run_id, metric_name),
                FOREIGN KEY (run_id) REFERENCES experiments(run_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_experiments_campaign
            ON experiments(campaign_name)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_metric_values_name
            ON metric_values(metric_name)
        """)
        conn.commit()
        conn.close()

    def store_result(self, result: dict[str, Any]) -> str:
        """Store an experiment result. Returns the run_id."""
        run_id = f"{result.get('experiment_name', 'run')}_{uuid.uuid4().hex[:8]}"
        metrics = result.get("metrics", {})
        config = result.get("config", {})

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO experiments
                   (run_id, timestamp, campaign_name, experiment_name,
                    config_json, metrics_json, status, wall_time_s,
                    raw_output, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    datetime.now(timezone.utc).isoformat(),
                    result.get("campaign_name", ""),
                    result.get("experiment_name", "unnamed"),
                    json.dumps(config, default=str),
                    json.dumps(metrics, default=str),
                    result.get("status", "completed"),
                    result.get("wall_time_s"),
                    result.get("raw_output"),
                    result.get("error"),
                ),
            )
            for metric_name, metric_value in metrics.items():
                if isinstance(metric_value, (int, float)):
                    conn.execute(
                        "INSERT INTO metric_values (run_id, metric_name, metric_value) "
                        "VALUES (?, ?, ?)",
                        (run_id, metric_name, float(metric_value)),
                    )
            conn.commit()
        finally:
            conn.close()
        return run_id

    def load_history(self, campaign_name: Optional[str] = None) -> list[dict]:
        """Load experiment history, optionally filtered by campaign."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if campaign_name:
                rows = conn.execute(
                    "SELECT * FROM experiments WHERE campaign_name = ? "
                    "ORDER BY timestamp ASC",
                    (campaign_name,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM experiments ORDER BY timestamp ASC"
                ).fetchall()

            results = []
            for row in rows:
                d = dict(row)
                d["metrics"] = json.loads(d.pop("metrics_json", "{}"))
                d["config"] = json.loads(d.pop("config_json", "{}"))
                results.append(d)
            return results
        finally:
            conn.close()

    def count_experiments(self, campaign_name: Optional[str] = None) -> int:
        """Count total experiments, optionally filtered by campaign."""
        conn = sqlite3.connect(self.db_path)
        try:
            if campaign_name:
                row = conn.execute(
                    "SELECT COUNT(*) FROM experiments WHERE campaign_name = ?",
                    (campaign_name,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def best_by_metric(
        self,
        metric_name: str,
        direction: str = "maximize",
        campaign_name: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Get the best experiments by a specific metric."""
        order = "DESC" if direction == "maximize" else "ASC"
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if campaign_name:
                rows = conn.execute(
                    f"""SELECT e.*, mv.metric_value
                        FROM experiments e
                        JOIN metric_values mv ON e.run_id = mv.run_id
                        WHERE mv.metric_name = ? AND e.campaign_name = ?
                        ORDER BY mv.metric_value {order}
                        LIMIT ?""",
                    (metric_name, campaign_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""SELECT e.*, mv.metric_value
                        FROM experiments e
                        JOIN metric_values mv ON e.run_id = mv.run_id
                        WHERE mv.metric_name = ?
                        ORDER BY mv.metric_value {order}
                        LIMIT ?""",
                    (metric_name, limit),
                ).fetchall()

            results = []
            for row in rows:
                d = dict(row)
                d["metrics"] = json.loads(d.pop("metrics_json", "{}"))
                d["config"] = json.loads(d.pop("config_json", "{}"))
                results.append(d)
            return results
        finally:
            conn.close()

    def campaign_summary(self, campaign_name: str) -> dict[str, Any]:
        """Get summary statistics for a campaign."""
        conn = sqlite3.connect(self.db_path)
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM experiments WHERE campaign_name = ?",
                (campaign_name,),
            ).fetchone()[0]
            completed = conn.execute(
                "SELECT COUNT(*) FROM experiments WHERE campaign_name = ? AND status = 'completed'",
                (campaign_name,),
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM experiments WHERE campaign_name = ? AND status = 'failed'",
                (campaign_name,),
            ).fetchone()[0]
            return {
                "campaign_name": campaign_name,
                "total": total,
                "completed": completed,
                "failed": failed,
            }
        finally:
            conn.close()
