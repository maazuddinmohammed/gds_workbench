"""Replace downloaded Atlas packages locally; no sign-in, network or workspace writes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import cast


def replace_packages(parent: Path, plugin_zip: Path, connector_zip: Path) -> None:
    """Validate both ZIPs, then replace whole folders with rollback and retained backups."""
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("Use the existing Atlas installation folder.")
    parent = parent.resolve()
    for name in ("atlas", "atlas-connector"):
        folder = parent / name
        if folder.is_symlink() or not folder.is_dir() or (folder / ".atlas").exists():
            raise ValueError(
                "Expected installed packages, separate from working folders."
            )
    lock = parent / ".atlas-setup.lock"
    try:
        with lock.open("x", encoding="utf-8") as stream:
            stream.write("Atlas package update in progress\n")
    except FileExistsError as error:
        raise ValueError(
            "Another Atlas setup may be running. See the installation guide."
        ) from error
    staging: Path | None = None
    backup: Path | None = None
    moved: list[str] = []
    promoted: list[str] = []
    try:
        staging = Path(tempfile.mkdtemp(prefix=".atlas-download-", dir=parent))
        for name, archive_path in (
            ("atlas", plugin_zip),
            ("atlas-connector", connector_zip),
        ):
            with zipfile.ZipFile(archive_path) as archive:
                entries = archive.infolist()
                if (
                    not entries
                    or len(entries) > 5000
                    or sum(item.file_size for item in entries) > 64 * 1024 * 1024
                ):
                    raise ValueError("Atlas ZIP exceeds package limits.")
                seen: set[str] = set()
                for entry in entries:
                    path = PurePosixPath(entry.filename)
                    kind = stat.S_IFMT(entry.external_attr >> 16)
                    parts = entry.filename.rstrip("/").split("/")
                    if (
                        path.is_absolute()
                        or not parts
                        or parts[0] != name
                        or any(
                            not part
                            or part in {".", ".."}
                            or ":" in part
                            or "\\" in part
                            or part.endswith((".", " "))
                            or part.startswith(".")
                            for part in parts
                        )
                        or kind not in {0, stat.S_IFREG, stat.S_IFDIR}
                        or entry.file_size > 16 * 1024 * 1024
                        or entry.filename.casefold() in seen
                    ):
                        raise ValueError(
                            "Atlas ZIP contains unsafe or duplicate paths."
                        )
                    seen.add(entry.filename.casefold())
                    if entry.is_dir():
                        continue
                    relative = PurePosixPath(*parts[1:])
                    if name == "atlas-connector":
                        allowed = str(relative) in {
                            "README.md",
                            "atlas-connector.cjs",
                            "install.cjs",
                            "update.py",
                            "package.json",
                            "package-lock.json",
                        }
                    else:
                        families = {
                            "skills": {".md"},
                            "references": {".md"},
                            "templates": {".md"},
                            "docs": {".md", ".png"},
                            "scripts": {".js", ".ps1", ".sh", ".py"},
                            "contracts": {".json"},
                            "workbench": {".js", ".html", ".css", ".md", ".json"},
                            "assets": {".json"},
                        }
                        allowed = str(relative) in {"plugin.json", "mcp.json"} or (
                            len(relative.parts) > 1
                            and relative.suffix
                            in families.get(relative.parts[0], set())
                        )
                    if not allowed:
                        raise ValueError(
                            "Atlas ZIP contains files outside the release package."
                        )
                    target = staging.joinpath(*parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        archive.open(entry) as source,
                        target.open("xb") as destination,
                    ):
                        shutil.copyfileobj(source, destination)
                    target.chmod(0o755 if target.suffix == ".sh" else 0o644)
            manifest_file = "plugin.json" if name == "atlas" else "package.json"
            decoded: object = json.loads(
                (staging / name / manifest_file).read_text(encoding="utf-8")
            )
            if not isinstance(decoded, dict):
                raise ValueError("Atlas ZIP has an invalid manifest.")
            manifest = cast(dict[str, object], decoded)
            if manifest.get("name") != name or not isinstance(
                manifest.get("version"), str
            ):
                raise ValueError("Atlas ZIP has an invalid manifest.")
            required = (
                ("mcp.json", "skills/atlas/SKILL.md")
                if name == "atlas"
                else (
                    "atlas-connector.cjs",
                    "install.cjs",
                    "update.py",
                    "package-lock.json",
                )
            )
            if not all((staging / name / file).is_file() for file in required):
                raise ValueError("Atlas ZIP is incomplete.")
        backup = Path(tempfile.mkdtemp(prefix="atlas-backup-", dir=parent))
        try:
            for name in ("atlas", "atlas-connector"):
                os.replace(parent / name, backup / name)
                moved.append(name)
                os.replace(staging / name, parent / name)
                promoted.append(name)
        except OSError:
            # Move only files this attempt created; recover both old packages.
            for name in reversed(moved):
                if name in promoted:
                    os.replace(parent / name, staging / name)
                os.replace(backup / name, parent / name)
            raise
        print(
            "Atlas packages replaced. Run npm run setup in atlas-connector, "
            "then restart your clients."
        )
        print(
            f"Previous packages retained in {backup.name}. Remove that backup after verification."
        )
    finally:
        if staging is not None:
            shutil.rmtree(staging)
        lock.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin", type=Path, required=True, help="downloaded plugin ZIP"
    )
    parser.add_argument(
        "--connector", type=Path, required=True, help="downloaded connector ZIP"
    )
    args = parser.parse_args()
    try:
        replace_packages(
            Path(__file__).resolve().parent.parent,
            args.plugin.resolve(),
            args.connector.resolve(),
        )
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        print(
            "Atlas update failed. Existing packages or their backup were retained. "
            "Check the installation guide; no working files were changed."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
