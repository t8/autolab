"""Autolab CLI — init, run, status, results."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import yaml

from .core.loop import ResearchLoop
from .metrics.db import ResultsDB


def _resolve_metric_direction(
    project_dir: Path, metric_name: str, campaign_name: str | None
) -> tuple[str, str | None]:
    """Resolve the sort direction for a metric from the campaign YAMLs.

    A campaign declares `metrics.direction`, but `results` had no way to see it
    and always sorted descending — reporting the *worst* run first for any
    minimize-direction metric such as latency.

    Returns (direction, source_campaign_name). Falls back to "maximize" when no
    campaign declares this metric as primary, preserving the historical default.
    """
    campaigns_dir = project_dir / "campaigns"
    if not campaigns_dir.is_dir():
        return "maximize", None

    declared: dict[str, str] = {}
    for path in sorted(campaigns_dir.glob("*.y*ml")):
        try:
            config = yaml.safe_load(path.read_text()) or {}
        except (yaml.YAMLError, OSError):
            continue
        if not isinstance(config, dict):
            continue
        metrics = config.get("metrics")
        if not isinstance(metrics, dict) or metrics.get("primary") != metric_name:
            continue
        direction = metrics.get("direction", "maximize")
        if direction not in ("maximize", "minimize"):
            continue
        name = config.get("name")
        if campaign_name and name == campaign_name:
            return direction, name
        if not campaign_name and name:
            declared[name] = direction

    # No campaign filter: only infer when every campaign using this metric agrees.
    if not campaign_name:
        agreed = set(declared.values())
        if len(agreed) == 1:
            return agreed.pop(), None
    return "maximize", None


@click.group()
@click.version_option(package_name="autolab")
def main():
    """Autolab — autonomous research orchestration."""


@main.command()
@click.argument("goal")
@click.option("--dir", "-d", "directory", default=".", help="Project directory")
def init(goal: str, directory: str):
    """Initialize a new research project with a goal."""
    from .scaffold.init import scaffold_project
    project_dir = Path(directory).resolve()
    scaffold_project(project_dir, goal)
    click.echo(f"\nAutolab project initialized in {project_dir}")
    click.echo(f"Research directive: {goal}")
    click.echo("\nNext steps:")
    click.echo("  1. Edit autolab.yaml to configure your agent and runner")
    click.echo("  2. Create campaigns in campaigns/")
    click.echo("  3. Run: autolab run campaigns/your_campaign.yaml")


@main.command()
@click.argument("campaign_path")
@click.option("--db", "db_path", default="results.db", help="Results database path")
def run(campaign_path: str, db_path: str):
    """Run a campaign's experiments."""
    if not Path(campaign_path).exists():
        click.echo(f"Campaign file not found: {campaign_path}", err=True)
        sys.exit(1)

    loop = ResearchLoop(db_path)
    results = loop.run_campaign(campaign_path)

    completed = sum(1 for r in results if r.status == "completed")
    failed = sum(1 for r in results if r.status == "failed")
    click.echo(f"\nFinished: {completed} completed, {failed} failed")


@main.command()
@click.option("--db", "db_path", default="results.db", help="Results database path")
def status(db_path: str):
    """Show research status."""
    if not Path(db_path).exists():
        click.echo("No results database found. Run some campaigns first.")
        return

    db = ResultsDB(db_path)
    total = db.count_experiments()
    click.echo(f"Total experiments: {total}")

    history = db.load_history()
    campaigns = set(r.get("campaign_name") for r in history)
    click.echo(f"Campaigns: {len(campaigns)}")

    for cname in sorted(campaigns):
        summary = db.campaign_summary(cname)
        click.echo(f"  {cname}: {summary['completed']} completed, {summary['failed']} failed")


@main.command()
@click.option("--db", "db_path", default="results.db", help="Results database path")
@click.option("--campaign", "-c", "campaign_name", default=None, help="Filter by campaign")
@click.option("--metric", "-m", "metric_name", default=None, help="Sort by metric")
@click.option("--top", "-n", "limit", default=10, help="Number of results")
@click.option(
    "--direction",
    "-d",
    "direction",
    default=None,
    type=click.Choice(["maximize", "minimize"]),
    help="Sort direction. Defaults to the campaign's declared metrics.direction.",
)
def results(db_path: str, campaign_name: str | None, metric_name: str | None, limit: int, direction: str | None):
    """Query experiment results."""
    if not Path(db_path).exists():
        click.echo("No results database found.")
        return

    db = ResultsDB(db_path)

    if metric_name:
        source = None
        if direction is None:
            direction, source = _resolve_metric_direction(
                Path(db_path).resolve().parent, metric_name, campaign_name
            )
        rows = db.best_by_metric(metric_name, direction, campaign_name, limit)
        label = f"{direction}, from campaign {source}" if source else direction
        click.echo(f"\nTop {len(rows)} by {metric_name} ({label}):")
        for r in rows:
            val = r.get("metric_value", "N/A")
            click.echo(f"  {r['experiment_name']}: {metric_name}={val}")
    else:
        history = db.load_history(campaign_name)
        for r in history[-limit:]:
            metrics_str = ", ".join(f"{k}={v}" for k, v in r.get("metrics", {}).items())
            click.echo(f"  [{r['status']}] {r['experiment_name']}: {metrics_str}")


@main.command()
@click.option("--dir", "-d", "directory", default=".", help="Project directory")
@click.option("--top", "-n", "top_n", default=5, help="Top experiments per campaign")
@click.option("--metric", "-m", "metric_override", default=None, help="Override primary metric")
@click.option("--no-color", is_flag=True, help="Disable ANSI colors")
@click.option("--dot", "dot_output", default=None, help="Write Graphviz DOT to file")
@click.option("--render", "render_path", default=None, help="Render to PNG/SVG (requires graphviz)")
def tree(directory: str, top_n: int, metric_override: str | None, no_color: bool, dot_output: str | None, render_path: str | None):
    """Visualize the research tree: directive -> questions -> campaigns -> experiments."""
    from .viz.tree import build_tree, render_terminal, render_dot

    project_dir = Path(directory).resolve()
    root = build_tree(project_dir, top_n=top_n, metric_override=metric_override)

    if dot_output or render_path:
        dot_str = render_dot(root)
        if dot_output:
            Path(dot_output).write_text(dot_str)
            click.echo(f"DOT written to {dot_output}")
        if render_path:
            dot_path = render_path + ".dot" if not dot_output else dot_output
            Path(dot_path).write_text(dot_str)
            fmt = "svg" if render_path.endswith(".svg") else "png"
            import subprocess
            try:
                subprocess.run(
                    ["dot", f"-T{fmt}", dot_path, "-o", render_path],
                    check=True, capture_output=True,
                )
                click.echo(f"Rendered to {render_path}")
            except FileNotFoundError:
                click.echo("graphviz 'dot' not found. Install with: brew install graphviz", err=True)
                sys.exit(1)
            finally:
                if not dot_output and Path(dot_path).exists():
                    Path(dot_path).unlink()
    else:
        click.echo(render_terminal(root, color=not no_color, top_n=top_n))


@main.command()
@click.option("--dir", "-d", "directory", default=".", help="Project directory")
@click.option("--backend", "-b", default=None, help="Agent backend: anthropic | openai | openai-compatible | deepseek")
@click.option("--model", "-m", default=None, help="Model ID override")
@click.option("--max-iterations", "-n", default=10, help="Max research iterations")
@click.option("--api-key", default=None, help="API key (or set env var)")
@click.option("--base-url", default=None, help="Base URL for openai-compatible backends")
def loop(directory: str, backend: str | None, model: str | None, max_iterations: int, api_key: str | None, base_url: str | None):
    """Run the autonomous research loop with an LLM agent."""
    project_dir = Path(directory).resolve()

    # Load config
    config_path = project_dir / "autolab.yaml"
    if config_path.exists():
        import yaml
        config = yaml.safe_load(config_path.read_text()) or {}
    else:
        click.echo("No autolab.yaml found. Run 'autolab init' first.", err=True)
        sys.exit(1)

    agent_config = config.get("agent", {})
    backend = backend or agent_config.get("backend", "anthropic")
    model = model or agent_config.get("model")
    api_key_env = agent_config.get("api_key_env")
    base_url = base_url or agent_config.get("base_url")

    # Create agent backend
    agent = _create_agent(backend, model, api_key, api_key_env, base_url, agent_config)

    from .agents.harness import AgentHarness
    harness = AgentHarness(agent, project_dir, max_tool_rounds=50)
    harness.run_loop(max_iterations=max_iterations)


# Backends that are driven by an external harness rather than by `autolab loop`.
_EXTERNAL_BACKENDS = {
    "claude-code": (
        "The 'claude-code' backend is driven by the Claude Code plugin, not by "
        "`autolab loop`.\nStart it from a Claude Code session in the project "
        "directory with:\n  /autolab:research-loop\n\nTo drive this project from "
        "the CLI instead, set agent.backend in autolab.yaml to one of: "
        "anthropic, openai, openai-compatible, deepseek."
    ),
}

# Providers reachable through the OpenAI-compatible surface, with their defaults.
_OPENAI_COMPATIBLE_PRESETS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-pro",
    },
}


def _create_agent(
    backend: str,
    model: str | None,
    api_key: str | None,
    api_key_env: str | None,
    base_url: str | None,
    agent_config: dict | None = None,
):
    """Create an agent backend from config."""
    agent_config = agent_config or {}

    if backend in _EXTERNAL_BACKENDS:
        click.echo(_EXTERNAL_BACKENDS[backend], err=True)
        sys.exit(1)

    if backend == "anthropic":
        from .agents.anthropic_agent import AnthropicAgent
        kwargs = {}
        if model:
            kwargs["model"] = model
        if api_key:
            kwargs["api_key"] = api_key
        if api_key_env:
            kwargs["api_key_env"] = api_key_env
        return AnthropicAgent(**kwargs)

    elif backend in ("openai", "openai-compatible") or backend in _OPENAI_COMPATIBLE_PRESETS:
        from .agents.openai_agent import OpenAIAgent
        preset = _OPENAI_COMPATIBLE_PRESETS.get(backend, {})
        kwargs = {}
        # Explicit config always wins over a preset default.
        resolved_model = model or preset.get("model")
        resolved_base_url = base_url or preset.get("base_url")
        resolved_key_env = api_key_env or preset.get("api_key_env")
        if resolved_model:
            kwargs["model"] = resolved_model
        if api_key:
            kwargs["api_key"] = api_key
        if resolved_key_env:
            kwargs["api_key_env"] = resolved_key_env
        if resolved_base_url:
            kwargs["base_url"] = resolved_base_url
        if "thinking" in agent_config:
            kwargs["thinking"] = bool(agent_config["thinking"])
        if agent_config.get("reasoning_effort"):
            kwargs["reasoning_effort"] = agent_config["reasoning_effort"]
        return OpenAIAgent(**kwargs)

    else:
        known = ["anthropic", "openai", "openai-compatible"]
        known += sorted(_OPENAI_COMPATIBLE_PRESETS)
        known += sorted(_EXTERNAL_BACKENDS)
        click.echo(
            f"Unknown backend: {backend}. Use one of: {', '.join(known)}", err=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
