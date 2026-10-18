"""Lossless, deterministic exports of saved Validation SQL and comparison criteria."""

import json
from io import BytesIO
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from gds_etl_workbench.domain.errors import InvalidRequestError

from .contracts import (
    ExportValidationRequest,
    ValidationBundleLimitExceededError,
    ValidationExportEmptyError,
    ValidationLedger,
)

MAX_EXPORT_CHECKS = 5_000
MAX_EXPORT_BYTES = 32 * 1024 * 1024
MAX_ZIP_BYTES = MAX_EXPORT_BYTES + (MAX_EXPORT_CHECKS * 512)


def build_validation_zip(
    ledger: ValidationLedger, command: ExportValidationRequest
) -> tuple[bytes, int]:
    groups = tuple(
        sorted(
            (
                group
                for group in ledger.groups
                if group.is_active and group.modeled_entity_type in (None, command.entity_type)
            ),
            key=lambda group: (
                group.system_code.casefold(),
                group.validation_group_name.casefold(),
                group.validation_group_id,
            ),
        )
    )
    check_count = sum(check.is_active for group in groups for check in group.checks)
    if check_count == 0:
        raise ValidationExportEmptyError()
    if check_count > MAX_EXPORT_CHECKS:
        raise ValidationBundleLimitExceededError()
    files: list[tuple[str, bytes]] = []
    manifest_groups: list[dict[str, object]] = []
    used_ids: set[int] = set()
    total_bytes = 0
    for group in groups:
        manifest_checks: list[dict[str, object]] = []
        for check in sorted(
            (check for check in group.checks if check.is_active),
            key=lambda check: (check.validation_check_name.casefold(), check.validation_check_id),
        ):
            if check.validation_check_id in used_ids:
                raise InvalidRequestError(
                    "The Validation export contains ambiguous check identities."
                )
            used_ids.add(check.validation_check_id)
            filename = f"check_{check.validation_check_id}.sql"
            sql = check.validation_query_sql.encode()
            files.append((filename, sql))
            total_bytes += len(sql)
            comparison_filename = None
            if check.validation_comparison_query_sql is not None:
                comparison_filename = f"check_{check.validation_check_id}__comparison.sql"
                comparison_sql = check.validation_comparison_query_sql.encode()
                files.append((comparison_filename, comparison_sql))
                total_bytes += len(comparison_sql)
            if total_bytes > MAX_EXPORT_BYTES:
                raise ValidationBundleLimitExceededError()
            manifest_checks.append(
                {
                    **check.model_dump(
                        mode="json",
                        exclude={"validation_query_sql", "validation_comparison_query_sql"},
                    ),
                    "query_file": filename,
                    "comparison_query_file": comparison_filename,
                }
            )
        manifest_groups.append(
            {**group.model_dump(mode="json", exclude={"checks"}), "checks": manifest_checks}
        )
    manifest = json.dumps(
        {
            "format_version": "1.0",
            "scope": "active_validation_checks",
            "project_id": ledger.project_id,
            "project_revision": ledger.project_revision,
            "entity_type": command.entity_type,
            "groups": manifest_groups,
        },
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode()
    if total_bytes + len(manifest) > MAX_EXPORT_BYTES:
        raise ValidationBundleLimitExceededError()
    files.append(("manifest.json", manifest))
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_STORED, allowZip64=False) as archive:
        for filename, content in files:
            member = ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = ZIP_STORED
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, content)
    content = buffer.getvalue()
    if len(content) > MAX_ZIP_BYTES:
        raise ValidationBundleLimitExceededError()
    return content, check_count
