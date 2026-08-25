"""Build a deterministic, clean GDS Agent Plugin archive."""

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


PLUGIN_ROOT = Path(__file__).parent / "v1" / "gds"
DIST_ROOT = Path(__file__).parent / "v1" / "dist"
IGNORED_NAMES = frozenset({".DS_Store", "__pycache__"})
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _plugin_version() -> str:
    manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("plugin.json has no valid version")
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
        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise ValueError("MCP URL must include a valid hostname") from error
        labels = ascii_hostname.split(".")
        if len(ascii_hostname) > 253 or any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in labels
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


def _mcp_manifest_bytes(mcp_url: str) -> bytes:
    manifest = json.loads((PLUGIN_ROOT / "mcp.json").read_text(encoding="utf-8"))
    try:
        server = manifest["mcpServers"]["gds-workbench"]
    except (KeyError, TypeError) as error:
        raise ValueError("mcp.json has no gds-workbench server") from error
    if not isinstance(server, dict):
        raise ValueError("mcp.json gds-workbench server must be an object")
    server["url"] = _validate_mcp_url(mcp_url)
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build(output: Path, *, mcp_url: str | None = None) -> tuple[int, str]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing archive: {output}")
    files = _source_files()
    overridden_mcp_manifest = (
        _mcp_manifest_bytes(mcp_url) if mcp_url is not None else None
    )
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
            mode = 0o755 if source.suffix in {".sh", ".ps1"} else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            content = (
                overridden_mcp_manifest
                if relative == Path("mcp.json") and overridden_mcp_manifest is not None
                else source.read_bytes()
            )
            archive.writestr(info, content, compresslevel=9)
    content = output.read_bytes()
    return len(content), hashlib.sha256(content).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--mcp-url",
        help="HTTPS /mcp endpoint embedded only in the output archive",
    )
    arguments = parser.parse_args()
    if arguments.mcp_url is not None and arguments.output is None:
        parser.error("--mcp-url requires --output")
    version = _plugin_version()
    output = arguments.output or DIST_ROOT / f"gds-agent-plugin-{version}.zip"
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
