"""Safe, deterministic SQL artifact download rendering."""

import json
import re
import unicodedata
from io import BytesIO
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from pydantic import JsonValue

from .contracts import (
    MAX_BULK_SQL_BYTES,
    MAX_EXPORT_ARTIFACTS,
    MAX_SELECTED_ARTIFACTS,
    GeneratedSqlArtifactDetail,
    SqlArtifactBundleLimitExceededError,
    SqlArtifactDownload,
)

_MAX_BULK_ZIP_BYTES = MAX_BULK_SQL_BYTES + (MAX_EXPORT_ARTIFACTS * 256)


def _safe_filename_component(value: str, *, fallback: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    component = re.sub(r"[^A-Za-z0-9_.-]+", "_", ascii_value).strip("._-").lower()
    component = component[:60].rstrip("._-")
    if not component:
        return fallback
    if component.split(".", 1)[0] in {
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


def build_sql_zip(
    artifacts: tuple[SqlArtifactDownload, ...],
    *,
    max_artifacts: int = MAX_SELECTED_ARTIFACTS,
    manifest: dict[str, JsonValue] | None = None,
) -> bytes:
    if not 1 <= len(artifacts) <= min(max_artifacts, MAX_EXPORT_ARTIFACTS):
        raise SqlArtifactBundleLimitExceededError()
    identifiers = tuple(item.generated_sql_artifact_id for item in artifacts)
    if len(set(identifiers)) != len(identifiers):
        raise SqlArtifactBundleLimitExceededError()
    total_bytes = sum(item.generated_sql_byte_count for item in artifacts)
    if total_bytes > MAX_BULK_SQL_BYTES:
        raise SqlArtifactBundleLimitExceededError()

    buffer = BytesIO()
    with ZipFile(
        buffer,
        mode="w",
        compression=ZIP_STORED,
        allowZip64=False,
    ) as archive:
        used_names: set[str] = set()
        manifest_artifacts: list[JsonValue] = []
        for artifact in artifacts:
            filename = sql_artifact_filename(artifact)
            stem = filename[:-4]
            collision = 1
            while filename.casefold() in used_names:
                suffix = "" if collision == 1 else f"_{collision}"
                filename = f"{stem}__{artifact.generated_sql_artifact_id}{suffix}.sql"
                collision += 1
            used_names.add(filename.casefold())
            member = ZipInfo(
                filename,
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            member.compress_type = ZIP_STORED
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, artifact.generated_sql.encode())
            if manifest is not None:
                manifest_artifacts.append(
                    {
                        "filename": filename,
                        "generated_sql_artifact_id": artifact.generated_sql_artifact_id,
                        "artifact_name": artifact.artifact_name,
                        "target": artifact.target.model_dump(mode="json"),
                        "source_system_codes": list(artifact.source_system_codes),
                        "artifact_is_current": artifact.artifact_is_current,
                    }
                )
        if manifest is not None:
            content = json.dumps(
                {**manifest, "artifacts": manifest_artifacts},
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            ).encode()
            if total_bytes + len(content) > MAX_BULK_SQL_BYTES:
                raise SqlArtifactBundleLimitExceededError()
            member = ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = ZIP_STORED
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, content)
    content = buffer.getvalue()
    if len(content) > _MAX_BULK_ZIP_BYTES:
        raise SqlArtifactBundleLimitExceededError()
    return content
