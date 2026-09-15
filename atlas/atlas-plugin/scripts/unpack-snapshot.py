"""Extract a verified Snapshot ZIP into an empty directory without following archive links."""

from __future__ import annotations

import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath


def unpack(archive: Path, destination: Path) -> None:
    if not destination.is_dir() or destination.is_symlink() or any(destination.iterdir()):
        raise ValueError("Snapshot extraction requires an empty regular directory")
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if (
            not members
            or len(members) > 4096
            or sum(item.file_size for item in members) > 512 * 1024**2
        ):
            raise ValueError("Snapshot archive exceeds extraction limits")
        seen: set[str] = set()
        for member in members:
            name = member.filename.rstrip("/")
            parts = name.split("/")
            mode = member.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if (
                not name
                or name in seen
                or name.startswith("/")
                or "\\" in name
                or ":" in name
                or any(part in {"", ".", ".."} for part in parts)
                or kind not in {0, stat.S_IFREG, stat.S_IFDIR}
            ):
                raise ValueError("Snapshot archive has an unsafe, duplicate or nonregular member")
            seen.add(name)
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.filename).parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as incoming, target.open("xb") as outgoing:
                count = 0
                while chunk := incoming.read(1024 * 1024):
                    count += len(chunk)
                    if count > member.file_size:
                        raise ValueError("Snapshot member exceeds declared size")
                    outgoing.write(chunk)
                if count != member.file_size:
                    raise ValueError("Snapshot member size mismatch")


if __name__ == "__main__":
    try:
        unpack(Path(sys.argv[1]), Path(sys.argv[2]))
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from None
