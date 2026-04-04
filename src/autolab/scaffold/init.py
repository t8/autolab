"""Project scaffolding — creates a new Autolab research project."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape


def scaffold_project(project_dir: Path, goal: str) -> None:
    """Create a new Autolab research project directory."""
    env = Environment(
        loader=PackageLoader("autolab.scaffold", "templates"),
        autoescape=select_autoescape(),
        keep_trailing_newline=True,
    )

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "campaigns").mkdir(exist_ok=True)
    (project_dir / "experiments").mkdir(exist_ok=True)
    (project_dir / "analysis").mkdir(exist_ok=True)
    (project_dir / ".autolab").mkdir(exist_ok=True)

    context = {"goal": goal}

    templates = {
        "autolab.yaml.j2": "autolab.yaml",
        "research_plan.yaml.j2": "research_plan.yaml",
        "CLAUDE.md.j2": "CLAUDE.md",
        "RESEARCH_PROMPT.md.j2": "RESEARCH_PROMPT.md",
        "JOURNAL.md.j2": "JOURNAL.md",
        "DISCOVERIES.md.j2": "DISCOVERIES.md",
        "example_campaign.yaml.j2": "campaigns/000_example.yaml",
        "state.json.j2": ".autolab/state.json",
        "gitignore.j2": ".gitignore",
    }

    for template_name, output_name in templates.items():
        tmpl = env.get_template(template_name)
        output_path = project_dir / output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(tmpl.render(**context))
