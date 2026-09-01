from __future__ import annotations

import hashlib

from gds_etl_workbench.domain.modeling_records import GeneratedCodeRecord
from gds_etl_workbench.tools.snapshots.model.selection import (
    _QA_AUTHORING_CONTEXT_SQL,
    _build_qa_authoring_context_records,
)


def _target_context(
    *,
    object_name: str,
    mapping_digest: str,
    source_digest: str,
    source_system_codes: tuple[str, ...] = ("ERP",),
) -> dict[str, object]:
    return {
        "modeled_entity_type": "logical_entity",
        "object_id": 99,
        "source_system_count": len(source_system_codes),
        "mapping_context_digest": mapping_digest,
        "source_context_digest": source_digest,
        "source_context": {
            "target": {
                "tenant_code": "Northwind",
                "system_code": "Silver",
                "connection_code": "Lakehouse",
                "object_schema": "Curated",
                "object_name": object_name,
            },
            "source_systems": [
                {"system_code": system_code} for system_code in source_system_codes
            ],
        },
    }


def _code(
    *,
    object_name: str,
    mapping_digest: str,
    source_digest: str,
    content: str,
    artifact_type: str = "python_file",
) -> GeneratedCodeRecord:
    return GeneratedCodeRecord.model_validate(
        {
            "tenant_code": "Northwind",
            "system_code": "Silver",
            "connection_code": "Lakehouse",
            "object_schema": "Curated",
            "object_name": object_name,
            "modeled_entity_type": "logical_entity",
            "artifact_type": artifact_type,
            "generated_code_content": content,
            "mapping_context_digest": mapping_digest,
            "source_context_digest": source_digest,
            "generated_code_digest": hashlib.sha256(content.encode()).hexdigest(),
            "generated_code_status": "active",
            "generated_code_is_locked": False,
        }
    )


def test_qa_snapshot_context_is_artifact_neutral_and_excludes_stale_code() -> None:
    current_mapping = "a" * 64
    current_source = "b" * 64
    rows = [
        _target_context(
            object_name="Customers",
            mapping_digest=current_mapping,
            source_digest=current_source,
        ),
        _target_context(
            object_name="Orders",
            mapping_digest="c" * 64,
            source_digest="d" * 64,
        ),
    ]
    current = _code(
        object_name="Customers",
        mapping_digest=current_mapping,
        source_digest=current_source,
        content="print('current')",
    )
    stale = _code(
        object_name="Orders",
        mapping_digest="e" * 64,
        source_digest="d" * 64,
        content="print('stale')",
    )

    records = _build_qa_authoring_context_records(rows, (current, stale))

    assert len(records) == 1
    record = records[0]
    assert record.tenant_code == "Northwind"
    assert record.system_code == "ERP"
    assert record.mapping_target_count == 2
    assert record.current_code_target_count == 1
    assert record.code_context_digest is not None
    assert [
        reference.model_dump(mode="json")
        for reference in record.current_code_references
    ] == [
        {
            "tenant_code": "Northwind",
            "system_code": "Silver",
            "connection_code": "Lakehouse",
            "object_schema": "Curated",
            "object_name": "Customers",
            "modeled_entity_type": "logical_entity",
            "artifact_type": "python_file",
            "generated_code_digest": current.generated_code_digest,
        }
    ]


def test_qa_snapshot_context_represents_no_current_code_without_fabricating_digest() -> (
    None
):
    records = _build_qa_authoring_context_records(
        [
            _target_context(
                object_name="Customers",
                mapping_digest="a" * 64,
                source_digest="b" * 64,
                source_system_codes=("ERP", "CRM"),
            )
        ],
        (),
    )

    assert [
        (record.system_code, record.mapping_target_count) for record in records
    ] == [
        ("CRM", 1),
        ("ERP", 1),
    ]
    assert all(record.code_context_digest is None for record in records)
    assert all(record.current_code_references == () for record in records)


def test_qa_snapshot_selection_requests_artifact_neutral_mapping_context() -> None:
    assert _QA_AUTHORING_CONTEXT_SQL.count("NULL") == 2
    assert (
        _QA_AUTHORING_CONTEXT_SQL.count("workflow.list_code_generation_target_context")
        == 2
    )
