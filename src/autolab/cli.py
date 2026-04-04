"""Autolab CLI — init, run, status, results."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .core.loop import ResearchLoop
from .metrics.db import ResultsDB


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
@click.option("--direction", "-d", "direction", default="maximize", type=click.Choice(["maximize", "minimize"]))
def results(db_path: str, campaign_name: str | None, metric_name: str | None, limit: int, direction: str):
    """Query experiment results."""
    if not Path(db_path).exists():
        click.echo("No results database found.")
        return

    db = ResultsDB(db_path)

    if metric_name:
        rows = db.best_by_metric(metric_name, direction, campaign_name, limit)
        click.echo(f"\nTop {len(rows)} by {metric_name} ({direction}):")
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
@click.option("--backend", "-b", default=None, help="Agent backend: anthropic | openai | openai-compatible")
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
    agent = _create_agent(backend, model, api_key, api_key_env, base_url)

    from .agents.harness import AgentHarness
    harness = AgentHarness(agent, project_dir, max_tool_rounds=50)
    harness.run_loop(max_iterations=max_iterations)


def _create_agent(
    backend: str,
    model: str | None,
    api_key: str | None,
    api_key_env: str | None,
    base_url: str | None,
):
    """Create an agent backend from config."""
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

    elif backend in ("openai", "openai-compatible"):
        from .agents.openai_agent import OpenAIAgent
        kwargs = {}
        if model:
            kwargs["model"] = model
        if api_key:
            kwargs["api_key"] = api_key
        if api_key_env:
            kwargs["api_key_env"] = api_key_env
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAIAgent(**kwargs)

    else:
        click.echo(f"Unknown backend: {backend}. Use: anthropic, openai, openai-compatible", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
