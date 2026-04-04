"""Tests for Claude Code plugin structure — verify files exist and are well-formed."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


PLUGIN_DIR = Path(__file__).parent.parent / "plugin"


def test_plugin_json_valid():
    path = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["name"] == "autolab"
    assert "version" in data
    assert "description" in data


def test_commands_exist():
    commands_dir = PLUGIN_DIR / "commands"
    expected = ["research-loop.md", "campaign.md", "status.md", "literature.md", "discover.md"]
    for name in expected:
        path = commands_dir / name
        assert path.exists(), f"Missing command: {name}"
        content = path.read_text()
        assert "---" in content  # has frontmatter


def test_skills_exist():
    skills_dir = PLUGIN_DIR / "skills"
    expected = ["research-loop", "campaign-design", "discovery-writing"]
    for name in expected:
        skill_file = skills_dir / name / "SKILL.md"
        assert skill_file.exists(), f"Missing skill: {name}/SKILL.md"
        content = skill_file.read_text()
        assert "---" in content  # has frontmatter
        # Check frontmatter has required fields
        assert "name:" in content
        assert "description:" in content
        assert "version:" in content


def test_hooks_valid():
    hooks_file = PLUGIN_DIR / "hooks" / "hooks.json"
    assert hooks_file.exists()
    data = json.loads(hooks_file.read_text())
    assert "hooks" in data
    assert len(data["hooks"]) >= 1
    assert data["hooks"][0]["event"] == "Stop"


def test_scripts_executable():
    scripts_dir = PLUGIN_DIR / "scripts"
    for script in ["setup-research-loop.sh", "check-progress.sh"]:
        path = scripts_dir / script
        assert path.exists(), f"Missing script: {script}"
        # Check shebang
        content = path.read_text()
        assert content.startswith("#!/")


def test_stop_hook_executable():
    hook = PLUGIN_DIR / "hooks" / "research-stop-hook.sh"
    assert hook.exists()
    content = hook.read_text()
    assert content.startswith("#!/")
    assert "autolab-loop.local.md" in content  # references state file
