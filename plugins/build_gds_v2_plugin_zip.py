"""Build a deterministic Agent Plugins 1.0 GDS archive."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import stat
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


PLUGIN_ROOT = Path(__file__).parent / "v2" / "gds"
DIST_ROOT = Path(__file__).parent / "v2" / "dist"
IGNORED_NAMES = frozenset({".DS_Store", "__pycache__"})
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
PLUGIN_FIELDS = frozenset(
    {
        "$schema",
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
)
AUTHOR_FIELDS = frozenset({"name", "email", "url"})
PLUGIN_NAME = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return document


def _plugin_version() -> str:
    manifest = _read_json_object(PLUGIN_ROOT / "plugin.json", "plugin.json")
    if manifest.get("$schema") != PLUGIN_SCHEMA:
        raise ValueError("plugin.json must target Agent Plugins 1.0.0")
    name = manifest.get("name")
    if (
        not isinstance(name, str)
        or not 1 <= len(name) <= 64
        or not PLUGIN_NAME.fullmatch(name)
    ):
        raise ValueError("plugin.json has no valid Agent Plugins name")
    if name != PLUGIN_ROOT.name:
        raise ValueError("plugin.json name must match the plugin directory")
    unknown_fields = sorted(set(manifest) - PLUGIN_FIELDS)
    if unknown_fields:
        raise ValueError(
            "plugin.json contains non-portable fields: " + ", ".join(unknown_fields)
        )
    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("plugin.json has no valid semantic version")
    for field in ("description", "homepage", "repository", "license"):
        if field in manifest and not isinstance(manifest[field], str):
            raise ValueError(f"plugin.json {field} must be a string")
    author = manifest.get("author")
    if author is not None:
        if not isinstance(author, dict):
            raise ValueError("plugin.json author must be an object")
        if set(author) - AUTHOR_FIELDS or any(
            not isinstance(value, str) for value in author.values()
        ):
            raise ValueError("plugin.json author contains invalid fields")
    keywords = manifest.get("keywords")
    if keywords is not None and (
        not isinstance(keywords, list)
        or any(not isinstance(keyword, str) for keyword in keywords)
    ):
        raise ValueError("plugin.json keywords must be an array of strings")
    extensions = manifest.get("extensions")
    if extensions is not None and (
        not isinstance(extensions, dict)
        or any(not isinstance(value, dict) for value in extensions.values())
    ):
        raise ValueError("plugin.json extensions must contain namespace objects")
    return version


def _source_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(PLUGIN_ROOT.rglob("*")):
        if any(part in IGNORED_NAMES for part in path.relative_to(PLUGIN_ROOT).parts):
            continue
        if path.is_symlink():
            raise ValueError(f"plugin contains a symbolic link: {path}")
        if path.is_file():
            files.append(path)
    if not files:
        raise ValueError("plugin contains no files")
    return files


def _validate_mcp_url(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or any(character.isspace() for character in value)
    ):
        raise ValueError("MCP URL must not be empty or contain whitespace")
    try:
        endpoint = urlsplit(value)
        hostname = endpoint.hostname
        endpoint.port
    except ValueError as error:
        raise ValueError(f"invalid MCP URL: {error}") from error
    if endpoint.scheme != "https":
        raise ValueError("MCP URL must use https")
    if not hostname:
        raise ValueError("MCP URL must include a hostname")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if re.fullmatch(r"[0-9.]+", hostname):
            raise ValueError("MCP URL must include a valid hostname")
        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise ValueError("MCP URL must include a valid hostname") from error
        if len(ascii_hostname) > 253 or any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in ascii_hostname.split(".")
        ):
            raise ValueError("MCP URL must include a valid hostname")
    if endpoint.username is not None or endpoint.password is not None:
        raise ValueError("MCP URL must not contain credentials")
    if endpoint.path != "/mcp":
        raise ValueError("MCP URL path must be exactly /mcp")
    if endpoint.query or "?" in value:
        raise ValueError("MCP URL must not contain a query")
    if endpoint.fragment or "#" in value:
        raise ValueError("MCP URL must not contain a fragment")
    return value


def _mcp_manifest_bytes(mcp_url: str | None) -> bytes:
    manifest = _read_json_object(PLUGIN_ROOT / "mcp.json", "mcp.json")
    if set(manifest) != {"$schema", "mcpServers"}:
        raise ValueError("mcp.json may contain only $schema and mcpServers")
    if manifest.get("$schema") != MCP_SCHEMA:
        raise ValueError("mcp.json must target Agent Plugins 1.0.0")
    servers = manifest.get("mcpServers")
    if not isinstance(servers, dict) or set(servers) != {"gds-workbench"}:
        raise ValueError("mcp.json must contain only the gds-workbench server")
    try:
        server = servers["gds-workbench"]
    except (KeyError, TypeError) as error:
        raise ValueError("mcp.json has no gds-workbench server") from error
    if not isinstance(server, dict):
        raise ValueError("mcp.json gds-workbench server must be an object")
    if set(server) != {"type", "url"}:
        raise ValueError("mcp.json gds-workbench server may contain only type and url")
    if server.get("type") != "streamable-http":
        raise ValueError("mcp.json gds-workbench server must use streamable-http")
    packaged_url = server.get("url") if mcp_url is None else mcp_url
    if not isinstance(packaged_url, str):
        raise ValueError("mcp.json gds-workbench server must include a URL")
    server["url"] = _validate_mcp_url(packaged_url)
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build(output: Path, *, mcp_url: str | None = None) -> tuple[int, str]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing archive: {output}")
    _plugin_version()
    files = _source_files()
    mcp_manifest = _mcp_manifest_bytes(mcp_url)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for source in files:
            relative = source.relative_to(PLUGIN_ROOT)
            archive_name = (Path(PLUGIN_ROOT.name) / relative).as_posix()
            info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = relative.parts[:3] == ("skills", "gds", "scripts")
            info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            content = (
                mcp_manifest if relative == Path("mcp.json") else source.read_bytes()
            )
            archive.writestr(info, content, compresslevel=9)
    content = output.read_bytes()
    return len(content), hashlib.sha256(content).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--mcp-url", help="HTTPS /mcp endpoint embedded only in the archive"
    )
    arguments = parser.parse_args()
    if arguments.mcp_url is not None and arguments.output is None:
        parser.error("--mcp-url requires --output")
    output = arguments.output or DIST_ROOT / f"gds-agent-plugin-{_plugin_version()}.zip"
    try:
        size, digest = build(output.resolve(), mcp_url=arguments.mcp_url)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"archive={output.resolve()}")
    print(f"size_bytes={size}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
