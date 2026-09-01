from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds"
SCHEMA_ROOT = Path(__file__).with_name("agent_plugins_1_0_0")
SKILL_FIELDS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_portable_manifests_match_the_official_agent_plugins_1_0_0_schemas() -> None:
    plugin_schema = _json(SCHEMA_ROOT / "plugin.schema.json")
    mcp_schema = _json(SCHEMA_ROOT / "mcp.schema.json")
    plugin = _json(PLUGIN_ROOT / "plugin.json")
    mcp = _json(PLUGIN_ROOT / "mcp.json")

    Draft202012Validator.check_schema(plugin_schema)
    Draft202012Validator.check_schema(mcp_schema)
    Draft202012Validator(plugin_schema).validate(plugin)
    Draft202012Validator(mcp_schema).validate(mcp)
    assert plugin["$schema"].rsplit("/", 2)[-2] == mcp["$schema"].rsplit("/", 2)[-2]

    servers = mcp["mcpServers"]
    assert isinstance(servers, dict)
    for server in servers.values():
        assert isinstance(server, dict)
        if server["type"] not in {"streamable-http", "sse"}:
            continue
        endpoint = urlsplit(server["url"])
        assert endpoint.scheme == "https"
        assert endpoint.hostname
        assert endpoint.username is None
        assert endpoint.password is None
        assert not endpoint.fragment


def test_plugin_package_paths_and_skill_discovery_are_portable() -> None:
    assert (PLUGIN_ROOT / "plugin.json").is_file()
    assert (PLUGIN_ROOT / "mcp.json").is_file()
    assert not any(path.is_symlink() for path in PLUGIN_ROOT.rglob("*"))

    skills_root = PLUGIN_ROOT / "skills"
    skill_directories = sorted(path for path in skills_root.iterdir() if path.is_dir())
    assert [path.name for path in skill_directories] == ["gds"]
    for skill_directory in skill_directories:
        document = (skill_directory / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\n(?P<frontmatter>.*?)\n---\n", document, re.DOTALL)
        assert match is not None
        frontmatter = dict(
            line.split(": ", maxsplit=1)
            for line in match.group("frontmatter").splitlines()
        )
        assert set(frontmatter) <= SKILL_FIELDS
        assert frontmatter["name"] == skill_directory.name
        assert re.fullmatch(r"(?!.*--)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", frontmatter["name"])
        assert 1 <= len(frontmatter["name"]) <= 64
        assert 1 <= len(frontmatter["description"]) <= 1024
