from __future__ import annotations

from copy import deepcopy

from gds_etl_workbench.tools.change_sets.validation import validate_metadata_documents


def test_validation_accepts_full_id_free_record_with_resolved_natural_keys() -> None:
    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=_foundation(),
        staged_rows_by_dataset={"copy_group": [_copy_group()]},
    )

    assert result.valid is True
    assert result.phase == "complete"
    assert result.candidate_digest is not None
    assert result.issues == ()


def test_validation_returns_authoritative_action_review() -> None:
    current = _foundation()
    update = _copy_group()
    deactivate = _copy_group()
    deactivate["copy_group_name"] = "DEACTIVATE"
    unchanged = _copy_group()
    unchanged["copy_group_name"] = "UNCHANGED"
    reactivate = _copy_group()
    reactivate["copy_group_name"] = "REACTIVATE"
    reactivate["is_active"] = False
    current["copy_group"] = [update, deactivate, unchanged, reactivate]

    updated = deepcopy(update)
    updated["copy_group_description"] = "changed"
    deactivated = deepcopy(deactivate)
    deactivated["is_active"] = False
    inserted = _copy_group()
    inserted["copy_group_name"] = "INSERTED"
    reactivated = deepcopy(reactivate)
    reactivated["is_active"] = True

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={
            "copy_group": [updated, deactivated, unchanged, inserted, reactivated]
        },
    )

    assert result.valid is True
    assert len(result.action_review) == 1
    summary = result.action_review[0]
    assert summary.dataset == "copy_group"
    assert (
        summary.insert_count,
        summary.update_count,
        summary.deactivate_count,
        summary.reactivate_count,
        summary.no_change_count,
    ) == (1, 1, 1, 1, 1)
    assert [item.action for item in summary.keys] == [
        "update",
        "deactivate",
        "no_change",
        "insert",
        "reactivate",
    ]
    assert summary.keys[0].natural_key == {
        "tenant_code": "DEMO",
        "system_code": "CRM",
        "copy_group_name": "CUSTOMERS",
    }
    assert summary.keys_truncated is False


def test_action_review_limits_natural_keys_but_keeps_counts() -> None:
    records: list[dict[str, object]] = []
    for index in range(101):
        record = _copy_group()
        record["copy_group_name"] = f"GROUP_{index:03d}"
        records.append(record)

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=_foundation(),
        staged_rows_by_dataset={"copy_group": records},
    )

    assert result.valid is True
    assert result.action_review[0].insert_count == 101
    assert len(result.action_review[0].keys) == 100
    assert result.action_review[0].keys_truncated is True


def test_validation_stops_at_duplicate_unique_keys() -> None:
    duplicate = _copy_group()
    duplicate["copy_group_description"] = "second"

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=_foundation(),
        staged_rows_by_dataset={"copy_group": [_copy_group(), duplicate]},
    )

    assert result.valid is False
    assert result.phase == "uniqueness"
    assert result.issues[0].code == "duplicate_unique_key"


def test_validation_uses_published_unicode_lowercase_without_case_folding() -> None:
    first = _copy_group()
    first["copy_group_name"] = "Straße"
    second = _copy_group()
    second["copy_group_name"] = "STRASSE"

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=_foundation(),
        staged_rows_by_dataset={"copy_group": [first, second]},
    )

    assert result.valid is True


def test_validation_rejects_cross_tenant_changes_before_references() -> None:
    record = _copy_group()
    record["tenant_code"] = "OTHER"

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=_foundation(),
        staged_rows_by_dataset={"copy_group": [record]},
    )

    assert result.valid is False
    assert result.phase == "tenant_scope"
    assert result.issues[0].fields == ("tenant_code",)


def test_validation_reports_missing_natural_key_reference() -> None:
    current = deepcopy(_foundation())
    current["system"] = []

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"copy_group": [_copy_group()]},
    )

    assert result.valid is False
    assert result.phase == "references"
    assert result.issues[0].code == "reference_not_found"
    assert result.issues[0].fields == ("system_code",)


def test_validation_allows_copy_group_control_without_optional_member_group() -> None:
    current = _foundation()
    current["copy_group"] = [_copy_group()]

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={
            "copy_group_control": [
                {
                    "tenant_code": "DEMO",
                    "system_code": "CRM",
                    "copy_group_name": "CUSTOMERS",
                    "member_group_name": None,
                    "copy_group_control_initial_load_date": None,
                    "copy_group_control_last_run_time": None,
                    "copy_group_control_last_run_value": None,
                }
            ]
        },
    )

    assert result.valid is True


def test_validation_still_rejects_partially_populated_nullable_connection_key() -> None:
    current = _foundation()
    current["tenant"][0]["gds_connection_tenant_code"] = "DEMO"

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"copy_group": [_copy_group()]},
    )

    assert result.valid is False
    assert result.phase == "schema"


def test_validation_allows_object_inside_tenant_discovery_scope() -> None:
    current = _foundation()
    current["tenant"].append(
        {
            "tenant_code": "GLOBAL",
            "project_code": "PROJECT",
            "tenant_name": "Global",
            "tenant_description": None,
            "tenant_catalog": "global",
            "gds_admin_catalog": "global_admin",
            "gds_connection_tenant_code": None,
            "gds_connection_system_code": None,
            "gds_connection_code": None,
            "tenant_visibility": "global",
            "is_active": True,
        }
    )
    current["connection_type"] = [
        {
            "connection_type_code": "POSTGRES",
            "connection_type_name": "Postgres",
            "connection_type_description": None,
            "is_active": True,
        }
    ]
    current["connection"] = [
        {
            "tenant_code": "GLOBAL",
            "system_code": "CRM",
            "connection_code": "GDS",
            "connection_name": "GDS",
            "connection_type_code": "POSTGRES",
            "has_foreign_catalog": False,
            "foreign_catalog": None,
            "is_global_data_store": True,
            "is_active": True,
        }
    ]
    current["zone"] = [
        {
            "zone_code": "bronze",
            "zone_name": "Bronze",
            "zone_description": None,
            "is_active": True,
        }
    ]
    current["object_type"] = [
        {
            "object_type_code": "TABLE",
            "object_type_name": "Table",
            "object_type_description": None,
            "is_active": True,
        }
    ]
    current["tenant_metadata_discovery_scope"] = [
        {
            "scope_tenant_code": "DEMO",
            "connection_tenant_code": "GLOBAL",
            "connection_system_code": "CRM",
            "connection_code": "GDS",
            "zone_code": "bronze",
            "object_schema": "demo",
            "is_active": True,
        }
    ]
    record = _object_record(object_schema="demo", tenant_code="DEMO")

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"bronze_object": [record]},
    )

    assert result.valid is True

    record["object_schema"] = "another_tenant"
    denied = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"bronze_object": [record]},
    )
    assert denied.valid is False
    assert denied.phase == "tenant_scope"


def test_validation_rejects_change_to_existing_locked_object() -> None:
    current = _foundation()
    locked_object = _object_record(object_schema="public", tenant_code="DEMO")
    locked_object["is_locked"] = True
    current["bronze_object"] = [locked_object]
    staged_object = deepcopy(locked_object)
    staged_object["object_description"] = "Changed"

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"bronze_object": [staged_object]},
    )

    assert result.valid is False
    assert result.phase == "locks"
    assert result.issues[0].code == "object_locked"
    assert result.issues[0].dataset == "bronze_object"


def test_validation_rejects_attribute_change_under_locked_object() -> None:
    current = _foundation()
    locked_object = _object_record(object_schema="public", tenant_code="DEMO")
    locked_object["is_locked"] = True
    current["bronze_object"] = [locked_object]

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"bronze_attribute": [_attribute_record()]},
    )

    assert result.valid is False
    assert result.phase == "locks"
    assert result.issues[0].code == "object_locked"
    assert result.issues[0].dataset == "bronze_attribute"


def test_validation_allows_attribute_change_under_unlocked_object() -> None:
    current = _foundation()
    current["bronze_object"] = [
        _object_record(object_schema="public", tenant_code="DEMO")
    ]

    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"bronze_attribute": [_attribute_record()]},
    )

    assert result.valid is True


def _foundation() -> dict[str, list[dict[str, object]]]:
    return {
        "project": [
            {
                "project_code": "PROJECT",
                "project_name": "Project",
                "project_description": None,
                "is_active": True,
            }
        ],
        "tenant": [
            {
                "tenant_code": "DEMO",
                "project_code": "PROJECT",
                "tenant_name": "Demo",
                "tenant_description": None,
                "tenant_catalog": "demo",
                "gds_admin_catalog": "admin",
                "gds_connection_tenant_code": None,
                "gds_connection_system_code": None,
                "gds_connection_code": None,
                "tenant_visibility": "private",
                "is_active": True,
            }
        ],
        "system_type": [
            {
                "system_type_code": "DATABASE",
                "system_type_name": "Database",
                "system_type_description": None,
                "is_active": True,
            }
        ],
        "system": [
            {
                "system_code": "CRM",
                "system_name": "CRM",
                "system_description": None,
                "system_type_code": "DATABASE",
                "is_active": True,
            }
        ],
        "connection_type": [
            {
                "connection_type_code": "POSTGRES",
                "connection_type_name": "Postgres",
                "connection_type_description": None,
                "is_active": True,
            }
        ],
        "connection": [
            {
                "tenant_code": "DEMO",
                "system_code": "CRM",
                "connection_code": "GDS",
                "connection_name": "GDS",
                "connection_type_code": "POSTGRES",
                "has_foreign_catalog": False,
                "foreign_catalog": None,
                "is_global_data_store": False,
                "is_active": True,
            }
        ],
        "object_type": [
            {
                "object_type_code": "TABLE",
                "object_type_name": "Table",
                "object_type_description": None,
                "is_active": True,
            }
        ],
        "zone": [
            {
                "zone_code": "bronze",
                "zone_name": "Bronze",
                "zone_description": None,
                "is_active": True,
            }
        ],
    }


def _copy_group() -> dict[str, object]:
    return {
        "tenant_code": "DEMO",
        "system_code": "CRM",
        "copy_group_name": "CUSTOMERS",
        "copy_group_description": None,
        "is_member_group_required": False,
        "is_active": True,
    }


def _object_record(
    *, object_schema: str, tenant_code: str = "GLOBAL"
) -> dict[str, object]:
    return {
        "tenant_code": tenant_code,
        "system_code": "CRM",
        "connection_code": "GDS",
        "object_schema": object_schema,
        "object_name": "customers",
        "fc_object_schema": None,
        "fc_object_name": None,
        "object_transformation": None,
        "object_description": None,
        "batch_attribute_name": None,
        "object_type_code": "TABLE",
        "zone_code": "bronze",
        "is_locked": False,
        "is_active": True,
    }


def _attribute_record() -> dict[str, object]:
    return {
        "tenant_code": "DEMO",
        "system_code": "CRM",
        "connection_code": "GDS",
        "object_schema": "public",
        "object_name": "customers",
        "attribute_name": "customer_id",
        "fc_attribute_name": None,
        "attribute_ordinal_position": 1,
        "attribute_description": None,
        "attribute_data_type": "bigint",
        "attribute_nullability": False,
        "attribute_custom_code": None,
        "is_surrogate_key": False,
        "is_natural_key": True,
        "is_meta_data": False,
        "is_masking_required": False,
        "is_mapped": True,
        "is_purge": False,
        "is_active": True,
    }
