"""Safe, deterministic SQL artifact download rendering."""

import re
import unicodedata
from io import BytesIO
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from .contracts import (
    MAX_BULK_SQL_BYTES,
    MAX_SELECTED_ARTIFACTS,
    GeneratedSqlArtifactDetail,
    SqlArtifactBundleLimitExceededError,
    SqlArtifactDownload,
)

_MAX_BULK_ZIP_BYTES = MAX_BULK_SQL_BYTES + (256 * 1024)


def _safe_filename_component(value: str, *, fallback: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    component = re.sub(r"[^A-Za-z0-9_.-]+", "_", ascii_value).strip("._-").lower()
    component = component[:60].rstrip("._-")
    if not component:
        return fallback
    if component in {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }:
        return f"_{component}"
    return component


def sql_artifact_filename(
    artifact: GeneratedSqlArtifactDetail | SqlArtifactDownload,
) -> str:
    filename = _safe_filename_component(
        artifact.artifact_name,
        fallback=f"artifact_{artifact.generated_sql_artifact_id}",
    )
    return filename if filename.endswith(".sql") else f"{filename}.sql"


def build_selected_sql_zip(artifacts: tuple[SqlArtifactDownload, ...]) -> bytes:
    if not 1 <= len(artifacts) <= MAX_SELECTED_ARTIFACTS:
        raise SqlArtifactBundleLimitExceededError()
    identifiers = tuple(item.generated_sql_artifact_id for item in artifacts)
    if len(set(identifiers)) != len(identifiers):
        raise SqlArtifactBundleLimitExceededError()
    if sum(item.generated_sql_byte_count for item in artifacts) > MAX_BULK_SQL_BYTES:
        raise SqlArtifactBundleLimitExceededError()

    buffer = BytesIO()
    with ZipFile(
        buffer,
        mode="w",
        compression=ZIP_STORED,
        allowZip64=False,
    ) as archive:
        used_names: set[str] = set()
        for artifact in artifacts:
            filename = sql_artifact_filename(artifact)
            if filename.casefold() in used_names:
                stem = filename[:-4] if filename.endswith(".sql") else filename
                filename = f"{stem}__{artifact.generated_sql_artifact_id}.sql"
            used_names.add(filename.casefold())
            member = ZipInfo(
                filename,
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            member.compress_type = ZIP_STORED
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, artifact.generated_sql.encode())
    content = buffer.getvalue()
    if len(content) > _MAX_BULK_ZIP_BYTES:
        raise SqlArtifactBundleLimitExceededError()
    return content
