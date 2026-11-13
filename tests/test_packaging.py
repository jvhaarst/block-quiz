"""The plugin manifests, the project metadata and the skill have to agree."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def load(name):
    return json.loads((ROOT / ".claude-plugin" / name).read_text(encoding="utf-8"))


def project_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"$', text, re.MULTILINE).group(1)


def test_plugin_version_matches_the_project_version():
    # Claude Code only offers an update when this version changes.
    assert load("plugin.json")["version"] == project_version()


def test_plugin_points_at_a_folder_with_the_skill():
    for skill_dir in load("plugin.json")["skills"]:
        assert (ROOT / skill_dir / "SKILL.md").is_file()


def test_marketplace_lists_the_plugin_under_the_same_name():
    plugin = load("plugin.json")
    listed = load("marketplace.json")["plugins"]

    assert [(p["name"], p["source"]) for p in listed] == [(plugin["name"], "./")]


def test_skill_name_matches_the_plugin_name():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert (
        re.search(r"^name: (.+)$", skill, re.MULTILINE).group(1)
        == (load("plugin.json")["name"])
    )
