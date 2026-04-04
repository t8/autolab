"""Research tree visualization — renders the directive → questions → campaigns → experiments tree.

Supports terminal output (Unicode + ANSI colors) and DOT/Graphviz export.
The best path from root to the single best experiment is highlighted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from ..core.campaign import Campaign
from ..core.plan import ResearchPlan
from ..metrics.db import ResultsDB


# ANSI color codes
class _C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    RED = "\033[31m"
    BG_GREEN = "\033[42m"
    BOLD_GREEN = "\033[1;32m"
    BOLD_YELLOW = "\033[1;33m"
    BOLD_CYAN = "\033[1;36m"


@dataclass
class ExperimentNode:
    name: str
    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    primary_value: float | None = None
    is_best_in_campaign: bool = False
    is_global_best: bool = False


@dataclass
class CampaignNode:
    name: str
    path: str
    hypothesis: str
    moonshot: bool
    primary_metric: str
    direction: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    experiments: list[ExperimentNode] = field(default_factory=list)
    best_value: float | None = None
    is_on_best_path: bool = False


@dataclass
class QuestionNode:
    id: str
    text: str
    status: str
    priority: str
    campaigns: list[CampaignNode] = field(default_factory=list)
    is_on_best_path: bool = False


@dataclass
class TreeRoot:
    directive: str
    questions: list[QuestionNode] = field(default_factory=list)
    global_best_experiment: str | None = None
    global_best_value: float | None = None
    global_best_metric: str | None = None


def build_tree(
    project_dir: str | Path,
    top_n: int = 5,
    metric_override: str | None = None,
) -> TreeRoot:
    """Build the research tree from project data.

    Args:
        project_dir: Path to the autolab project
        top_n: Number of top experiments to show per campaign
        metric_override: Override the primary metric for ranking
    """
    project_dir = Path(project_dir)
    plan = ResearchPlan(project_dir)
    db_path = project_dir / "results.db"
    db = ResultsDB(db_path) if db_path.exists() else None

    # Load config for directive
    config_path = project_dir / "autolab.yaml"
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text()) or {}
        directive = config.get("directive", "Research project")
    else:
        directive = plan.directive or "Research project"

    root = TreeRoot(directive=directive)

    # Track global best across all campaigns
    global_best_val: float | None = None
    global_best_exp: str | None = None
    global_best_metric: str | None = None
    global_best_campaign: str | None = None
    global_best_question: str | None = None
    global_direction: str = "maximize"

    # Build question nodes from plan
    questions = plan.get_questions()
    campaign_to_question: dict[str, str] = {}

    for q in questions:
        qnode = QuestionNode(
            id=q.id, text=q.text, status=q.status, priority=q.priority,
        )

        for cname in q.campaigns:
            campaign_to_question[cname] = q.id

        root.questions.append(qnode)

    # Discover campaign files
    campaigns_dir = project_dir / "campaigns"
    campaign_files: list[Path] = []
    if campaigns_dir.exists():
        campaign_files = sorted(campaigns_dir.glob("*.yaml")) + sorted(campaigns_dir.glob("*.yml"))

    # Build campaign nodes
    for cpath in campaign_files:
        try:
            campaign = Campaign(cpath)
        except Exception:
            continue

        cnode = CampaignNode(
            name=campaign.name,
            path=str(cpath.relative_to(project_dir)),
            hypothesis=campaign.hypothesis,
            moonshot=campaign.moonshot,
            primary_metric=metric_override or campaign.primary_metric,
            direction=campaign.metric_direction,
        )

        # Load results
        if db:
            history = db.load_history(campaign.name)
            cnode.total = len(history)
            cnode.completed = sum(1 for r in history if r.get("status") == "completed")
            cnode.failed = sum(1 for r in history if r.get("status") == "failed")

            # Get experiments with metrics
            completed_results = [r for r in history if r.get("status") == "completed"]

            if cnode.primary_metric and completed_results:
                # Sort by primary metric
                reverse = cnode.direction == "maximize"
                completed_results.sort(
                    key=lambda r: r.get("metrics", {}).get(cnode.primary_metric, float("-inf") if reverse else float("inf")),
                    reverse=reverse,
                )

                if completed_results:
                    best_r = completed_results[0]
                    cnode.best_value = best_r.get("metrics", {}).get(cnode.primary_metric)

            # Build experiment nodes (top N + failures)
            shown = completed_results[:top_n]
            for i, r in enumerate(shown):
                val = r.get("metrics", {}).get(cnode.primary_metric)
                enode = ExperimentNode(
                    name=_short_experiment_name(r.get("experiment_name", ""), campaign.name),
                    status=r.get("status", "unknown"),
                    metrics=r.get("metrics", {}),
                    primary_value=val,
                    is_best_in_campaign=(i == 0 and val is not None),
                )
                cnode.experiments.append(enode)

            # Track global best
            if cnode.best_value is not None:
                is_better = False
                if global_best_val is None:
                    is_better = True
                elif cnode.direction == "maximize" and cnode.best_value > global_best_val:
                    is_better = True
                elif cnode.direction == "minimize" and cnode.best_value < global_best_val:
                    is_better = True

                if is_better:
                    global_best_val = cnode.best_value
                    global_best_exp = completed_results[0].get("experiment_name", "")
                    global_best_metric = cnode.primary_metric
                    global_best_campaign = campaign.name
                    global_best_question = campaign_to_question.get(campaign.name)
                    global_direction = cnode.direction

        # Attach to the right question
        q_id = campaign_to_question.get(campaign.name)
        attached = False
        if q_id:
            for qnode in root.questions:
                if qnode.id == q_id:
                    qnode.campaigns.append(cnode)
                    attached = True
                    break

        if not attached:
            # Create an "unlinked" question if needed
            unlinked = None
            for qnode in root.questions:
                if qnode.id == "_unlinked":
                    unlinked = qnode
                    break
            if unlinked is None:
                unlinked = QuestionNode(
                    id="_unlinked", text="Unlinked campaigns", status="active", priority="medium",
                )
                root.questions.append(unlinked)
            unlinked.campaigns.append(cnode)

    # Mark the best path
    root.global_best_experiment = global_best_exp
    root.global_best_value = global_best_val
    root.global_best_metric = global_best_metric

    if global_best_campaign:
        for qnode in root.questions:
            for cnode in qnode.campaigns:
                if cnode.name == global_best_campaign:
                    cnode.is_on_best_path = True
                    qnode.is_on_best_path = True
                    for enode in cnode.experiments:
                        if enode.is_best_in_campaign:
                            enode.is_global_best = True

    return root


def render_terminal(root: TreeRoot, color: bool = True, top_n: int = 5) -> str:
    """Render the tree as a Unicode string with optional ANSI colors."""
    c = _C if color else type("_NoColor", (), {k: "" for k in dir(_C) if not k.startswith("_")})()
    lines: list[str] = []

    # Root
    lines.append(f"{c.BOLD}{c.CYAN}{root.directive}{c.RESET}")
    if root.global_best_experiment:
        lines.append(
            f"{c.DIM}Best overall: {root.global_best_metric}="
            f"{_fmt_val(root.global_best_value)} "
            f"({_short_experiment_name(root.global_best_experiment, '')}){c.RESET}"
        )
    lines.append("")

    for qi, qnode in enumerate(root.questions):
        is_last_q = (qi == len(root.questions) - 1)
        q_prefix = "└── " if is_last_q else "├── "
        q_cont = "    " if is_last_q else "│   "

        # Question line
        status_icon = {"active": "●", "answered": "✓", "blocked": "◌", "abandoned": "✗"}.get(qnode.status, "?")
        priority_color = {"high": c.RED, "medium": c.YELLOW, "low": c.DIM}.get(qnode.priority, "")
        highlight = c.BOLD_GREEN if qnode.is_on_best_path else ""

        lines.append(
            f"{highlight}{q_prefix}{status_icon} {c.BOLD}{qnode.id}{c.RESET}"
            f"{highlight}: {qnode.text}{c.RESET}"
            f" {c.DIM}[{qnode.status}]{c.RESET}"
            f" {priority_color}({qnode.priority}){c.RESET}"
        )

        if not qnode.campaigns:
            lines.append(f"{q_cont}{c.DIM}(no campaigns yet){c.RESET}")
            continue

        for ci, cnode in enumerate(qnode.campaigns):
            is_last_c = (ci == len(qnode.campaigns) - 1)
            c_prefix = q_cont + ("└── " if is_last_c else "├── ")
            c_cont = q_cont + ("    " if is_last_c else "│   ")

            # Campaign line
            moon = " 🌙" if cnode.moonshot else ""
            c_highlight = c.BOLD_GREEN if cnode.is_on_best_path else ""
            status_parts = []
            if cnode.completed:
                status_parts.append(f"{cnode.completed} completed")
            if cnode.failed:
                status_parts.append(f"{c.RED}{cnode.failed} failed{c.RESET}")
            status_str = ", ".join(status_parts) or "no results"

            best_str = ""
            if cnode.best_value is not None:
                best_str = f" → best {cnode.primary_metric}={_fmt_val(cnode.best_value)}"

            lines.append(
                f"{c_highlight}{c_prefix}{c.BOLD_YELLOW}{cnode.name}{c.RESET}"
                f"{moon} {c.DIM}({status_str}){c.RESET}"
                f"{c_highlight}{best_str}{c.RESET}"
            )

            if cnode.hypothesis:
                lines.append(f"{c_cont}{c.DIM}\"{cnode.hypothesis}\"{c.RESET}")

            # Experiments
            for ei, enode in enumerate(cnode.experiments):
                is_last_e = (ei == len(cnode.experiments) - 1)
                remaining = cnode.completed - len(cnode.experiments)
                show_more = is_last_e and remaining > 0

                e_prefix = c_cont + ("└── " if (is_last_e and not show_more) else "├── ")

                metric_str = ""
                if enode.primary_value is not None:
                    metric_str = f" → {cnode.primary_metric}={_fmt_val(enode.primary_value)}"

                if enode.is_global_best:
                    star = f" {c.BOLD_GREEN}★ BEST{c.RESET}"
                    e_color = c.BOLD_GREEN
                elif enode.is_best_in_campaign:
                    star = f" {c.GREEN}★{c.RESET}"
                    e_color = c.GREEN
                else:
                    star = ""
                    e_color = ""

                lines.append(
                    f"{e_color}{e_prefix}{enode.name}{c.RESET}"
                    f"{e_color}{metric_str}{c.RESET}{star}"
                )

                if show_more:
                    more_prefix = c_cont + "└── "
                    lines.append(f"{more_prefix}{c.DIM}...{remaining} more{c.RESET}")

        if qi < len(root.questions) - 1:
            lines.append("│")

    return "\n".join(lines)


def render_dot(root: TreeRoot) -> str:
    """Render the tree as a Graphviz DOT string."""
    lines = [
        "digraph autolab {",
        '  rankdir=TB;',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica"];',
        '  edge [color="#888888"];',
        "",
    ]

    # Root node
    root_id = "root"
    lines.append(f'  {root_id} [label="{_dot_escape(root.directive)}", '
                 f'fillcolor="#E3F2FD", fontsize=14, style="rounded,filled,bold"];')

    for qnode in root.questions:
        q_id = f"q_{qnode.id}"
        q_color = "#C8E6C9" if qnode.is_on_best_path else "#F5F5F5"
        q_border = ', color="#2E7D32", penwidth=2' if qnode.is_on_best_path else ""
        status_label = f"[{qnode.status}]"
        lines.append(
            f'  {q_id} [label="{qnode.id}: {_dot_escape(qnode.text)}\\n{status_label}", '
            f'fillcolor="{q_color}"{q_border}];'
        )
        edge_style = ' [color="#2E7D32", penwidth=2]' if qnode.is_on_best_path else ""
        lines.append(f"  {root_id} -> {q_id}{edge_style};")

        for cnode in qnode.campaigns:
            c_id = f"c_{cnode.name}"
            c_color = "#C8E6C9" if cnode.is_on_best_path else ("#FFF9C4" if cnode.moonshot else "#FFFFFF")
            c_border = ', color="#2E7D32", penwidth=2' if cnode.is_on_best_path else ""
            moon_label = " 🌙" if cnode.moonshot else ""
            best_label = f"\\nbest: {_fmt_val(cnode.best_value)}" if cnode.best_value is not None else ""
            lines.append(
                f'  {c_id} [label="{_dot_escape(cnode.name)}{moon_label}\\n'
                f'{cnode.completed}/{cnode.total} done{best_label}", '
                f'fillcolor="{c_color}"{c_border}];'
            )
            edge_style = ' [color="#2E7D32", penwidth=2]' if cnode.is_on_best_path else ""
            lines.append(f"  {q_id} -> {c_id}{edge_style};")

            for enode in cnode.experiments:
                e_id = f"e_{cnode.name}_{hash(enode.name) % 99999}"
                val_label = f"\\n{_fmt_val(enode.primary_value)}" if enode.primary_value is not None else ""

                if enode.is_global_best:
                    e_color = "#A5D6A7"
                    e_border = ', color="#1B5E20", penwidth=3'
                    e_shape = ', shape=doubleoctagon'
                elif enode.is_best_in_campaign:
                    e_color = "#C8E6C9"
                    e_border = ', color="#2E7D32", penwidth=2'
                    e_shape = ""
                else:
                    e_color = "#FAFAFA"
                    e_border = ""
                    e_shape = ""

                lines.append(
                    f'  {e_id} [label="{_dot_escape(enode.name)}{val_label}", '
                    f'fillcolor="{e_color}", fontsize=10{e_border}{e_shape}];'
                )
                edge_style = ' [color="#2E7D32", penwidth=2]' if enode.is_global_best else ""
                lines.append(f"  {c_id} -> {e_id}{edge_style};")

    lines.append("}")
    return "\n".join(lines)


def _short_experiment_name(name: str, campaign_name: str) -> str:
    """Strip the campaign name prefix from an experiment name for display."""
    if campaign_name and name.startswith(campaign_name + "_"):
        return name[len(campaign_name) + 1:]
    return name


def _fmt_val(val: Any) -> str:
    """Format a metric value for display."""
    if val is None:
        return "N/A"
    if isinstance(val, float):
        if abs(val) >= 1_000_000:
            return f"{val:,.0f}"
        elif abs(val) >= 100:
            return f"{val:,.1f}"
        elif abs(val) >= 1:
            return f"{val:.2f}"
        else:
            return f"{val:.4f}"
    return str(val)


def _dot_escape(s: str) -> str:
    """Escape a string for Graphviz DOT labels."""
    return s.replace('"', '\\"').replace("\n", "\\n")[:80]
