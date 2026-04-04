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
    total_experiments: int = 0
    total_wall_time_s: float = 0.0


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

    # Aggregate totals from database
    if db:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(wall_time_s), 0) FROM experiments"
        ).fetchone()
        conn.close()
        root.total_experiments = row[0]
        root.total_wall_time_s = row[1]

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
    """Render the tree as a phylogenetic-style DOT string with dark-mode heatmap.

    Nodes are translucent except for the global-best experiment.  Stage titles
    sit at the top of each column via rank constraints.  Vertical separator
    lines are added in post-processing by ``render_to_png``.
    """
    # --- Footer text ---------------------------------------------------------
    total_campaigns = sum(len(q.campaigns) for q in root.questions)
    wall = root.total_wall_time_s
    if wall >= 3600:
        time_str = f"{wall / 3600:.1f}h"
    elif wall >= 60:
        time_str = f"{wall / 60:.1f}m"
    else:
        time_str = f"{wall:.1f}s"
    footer = (
        f"autolab: {root.total_experiments} experiments across "
        f"{total_campaigns} campaigns  |  "
        f"Cumulative wall time: {time_str}"
    )

    lines = [
        "digraph autolab {",
        "  rankdir=LR;",
        '  size="25.6,14.4!";',
        "  dpi=150;",
        '  ratio=fill;',
        '  bgcolor="transparent";',
        '  pad="0.5,1.5";',
        "  splines=ortho;",
        '  nodesep=0.4;',
        '  ranksep=2.5;',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica",'
        '        fontsize=28, margin="0.3,0.2", color="#484f58"];',
        '  edge [penwidth=4, arrowhead=none];',
        "",
    ]

    # --- Score experiments 0-1, scaled by campaign best-path status ----------
    exp_scores: dict[str, float] = {}
    campaign_scores: dict[str, float] = {}

    def _ekey(cname: str, ename: str) -> str:
        return f"{cname}/{ename}"

    for qnode in root.questions:
        for cnode in qnode.campaigns:
            vals = [
                (e, e.primary_value)
                for e in cnode.experiments
                if e.primary_value is not None
            ]
            if not vals:
                for e in cnode.experiments:
                    exp_scores[_ekey(cnode.name, e.name)] = 0.3
                campaign_scores[cnode.name] = 0.25
                continue

            raw = [v for _, v in vals]
            vmin, vmax = min(raw), max(raw)

            if cnode.is_on_best_path:
                lo, hi = 0.55, 1.0
            else:
                lo, hi = 0.0, 0.7

            for e, v in vals:
                if vmax == vmin:
                    norm = 1.0
                elif cnode.direction == "maximize":
                    norm = (v - vmin) / (vmax - vmin)
                else:
                    norm = (vmax - v) / (vmax - vmin)
                score = lo + norm * (hi - lo)
                if e.is_global_best:
                    score = 1.0
                exp_scores[_ekey(cnode.name, e.name)] = score

            campaign_scores[cnode.name] = max(
                exp_scores.get(_ekey(cnode.name, e.name), 0)
                for e in cnode.experiments
            )

    # --- Generate nodes and edges --------------------------------------------
    root_id = "root"
    q_ids: list[str] = []
    c_ids: list[str] = []
    e_ids: list[str] = []
    edge_defs: list[str] = []

    # Root node (semi-translucent dark blue)
    lines.append(
        f'  {root_id} [label="{_dot_escape(root.directive)}", '
        f'fillcolor="#1e3a5fCC", fontcolor="#e6edf3", fontsize=36, '
        f'style="rounded,filled,bold", margin="0.5,0.3"];'
    )

    for qnode in root.questions:
        q_id = f"q_{qnode.id}"
        q_ids.append(q_id)
        q_score = 1.0 if qnode.is_on_best_path else max(
            (campaign_scores.get(c.name, 0.25) for c in qnode.campaigns),
            default=0.25,
        )
        q_color = _heatmap_color(q_score)
        q_text = _text_color_for(q_color)
        n_campaigns = len(qnode.campaigns)
        n_experiments = sum(c.total for c in qnode.campaigns)
        counts = f"{n_campaigns} campaigns, {n_experiments} experiments"
        lines.append(
            f'  {q_id} [label="{_dot_escape(qnode.text)}\\n[{qnode.status}]\\n'
            f'{counts}", '
            f'fillcolor="{q_color}90", fontcolor="{q_text}", fontsize=30, '
            f'margin="0.4,0.25"];'
        )
        edge_defs.append(
            f'  {root_id} -> {q_id} [color="{q_color}", penwidth=6];'
        )

        for cnode in qnode.campaigns:
            c_id = f"c_{cnode.name}"
            c_ids.append(c_id)
            c_score = campaign_scores.get(cnode.name, 0.25)
            c_color = _heatmap_color(c_score)
            c_text = _text_color_for(c_color)
            moon = " 🌙" if cnode.moonshot else ""
            best = (
                f"\\nbest: {_fmt_val(cnode.best_value)}"
                if cnode.best_value is not None
                else ""
            )
            lines.append(
                f'  {c_id} [label="{_dot_escape(cnode.name)}{moon}\\n'
                f'{cnode.completed}/{cnode.total} done{best}", '
                f'fillcolor="{c_color}90", fontcolor="{c_text}", fontsize=28, '
                f'margin="0.4,0.25"];'
            )
            edge_defs.append(
                f'  {q_id} -> {c_id} [color="{c_color}", penwidth=5];'
            )

            for enode in cnode.experiments:
                e_id = f"e_{cnode.name}_{hash(enode.name) % 99999}"
                e_ids.append(e_id)
                e_score = exp_scores.get(_ekey(cnode.name, enode.name), 0.5)
                base_color = _heatmap_color(e_score)
                if enode.is_global_best:
                    # Fully opaque darkest green + bright border
                    e_fill = "#1B5E20"
                    e_text = "#FFFFFF"
                    e_extra = ', penwidth=5, color="#00E676"'
                    star = "⭐ BEST "
                else:
                    # Alpha proportional to score — best scores more opaque
                    alpha = int(0x50 + e_score * 0x70)
                    e_fill = f"{base_color}{alpha:02X}"
                    e_text = _text_color_for(base_color)
                    e_extra = ""
                    star = "★ " if enode.is_best_in_campaign else ""
                val = (
                    f"  ({_fmt_val(enode.primary_value)})"
                    if enode.primary_value is not None
                    else ""
                )
                lines.append(
                    f'  {e_id} [label="{star}{_dot_escape(enode.name)}{val}", '
                    f'fillcolor="{e_fill}", fontcolor="{e_text}", '
                    f'fontsize=24{e_extra}];'
                )
                edge_defs.append(
                    f'  {c_id} -> {e_id} [color="{_heatmap_color(e_score)}", '
                    f'penwidth=4];'
                )

            remaining = cnode.completed - len(cnode.experiments)
            if remaining > 0:
                more_id = f"e_{cnode.name}_more"
                e_ids.append(more_id)
                lines.append(
                    f'  {more_id} [label="...{remaining} more", '
                    f'fillcolor="#21262d99", fontcolor="#8b949e", fontsize=22, '
                    f'style="rounded,filled,dashed", color="#30363d"];'
                )
                edge_defs.append(
                    f'  {c_id} -> {more_id} [color="#30363d", '
                    f'penwidth=2, style=dashed];'
                )

    # --- Edges ---------------------------------------------------------------
    lines.extend(edge_defs)

    lines.append("}")
    return "\n".join(lines)


def render_to_png(
    dot_str: str,
    png_path: str,
    root: TreeRoot | None = None,
    svg_path: str | None = None,
) -> None:
    """Render DOT to PNG with separator lines behind the graph and titles on top.

    Pipeline:
    1. Graphviz renders with transparent background.
    2. A dark base layer is created with dashed separator lines.
    3. The graphviz output is composited on top (separators stay behind).
    4. Stage titles and footer are drawn via PIL for precise positioning.
    """
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(
        suffix=".dot", mode="w", delete=False,
    ) as f:
        f.write(dot_str)
        dot_path = f.name

    try:
        subprocess.run(
            ["dot", "-Tpng", dot_path, "-o", png_path],
            check=True, capture_output=True,
        )
        if svg_path:
            subprocess.run(
                ["dot", "-Tsvg", dot_path, "-o", svg_path],
                check=True, capture_output=True,
            )
        result = subprocess.run(
            ["dot", "-Tplain", dot_path],
            check=True, capture_output=True, text=True,
        )
        _composite_layers(result.stdout, png_path, root)
    finally:
        Path(dot_path).unlink(missing_ok=True)


_STAGE_TITLES = ["DIRECTIVE", "HYPOTHESES", "CAMPAIGNS", "EXPERIMENTS"]
_BG_COLOR = (13, 17, 23, 255)  # #0d1117


def _composite_layers(
    plain_output: str,
    png_path: str,
    root: "TreeRoot | None" = None,
) -> None:
    """Build the final image: dark bg + separators → graph → titles + footer."""
    from PIL import Image, ImageDraw

    # --- Parse graphviz plain layout for node positions ----------------------
    graph_width = graph_height = 0.0
    nodes: dict[str, tuple[float, float, float]] = {}  # name: (x, y, w)

    for line in plain_output.split("\n"):
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "graph":
            graph_width = float(parts[2])
            graph_height = float(parts[3])
        elif parts[0] == "node":
            nodes[parts[1]] = (float(parts[2]), float(parts[3]),
                               float(parts[4]))

    if not graph_width or not nodes:
        return

    # --- Group nodes by stage ------------------------------------------------
    stages: list[list[tuple[float, float]]] = [[], [], [], []]
    for name, (x, _, w) in nodes.items():
        if name == "root":
            stages[0].append((x, w))
        elif name.startswith("q_"):
            stages[1].append((x, w))
        elif name.startswith("c_"):
            stages[2].append((x, w))
        elif name.startswith("e_"):
            stages[3].append((x, w))

    # --- Load graph image (transparent bg from graphviz) ---------------------
    graph = Image.open(png_path).convert("RGBA")
    W, H = graph.size
    x_scale = W / graph_width

    # --- 1. Base layer: dark background + separator lines --------------------
    base = Image.new("RGBA", (W, H), _BG_COLOR)
    draw = ImageDraw.Draw(base)

    dash, gap = 24, 14
    sep_color = (48, 54, 61, 180)

    for i in range(len(stages) - 1):
        left, right = stages[i], stages[i + 1]
        if not left or not right:
            continue
        right_edge = max(x + w / 2 for x, w in left)
        left_edge = min(x - w / 2 for x, w in right)
        px = int(((right_edge + left_edge) / 2) * x_scale)
        y = 0
        while y < H:
            draw.line([(px, y), (px, min(y + dash, H))],
                      fill=sep_color, width=3)
            y += dash + gap

    # --- 2. Composite graph on top of base -----------------------------------
    result = Image.alpha_composite(base, graph)

    # --- 3. Draw stage titles at a fixed y across all columns ----------------
    draw = ImageDraw.Draw(result)
    title_font = _load_font(64)
    title_y = 55  # padding from the top edge
    title_color = (230, 237, 243, 255)

    for idx, stage_nodes in enumerate(stages):
        if not stage_nodes:
            continue
        center_x = sum(x for x, _ in stage_nodes) / len(stage_nodes)
        px = int(center_x * x_scale)
        title = _STAGE_TITLES[idx]
        bbox = draw.textbbox((0, 0), title, font=title_font)
        tw = bbox[2] - bbox[0]
        draw.text((px - tw // 2, title_y), title,
                  fill=title_color, font=title_font)

    # --- 4. Draw footer with bold "autolab" ----------------------------------
    if root is not None:
        total_campaigns = sum(len(q.campaigns) for q in root.questions)
        wall = root.total_wall_time_s
        if wall >= 3600:
            time_str = f"{wall / 3600:.1f}h"
        elif wall >= 60:
            time_str = f"{wall / 60:.1f}m"
        else:
            time_str = f"{wall:.1f}s"
        bold_part = "autolab:"
        rest_part = (
            f" {root.total_experiments} experiments across "
            f"{total_campaigns} campaigns  |  "
            f"Cumulative wall time: {time_str}"
        )
        font_bold = _load_font(44, bold=True)
        font_reg = _load_font(44, bold=False)
        footer_color = (139, 148, 158, 255)  # #8b949e

        # Measure bold part width
        bb = draw.textbbox((0, 0), bold_part, font=font_bold)
        bold_w = bb[2] - bb[0]
        # Measure full footer width
        br = draw.textbbox((0, 0), rest_part, font=font_reg)
        rest_w = br[2] - br[0]
        total_w = bold_w + rest_w

        fx = (W - total_w) // 2
        fy = H - 80  # raised from the very bottom
        draw.text((fx, fy), bold_part, fill=title_color, font=font_bold)
        draw.text((fx + bold_w, fy), rest_part, fill=footer_color,
                  font=font_reg)

    result.save(png_path)


def _load_font(size: int, bold: bool = False):
    """Try to load Helvetica (regular or bold); fall back to default."""
    from PIL import ImageFont
    if bold:
        candidates = [
            ("/System/Library/Fonts/Helvetica.ttc", 1),  # Bold face index
            ("/Library/Fonts/Helvetica Bold.ttf", 0),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
        ]
    else:
        candidates = [
            ("/System/Library/Fonts/Helvetica.ttc", 0),
            ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
            ("/Library/Fonts/Helvetica.ttc", 0),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
        ]
    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size, index=index)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


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


def _heatmap_color(score: float) -> str:
    """Map a 0-1 score to a heatmap hex color (dark-red -> yellow -> dark-green)."""
    stops = [
        (0.0, 0xB7, 0x1C, 0x1C),
        (0.25, 0xE6, 0x51, 0x00),
        (0.5, 0xFD, 0xD8, 0x35),
        (0.75, 0x43, 0xA0, 0x47),
        (1.0, 0x1B, 0x5E, 0x20),
    ]
    score = max(0.0, min(1.0, score))
    for i in range(len(stops) - 1):
        if score <= stops[i + 1][0]:
            s0, r0, g0, b0 = stops[i]
            s1, r1, g1, b1 = stops[i + 1]
            t = (score - s0) / (s1 - s0) if s1 != s0 else 0
            r = int(r0 + t * (r1 - r0))
            g = int(g0 + t * (g1 - g0))
            b = int(b0 + t * (b1 - b0))
            return f"#{r:02X}{g:02X}{b:02X}"
    return f"#{stops[-1][1]:02X}{stops[-1][2]:02X}{stops[-1][3]:02X}"


def _text_color_for(bg_hex: str) -> str:
    """Return black or white text for readability on the given background."""
    r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
    return "#FFFFFF" if (0.299 * r + 0.587 * g + 0.114 * b) < 110 else "#000000"
