from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from gds_etl_workbench.domain.modeling_records import ValidationCheckRecord

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER = (
    REPOSITORY_ROOT
    / "plugins"
    / "v2"
    / "gds"
    / "skills"
    / "gds"
    / "scripts"
    / "gds-local.js"
)
OBJECT_KEY = [
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
]


def run_helper(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(HELPER), *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _write_snapshot(
    session: Path,
    area: str,
    datasets: dict[str, tuple[list[str], list[dict[str, object]]]],
) -> None:
    root = session / area / f"{area}-snapshot"
    members: dict[str, bytes] = {}
    catalog_datasets = []
    for name, (key, rows) in datasets.items():
        rows_path = f"data/{name}/rows.jsonl"
        schema_path = f"schemas/{area}/{name}.schema.json"
        members[rows_path] = b"".join(
            (json.dumps(row, separators=(",", ":")) + "\n").encode() for row in rows
        )
        schema = {
            "type": "object",
            "properties": {},
            "required": [],
            "x-gds-change-set-eligible": not (
                area == "model" and name in {"model_scope", "qa_authoring_context"}
            ),
            "x-gds-canonical-key": key,
        }
        members[schema_path] = (
            json.dumps(schema, separators=(",", ":")) + "\n"
        ).encode()
        catalog_datasets.append(
            {
                "name": name,
                "record_type": name,
                "row_count": len(rows),
                "canonical_key": key,
                "rows_file": rows_path,
                "schema_file": schema_path,
            }
        )
    catalog = {
        "snapshot_kind": area,
        "sections": [{"name": "test", "datasets": catalog_datasets}],
    }
    if area == "model":
        catalog["model"] = {
            "model_id": 41,
            "model_name": "Customer Model",
            "model_revision": 8,
        }
    members["catalog.json"] = (
        json.dumps(catalog, separators=(",", ":")) + "\n"
    ).encode()
    for relative, content in members.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    inventory = [
        {
            "path": relative,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
        for relative, content in members.items()
    ]
    manifest: dict[str, object] = {
        "snapshot_kind": area,
        "snapshot_id": f"{area}-snapshot-01",
        "catalog": {
            "path": "catalog.json",
            "sha256": hashlib.sha256(members["catalog.json"]).hexdigest(),
        },
        "members": inventory,
    }
    if area == "model":
        manifest.update(model_id=41, model_name="Customer Model", model_revision=8)
    else:
        manifest["tenant_code"] = "TENANT_A"
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n")


def _physical(zone: str, name: str) -> dict[str, object]:
    return {
        "tenant_code": "TENANT_A",
        "system_code": zone.upper(),
        "connection_code": "MAIN",
        "object_schema": zone,
        "object_name": name,
        "object_type_code": "TABLE",
        "is_active": True,
    }


def _attribute(record: dict[str, object], name: str) -> dict[str, object]:
    return {**record, "attribute_name": name}


def _scope_record(
    record: dict[str, object],
    *,
    bronze_source: bool = False,
    dimensional_source: bool = False,
    logical_target: bool = False,
    dimensional_target: bool = False,
) -> dict[str, object]:
    return {
        **{field: record[field] for field in OBJECT_KEY},
        "zone_code": record["object_schema"],
        "is_bronze_source_eligible": bronze_source,
        "is_dimensional_source_eligible": dimensional_source,
        "is_logical_mapping_target_eligible": logical_target,
        "is_dimensional_mapping_target_eligible": dimensional_target,
        "model_scope_is_locked": False,
        "is_active": True,
    }


def write_ready_snapshots(
    session: Path,
    *,
    physical_source_tenant_code: str = "TENANT_A",
    physical_source_system_code: str = "SOURCE",
    silver_in_scope: bool = True,
    include_mappings: bool = True,
    include_ineligible_scope: bool = False,
    logical_target_eligible: bool = True,
    bronze_source_eligible: bool = True,
    dimensional_source_eligible: bool = True,
    dimensional_target_eligible: bool = True,
    policies_present: bool = True,
    include_generated_code: bool = True,
    include_qa_authoring_context: bool = True,
    duplicate_qa_authoring_context: bool = False,
    qa_references_generated_code: bool | None = None,
    include_profile: bool = False,
    profile_attribute_name: str = "CustomerId",
    include_unmapped_silver_attribute: bool = False,
) -> None:
    source = {
        **_physical("source", "Customer"),
        "tenant_code": physical_source_tenant_code,
        "system_code": physical_source_system_code,
    }
    silver = _physical("silver", "CustomerSilver")
    gold = _physical("gold", "CustomerGold")
    _write_snapshot(
        session,
        "metadata",
        {
            "source_object": (OBJECT_KEY, [source]),
            "source_attribute": (
                [*OBJECT_KEY, "attribute_name"],
                [_attribute(source, "CustomerId")],
            ),
            "silver_object": (OBJECT_KEY, [silver]),
            "silver_attribute": (
                [*OBJECT_KEY, "attribute_name"],
                [
                    _attribute(silver, "CustomerId"),
                    *(
                        [_attribute(silver, "Name")]
                        if include_unmapped_silver_attribute
                        else []
                    ),
                ],
            ),
            "gold_object": (OBJECT_KEY, [gold]),
            "gold_attribute": (
                [*OBJECT_KEY, "attribute_name"],
                [_attribute(gold, "CustomerKey")],
            ),
        },
    )
    scope = [_scope_record(source, bronze_source=bronze_source_eligible)]
    if silver_in_scope:
        scope.append(
            _scope_record(
                silver,
                dimensional_source=dimensional_source_eligible,
                logical_target=logical_target_eligible,
            )
        )
    scope.append(_scope_record(gold, dimensional_target=dimensional_target_eligible))
    if include_ineligible_scope:
        scope.append(_scope_record(_physical("source", "Ignored")))
    logical_source = {
        "support_source_type": "object",
        "source_object": {field: source[field] for field in OBJECT_KEY},
        "status": "active",
    }
    logical_attribute_source = {
        "support_source_type": "attribute",
        "source_attribute": {
            **{field: source[field] for field in OBJECT_KEY},
            "attribute_name": "CustomerId",
        },
        "status": "active",
    }
    dimensional_source = {
        "support_source_type": "object",
        "source_object": {field: silver[field] for field in OBJECT_KEY},
        "source_role": "dimension_source",
        "status": "active",
    }
    logical_mapping = {
        **{field: silver[field] for field in OBJECT_KEY},
        "source_system_code": "SOURCE",
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "Customer",
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic Databricks SQL.",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_package_document": {"schema_version": "1.0"},
        "object_mapping_transformation_document": {
            "schema_version": "1.0",
            "transformation_kind": "direct",
        },
        "object_mapping_status": "active",
    }
    dimensional_mapping = {
        **{field: gold[field] for field in OBJECT_KEY},
        "source_system_code": "SILVER",
        "modeled_entity_type": "dimensional_entity",
        "modeled_entity_name": "DimCustomer",
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic Databricks SQL.",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_package_document": {"schema_version": "1.0"},
        "object_mapping_transformation_document": {
            "schema_version": "1.0",
            "transformation_kind": "direct",
        },
        "object_mapping_status": "active",
    }
    generated_code = {
        **{field: silver[field] for field in OBJECT_KEY},
        "modeled_entity_type": "logical_entity",
        "artifact_type": "sql_file",
        "generated_code_content": "SELECT 1",
        "mapping_context_digest": "1" * 64,
        "source_context_digest": "2" * 64,
        "generated_code_digest": hashlib.sha256(b"SELECT 1").hexdigest(),
        "generated_code_status": "active",
        "generated_code_is_locked": False,
    }
    references_generated_code = (
        include_generated_code
        if qa_references_generated_code is None
        else qa_references_generated_code
    )
    current_code_references = (
        [
            {
                **{field: generated_code[field] for field in OBJECT_KEY},
                "modeled_entity_type": generated_code["modeled_entity_type"],
                "artifact_type": generated_code["artifact_type"],
                "generated_code_digest": generated_code["generated_code_digest"],
            }
        ]
        if references_generated_code
        else []
    )
    qa_authoring_context = {
        "tenant_code": "TENANT_A",
        "system_code": "SOURCE",
        "mapping_context_digest": "3" * 64,
        "code_context_digest": "4" * 64 if current_code_references else None,
        "mapping_target_count": 1,
        "current_code_target_count": len(current_code_references),
        "current_code_references": current_code_references,
    }
    qa_authoring_contexts = (
        [qa_authoring_context, dict(qa_authoring_context)]
        if duplicate_qa_authoring_context
        else [qa_authoring_context]
    )
    if not include_qa_authoring_context:
        qa_authoring_contexts = []
    _write_snapshot(
        session,
        "model",
        {
            "model_details": (
                [],
                [
                    {
                        "silver_model_naming_instructions": (
                            "Use PascalCase names." if policies_present else None
                        ),
                        "silver_model_audit_columns_template": (
                            {"enabled": True} if policies_present else None
                        ),
                        "gold_model_naming_instructions": (
                            "Use PascalCase names." if policies_present else None
                        ),
                        "gold_model_technical_columns_template": (
                            {"enabled": True} if policies_present else None
                        ),
                        "gold_model_audit_columns_template": (
                            {"enabled": True} if policies_present else None
                        ),
                    }
                ],
            ),
            "model_scope": (OBJECT_KEY, scope),
            "profiling_profile": (
                [*OBJECT_KEY, "attribute_name"],
                [
                    {
                        **{field: source[field] for field in OBJECT_KEY},
                        "attribute_name": profile_attribute_name,
                        "row_count": 10,
                        "non_null_count": 10,
                        "null_count": 0,
                        "blank_count": 0,
                        "distinct_count": 10,
                        "min_data_length": 1,
                        "max_data_length": 2,
                        "avg_data_length": "1.500000",
                        "percent_populated": "100.0000",
                        "percent_duplicates": "0.0000",
                        "percent_null": "0.0000",
                        "percent_blank": "0.0000",
                        "percent_distinct": "100.0000",
                    }
                ]
                if include_profile
                else [],
            ),
            "logical_entity": (
                ["logical_entity_name"],
                [
                    {
                        "logical_entity_name": "Customer",
                        "logical_entity_status": "active",
                        "sources": [logical_source],
                    }
                ],
            ),
            "logical_attribute": (
                ["logical_entity_name", "logical_attribute_name"],
                [
                    {
                        "logical_entity_name": "Customer",
                        "logical_attribute_name": "CustomerId",
                        "logical_attribute_status": "active",
                        "sources": [logical_attribute_source],
                    }
                ],
            ),
            "dimensional_entity": (
                ["dimensional_entity_name"],
                [
                    {
                        "dimensional_entity_name": "DimCustomer",
                        "dimensional_entity_status": "active",
                        "sources": [dimensional_source],
                    }
                ],
            ),
            "dimensional_attribute": (
                ["dimensional_entity_name", "dimensional_attribute_name"],
                [
                    {
                        "dimensional_entity_name": "DimCustomer",
                        "dimensional_attribute_name": "CustomerKey",
                        "dimensional_attribute_status": "active",
                        "sources": [],
                    }
                ],
            ),
            "mapping_dependency": (
                ["modeled_entity_type", "source_system_code"],
                [
                    {
                        "modeled_entity_type": "logical_entity",
                        "source_system_code": "SOURCE",
                        "mapping_source_system_dependency_status": "active",
                    },
                    {
                        "modeled_entity_type": "dimensional_entity",
                        "source_system_code": "SILVER",
                        "mapping_source_system_dependency_status": "active",
                    },
                ]
                if include_mappings
                else [],
            ),
            "mapping_object": (
                [
                    *OBJECT_KEY,
                    "source_system_code",
                    "modeled_entity_type",
                    "modeled_entity_name",
                ],
                [logical_mapping, dimensional_mapping] if include_mappings else [],
            ),
            "mapping_attribute": (
                [
                    *OBJECT_KEY,
                    "attribute_name",
                    "source_system_code",
                    "modeled_entity_type",
                    "modeled_entity_name",
                    "modeled_attribute_name",
                ],
                [
                    {
                        **{field: silver[field] for field in OBJECT_KEY},
                        "attribute_name": "CustomerId",
                        "source_system_code": "SOURCE",
                        "modeled_entity_type": "logical_entity",
                        "modeled_entity_name": "Customer",
                        "modeled_attribute_name": "CustomerId",
                        "attribute_mapping_transformation_document": {
                            "schema_version": "1.0",
                            "transformation_kind": "direct",
                        },
                        "attribute_mapping_status": "active",
                    },
                    {
                        **{field: gold[field] for field in OBJECT_KEY},
                        "attribute_name": "CustomerKey",
                        "source_system_code": "SILVER",
                        "modeled_entity_type": "dimensional_entity",
                        "modeled_entity_name": "DimCustomer",
                        "modeled_attribute_name": "CustomerKey",
                        "attribute_mapping_transformation_document": {
                            "schema_version": "1.0",
                            "transformation_kind": "direct",
                        },
                        "attribute_mapping_status": "active",
                    },
                ]
                if include_mappings
                else [],
            ),
            "generated_code": (
                OBJECT_KEY,
                [generated_code] if include_generated_code else [],
            ),
            "qa_authoring_context": (
                ["tenant_code", "system_code"],
                qa_authoring_contexts,
            ),
            "validation_group": (
                ["tenant_code", "system_code", "validation_group_name"],
                [],
            ),
            "validation_check": (
                [
                    "tenant_code",
                    "system_code",
                    "validation_group_name",
                    "validation_check_name",
                ],
                [],
            ),
        },
    )


def initialized_session(tmp_path: Path) -> Path:
    result = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert result.returncode == 0, result.stderr
    return Path(json.loads(result.stdout)["path"])


def _validation_check(
    result_type: str,
    comparison_value: str,
) -> dict[str, object]:
    return {
        "tenant_code": "TENANT_A",
        "system_code": "SOURCE",
        "validation_group_name": "literal-parity",
        "validation_check_name": "literal-parity",
        "validation_check_description": None,
        "validation_category_code": "technical.literal",
        "validation_severity": "blocking",
        "validation_query_sql": "SELECT 1",
        "validation_comparison_query_sql": None,
        "validation_result_data_type": result_type,
        "validation_comparison_operator": "equal",
        "validation_comparison_value_type": "literal",
        "validation_comparison_value": comparison_value,
        "is_active": True,
    }


def _validate_local_qa_literal(
    tmp_path: Path,
    result_type: str,
    comparison_value: str,
) -> dict[str, object]:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Validate QA literal",
        "--plan",
        '["Validate QA literal against the server contract"]',
    )
    assert added.returncode == 0, added.stderr
    changes = {
        "validation_group": [
            {
                "tenant_code": "TENANT_A",
                "system_code": "SOURCE",
                "validation_group_name": "literal-parity",
                "validation_group_description": None,
                "mapping_context_digest": "3" * 64,
                "code_context_digest": "4" * 64,
                "is_active": True,
            }
        ],
        "validation_check": [_validation_check(result_type, comparison_value)],
    }
    written = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "model",
        "--changes",
        json.dumps(changes, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    validated = run_helper("validate", "--session", str(session), "--area", "model")

    assert written.returncode == 0, written.stderr
    assert validated.returncode == 0, validated.stderr
    return json.loads(validated.stdout)


def test_qa_plugin_scenario_reaches_digest_bound_local_acceptance(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    expected_contract = json.loads(
        (
            REPOSITORY_ROOT / "plugins" / "v2" / "gds" / "tool-contract.json"
        ).read_text()
    )
    compatible = run_helper(
        "contract-check",
        "--actual",
        json.dumps(expected_contract, separators=(",", ":")),
    )
    readiness = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "qa",
        "--system-codes",
        '["SOURCE"]',
    )
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Author QA",
        "--plan",
        '["Inputs: model=model-snapshot-01@8","Author QA","Review and validate"]',
    )
    check = _validation_check("integer", "1")
    check["validation_comparison_value"] = 1
    changes = {
        "validation_group": [
            {
                "tenant_code": "TENANT_A",
                "system_code": "SOURCE",
                "validation_group_name": "literal-parity",
                "validation_group_description": None,
                "mapping_context_digest": "3" * 64,
                "code_context_digest": "4" * 64,
                "is_active": True,
            }
        ],
        "validation_check": [check],
    }
    written = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "model",
        "--changes",
        json.dumps(changes, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    assert compatible.returncode == 0, compatible.stderr
    assert json.loads(compatible.stdout)["compatible"] is True
    assert readiness.returncode == 0, readiness.stderr
    assert json.loads(readiness.stdout)["ready"] is True
    assert added.returncode == 0, added.stderr
    assert written.returncode == 0, written.stderr

    digest = json.loads(written.stdout)["digest"]
    validated = run_helper("validate", "--session", str(session), "--area", "model")
    accepted = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "model",
        "--digest",
        digest,
    )
    status = run_helper("status", "--session", str(session))

    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["valid"] is True
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(status.stdout)["current"][3] == "ready"


def test_session_sql_policy_is_absent_then_persisted_and_reused(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)

    before = run_helper("status", "--session", str(session))
    selected = run_helper(
        "sql-policy", "--session", str(session), "--policy", "essential"
    )
    after = run_helper("status", "--session", str(session))
    invalid = run_helper(
        "sql-policy", "--session", str(session), "--policy", "sometimes"
    )

    assert before.returncode == 0, before.stderr
    assert json.loads(before.stdout)["sql_policy"] is None
    assert selected.returncode == 0, selected.stderr
    assert json.loads(selected.stdout) == {"sql_policy": "essential"}
    assert after.returncode == 0, after.stderr
    assert json.loads(after.stdout)["sql_policy"] == "essential"
    assert json.loads((session / "session.json").read_text())["sql"] == "essential"
    assert invalid.returncode != 0
    assert "never, essential, or as_needed" in invalid.stderr


def _mapping_materialization_proof(
    modeled_entity_type: str = "logical_entity",
) -> dict[str, object]:
    return {
        "contract": "mapping-authoring@1.0",
        "model_id": 41,
        "model_revision": 8,
        "modeled_entity_type": modeled_entity_type,
        "target_object_id": 101,
        "source_system_id": 201,
        "profile_schema_digest": "1" * 64,
        "context_digest": "2" * 64,
        "candidate_digest": "3" * 64,
        "change_count": 2,
        "record_count": 2,
    }


def _generator_document_proof(
    modeled_entity_type: str = "logical_entity",
) -> dict[str, object]:
    return {
        "contract": "generator-document@1.0",
        "model_id": 41,
        "model_revision": 8,
        "modeled_entity_type": modeled_entity_type,
        "target_object_id": 101,
        "source_system_id": 201,
        "profile_schema_digest": "1" * 64,
        "mapping_context_digest": "2" * 64,
        "document_digest": "3" * 64,
    }


def _proof_units(*pairs: tuple[int, int]) -> str:
    return json.dumps(
        [
            {"target_object_id": target_object_id, "source_system_id": source_system_id}
            for target_object_id, source_system_id in pairs
        ],
        separators=(",", ":"),
    )


@pytest.mark.parametrize("proof_kind", ("mapping", "generator"))
def test_proof_sidecars_and_readiness_units_can_exceed_256(
    tmp_path: Path,
    proof_kind: str,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    if proof_kind == "mapping":
        command = "mapping-proof"
        target = "logical-mapping"
        sidecar = session / "tasks" / ".mapping-proofs.json"
        proof_factory = _mapping_materialization_proof
    else:
        command = "generator-proof"
        target = "logical-code"
        sidecar = session / "tasks" / ".generator-proofs.json"
        proof_factory = _generator_document_proof

    records = []
    pairs = []
    for target_object_id in range(1, 257):
        source_system_id = 1_000 + target_object_id
        proof = proof_factory()
        proof["target_object_id"] = target_object_id
        proof["source_system_id"] = source_system_id
        records.append(
            {
                "target": target,
                "model_snapshot_id": "model-snapshot-01",
                "proof": proof,
            }
        )
        pairs.append((target_object_id, source_system_id))
    sidecar.write_text(json.dumps(records, separators=(",", ":")))

    final_proof = proof_factory()
    final_proof["target_object_id"] = 257
    final_proof["source_system_id"] = 1_257
    bound = run_helper(
        command,
        "--session",
        str(session),
        "--target",
        target,
        "--proof",
        json.dumps(final_proof, separators=(",", ":")),
    )

    assert bound.returncode == 0, bound.stderr
    stored = json.loads(sidecar.read_text())
    assert len(stored) == 257
    pairs.append((257, 1_257))
    ready = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        target,
        "--proof-units",
        _proof_units(*pairs),
    )
    assert ready.returncode == 0, ready.stderr
    assert json.loads(ready.stdout)["ready"] is True


def test_mapping_readiness_requires_bound_server_materialization_proof(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)

    before = run_helper(
        "readiness", "--session", str(session), "--target", "logical-mapping"
    )
    bound = run_helper(
        "mapping-proof",
        "--session",
        str(session),
        "--target",
        "logical-mapping",
        "--proof",
        json.dumps(_mapping_materialization_proof(), separators=(",", ":")),
    )
    after = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "logical-mapping",
        "--proof-units",
        _proof_units((101, 201)),
    )

    assert before.returncode == 0, before.stderr
    assert ["mapping_contract_unavailable", 1] in json.loads(before.stdout)["blockers"]
    assert bound.returncode == 0, bound.stderr
    assert json.loads(bound.stdout) == {
        "target": "logical-mapping",
        "bound": True,
        "model_snapshot_id": "model-snapshot-01",
        "model_revision": 8,
        "target_object_id": 101,
        "source_system_id": 201,
        "candidate_digest": "3" * 64,
    }
    assert after.returncode == 0, after.stderr
    output = json.loads(after.stdout)
    assert output["ready"] is True
    assert not any(
        code == "mapping_contract_unavailable" for code, _ in output["blockers"]
    )
    stored = (session / "tasks" / ".mapping-proofs.json").read_text()
    assert "records" not in stored
    assert "changes" not in stored


def test_mapping_proof_rejects_a_different_model_revision(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    proof = _mapping_materialization_proof()
    proof["model_revision"] = 9

    result = run_helper(
        "mapping-proof",
        "--session",
        str(session),
        "--target",
        "logical-mapping",
        "--proof",
        json.dumps(proof, separators=(",", ":")),
    )

    assert result.returncode != 0
    assert "does not match the current Model Snapshot" in result.stderr
    assert not (session / "tasks" / ".mapping-proofs.json").exists()


def test_mapping_proof_is_not_reused_for_a_replaced_snapshot(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    bound = run_helper(
        "mapping-proof",
        "--session",
        str(session),
        "--target",
        "logical-mapping",
        "--proof",
        json.dumps(_mapping_materialization_proof(), separators=(",", ":")),
    )
    assert bound.returncode == 0, bound.stderr
    manifest_path = session / "model" / "model-snapshot" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["snapshot_id"] = "model-snapshot-02"
    manifest_path.write_text(json.dumps(manifest) + "\n")

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-mapping"
    )

    assert result.returncode == 0, result.stderr
    assert ["mapping_contract_unavailable", 1] in json.loads(result.stdout)["blockers"]


def test_code_readiness_requires_bound_server_generator_document_proof(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)

    before = run_helper(
        "readiness", "--session", str(session), "--target", "logical-code"
    )
    bound = run_helper(
        "generator-proof",
        "--session",
        str(session),
        "--target",
        "logical-code",
        "--proof",
        json.dumps(_generator_document_proof(), separators=(",", ":")),
    )
    after = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "logical-code",
        "--proof-units",
        _proof_units((101, 201)),
    )

    assert before.returncode == 0, before.stderr
    assert ["generator_contract_unavailable", 1] in json.loads(before.stdout)[
        "blockers"
    ]
    assert bound.returncode == 0, bound.stderr
    assert json.loads(bound.stdout) == {
        "target": "logical-code",
        "bound": True,
        "model_snapshot_id": "model-snapshot-01",
        "model_revision": 8,
        "target_object_id": 101,
        "source_system_id": 201,
        "document_digest": "3" * 64,
    }
    assert after.returncode == 0, after.stderr
    output = json.loads(after.stdout)
    assert output["ready"] is True
    assert not any(
        code == "generator_contract_unavailable" for code, _ in output["blockers"]
    )
    stored = (session / "tasks" / ".generator-proofs.json").read_text()
    assert '"document":' not in stored
    assert "executable_sources" not in stored


def test_mapping_readiness_requires_every_selected_work_unit_proof(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    first = _mapping_materialization_proof()
    second = _mapping_materialization_proof()
    second["target_object_id"] = 102
    second["source_system_id"] = 202
    units = _proof_units((101, 201), (102, 202))

    bound_first = run_helper(
        "mapping-proof",
        "--session",
        str(session),
        "--target",
        "logical-mapping",
        "--proof",
        json.dumps(first, separators=(",", ":")),
    )
    incomplete = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "logical-mapping",
        "--proof-units",
        units,
    )
    bound_second = run_helper(
        "mapping-proof",
        "--session",
        str(session),
        "--target",
        "logical-mapping",
        "--proof",
        json.dumps(second, separators=(",", ":")),
    )
    complete = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "logical-mapping",
        "--proof-units",
        units,
    )

    assert bound_first.returncode == 0, bound_first.stderr
    assert bound_second.returncode == 0, bound_second.stderr
    assert incomplete.returncode == 0, incomplete.stderr
    assert ["mapping_contract_unavailable", 1] in json.loads(incomplete.stdout)[
        "blockers"
    ]
    assert complete.returncode == 0, complete.stderr
    assert json.loads(complete.stdout)["ready"] is True


def test_code_readiness_requires_every_selected_work_unit_proof(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    first = _generator_document_proof()
    second = _generator_document_proof()
    second["target_object_id"] = 102
    second["source_system_id"] = 202
    units = _proof_units((101, 201), (102, 202))

    for proof in (first, second):
        if proof is second:
            before = run_helper(
                "readiness",
                "--session",
                str(session),
                "--target",
                "logical-code",
                "--proof-units",
                units,
            )
        bound = run_helper(
            "generator-proof",
            "--session",
            str(session),
            "--target",
            "logical-code",
            "--proof",
            json.dumps(proof, separators=(",", ":")),
        )
        assert bound.returncode == 0, bound.stderr
    after = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "logical-code",
        "--proof-units",
        units,
    )

    assert before.returncode == 0, before.stderr
    assert ["generator_contract_unavailable", 1] in json.loads(before.stdout)[
        "blockers"
    ]
    assert after.returncode == 0, after.stderr
    assert json.loads(after.stdout)["ready"] is True


def test_readiness_rejects_duplicate_proof_units(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)

    result = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "logical-mapping",
        "--proof-units",
        _proof_units((101, 201), (101, 201)),
    )

    assert result.returncode != 0
    assert "unique exact target/source pairs" in result.stderr


def test_generator_proof_rejects_a_different_model_revision(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    proof = _generator_document_proof()
    proof["model_revision"] = 9

    result = run_helper(
        "generator-proof",
        "--session",
        str(session),
        "--target",
        "logical-code",
        "--proof",
        json.dumps(proof, separators=(",", ":")),
    )

    assert result.returncode != 0
    assert "does not match the current Model Snapshot" in result.stderr
    assert not (session / "tasks" / ".generator-proofs.json").exists()


def test_readiness_supports_all_nine_targets_without_returning_rows(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    targets = (
        "logical-build",
        "silver-registration",
        "logical-mapping",
        "logical-code",
        "dimensional-build",
        "gold-registration",
        "dimensional-mapping",
        "dimensional-code",
        "qa",
    )

    outputs = {}
    for target in targets:
        arguments = ["readiness", "--session", str(session), "--target", target]
        if target == "qa":
            arguments.extend(("--system-codes", '["SOURCE"]'))
        result = run_helper(*arguments)
        assert result.returncode == 0, result.stderr
        outputs[target] = json.loads(result.stdout)
        assert outputs[target]["target"] == target
        assert "records" not in result.stdout
        assert len(outputs[target]["examples"]) <= 10

    assert outputs["logical-build"]["ready"] is True
    assert outputs["silver-registration"]["ready"] is True
    assert outputs["dimensional-build"]["ready"] is True
    assert outputs["gold-registration"]["ready"] is True
    assert ["mapping_contract_unavailable", 1] in outputs["logical-mapping"]["blockers"]
    assert ["mapping_contract_unavailable", 1] in outputs["dimensional-mapping"][
        "blockers"
    ]
    assert ["generator_contract_unavailable", 1] in outputs["logical-code"]["blockers"]
    assert ["generator_contract_unavailable", 1] in outputs["dimensional-code"][
        "blockers"
    ]
    assert outputs["qa"]["ready"] is True
    assert outputs["qa"]["counts"] == {
        "selected_systems": 1,
        "mapped_systems": 1,
        "mapping_targets": 1,
        "code_artifacts": 1,
        "validation_groups": 0,
        "validation_checks": 0,
    }


def test_qa_readiness_uses_exact_system_scope_and_code_is_optional(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, include_generated_code=False)

    result = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "qa",
        "--system-codes",
        '[" source "]',
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is True
    assert output["counts"]["mapped_systems"] == 1
    assert output["counts"]["code_artifacts"] == 0


def test_qa_readiness_counts_only_trusted_current_code_references(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(
        session,
        include_generated_code=True,
        qa_references_generated_code=False,
    )

    result = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "qa",
        "--system-codes",
        '["SOURCE"]',
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is True
    assert output["counts"]["code_artifacts"] == 0


def test_qa_readiness_reports_missing_or_ambiguous_trusted_context(
    tmp_path: Path,
) -> None:
    outputs = {}
    for name, settings in (
        ("missing", {"include_qa_authoring_context": False}),
        ("ambiguous", {"duplicate_qa_authoring_context": True}),
    ):
        session = initialized_session(tmp_path / name)
        write_ready_snapshots(session, **settings)
        result = run_helper(
            "readiness",
            "--session",
            str(session),
            "--target",
            "qa",
            "--system-codes",
            '["SOURCE"]',
        )
        assert result.returncode == 0, result.stderr
        outputs[name] = json.loads(result.stdout)

    assert ["qa_authoring_context_missing", 1] in outputs["missing"]["blockers"]
    assert ["qa_authoring_context_missing", ["SOURCE"]] in outputs["missing"][
        "examples"
    ]
    assert ["qa_authoring_context_ambiguous", 1] in outputs["ambiguous"]["blockers"]
    assert ["qa_authoring_context_ambiguous", ["SOURCE"]] in outputs["ambiguous"][
        "examples"
    ]
    assert all(output["ready"] is False for output in outputs.values())
    assert all(
        "exactly one trusted QA authoring context" in output["resolution_prompt"]
        for output in outputs.values()
    )


def test_qa_readiness_reports_each_selected_system_without_complete_mapping(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)

    result = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "qa",
        "--system-codes",
        '["SOURCE","ERP"]',
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is False
    assert ["qa_mapping_missing", 1] in output["blockers"]
    assert ["qa_mapping_missing", ["ERP"]] in output["examples"]
    assert "every selected System" in output["resolution_prompt"]


def test_qa_readiness_preserves_requested_system_order_in_examples(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, duplicate_qa_authoring_context=True)

    result = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "qa",
        "--system-codes",
        '["ERP","SOURCE","CRM"]',
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["blockers"] == [
        ["qa_authoring_context_missing", 2],
        ["qa_authoring_context_ambiguous", 1],
        ["qa_mapping_missing", 2],
    ]
    assert output["examples"] == [
        ["qa_authoring_context_missing", ["ERP"]],
        ["qa_authoring_context_ambiguous", ["SOURCE"]],
        ["qa_authoring_context_missing", ["CRM"]],
        ["qa_mapping_missing", ["ERP"]],
        ["qa_mapping_missing", ["CRM"]],
    ]


def test_qa_readiness_rejects_case_insensitive_duplicate_or_oversized_scope(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)

    duplicate = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "qa",
        "--system-codes",
        '["SOURCE","source"]',
    )
    oversized = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "qa",
        "--system-codes",
        json.dumps([f"S{index}" for index in range(1001)]),
    )

    assert duplicate.returncode != 0
    assert "unique case-insensitively" in duplicate.stderr
    assert oversized.returncode != 0
    assert "1..1000" in oversized.stderr


def test_local_model_validation_enforces_generated_code_and_qa_policies(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Author QA",
        "--plan",
        '["Inputs: model=model-snapshot-01@8","Author governed Code and QA"]',
    )
    assert added.returncode == 0, added.stderr
    changes = {
        "generated_code": [
            {
                "tenant_code": "TENANT_A",
                "system_code": "SILVER",
                "connection_code": "MAIN",
                "object_schema": "silver",
                "object_name": "CustomerSilver",
                "modeled_entity_type": "logical_entity",
                "artifact_type": "sql_file",
                "generated_code_content": "SELECT 1",
                "mapping_context_digest": "1" * 64,
                "source_context_digest": "2" * 64,
                "generated_code_digest": "0" * 64,
                "generated_code_status": "active",
                "generated_code_is_locked": False,
            }
        ],
        "validation_check": [
            {
                "tenant_code": "TENANT_A",
                "system_code": "SOURCE",
                "validation_group_name": "missing-parent",
                "validation_check_name": "query-runs",
                "validation_check_description": None,
                "validation_category_code": "technical.execution",
                "validation_severity": "blocking",
                "validation_query_sql": "SELECT 1",
                "validation_comparison_query_sql": None,
                "validation_result_data_type": "integer",
                "validation_comparison_operator": "executes_successfully",
                "validation_comparison_value_type": "none",
                "validation_comparison_value": None,
                "is_active": True,
            }
        ],
    }
    written = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "model",
        "--changes",
        json.dumps(changes, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    validated = run_helper("validate", "--session", str(session), "--area", "model")

    assert written.returncode == 0, written.stderr
    assert validated.returncode == 0, validated.stderr
    output = json.loads(validated.stdout)
    assert output["valid"] is False
    serialized = json.dumps(output["issues"])
    assert "Generated Code digest does not match its content" in serialized
    assert "Validation assertion shape is invalid" in serialized
    assert "Referenced record is not present" in serialized


def test_local_qa_date_literal_matches_server_calendar_validation(
    tmp_path: Path,
) -> None:
    check = _validation_check("date", "2026-02-30")
    with pytest.raises(ValueError, match="comparison value does not match"):
        ValidationCheckRecord.model_validate(check, strict=True)

    output = _validate_local_qa_literal(tmp_path, "date", "2026-02-30")
    assert output["valid"] is False
    assert any(
        issue[0] == "validation_check"
        and "Validation comparison value does not match its result type" in issue[2]
        for issue in output["issues"]
    )


def test_local_qa_timestamp_literal_matches_server_calendar_validation(
    tmp_path: Path,
) -> None:
    value = "2026-02-30T10:30:00Z"
    check = _validation_check("timestamp", value)
    with pytest.raises(ValueError, match="comparison value does not match"):
        ValidationCheckRecord.model_validate(check, strict=True)

    output = _validate_local_qa_literal(tmp_path, "timestamp", value)

    assert output["valid"] is False
    assert any(
        issue[0] == "validation_check"
        and "Validation comparison value does not match its result type" in issue[2]
        for issue in output["issues"]
    )


def test_local_qa_date_literal_accepts_server_basic_iso_format(
    tmp_path: Path,
) -> None:
    value = "20260831"
    ValidationCheckRecord.model_validate(_validation_check("date", value), strict=True)

    output = _validate_local_qa_literal(tmp_path, "date", value)

    assert output["valid"] is True


def test_local_qa_date_literal_accepts_server_iso_week_format(
    tmp_path: Path,
) -> None:
    value = "2026-W36-1"
    ValidationCheckRecord.model_validate(_validation_check("date", value), strict=True)

    output = _validate_local_qa_literal(tmp_path, "date", value)

    assert output["valid"] is True


def test_local_qa_timestamp_literal_rejects_non_iso_server_input(
    tmp_path: Path,
) -> None:
    value = "08/31/2026 10:30:00"
    with pytest.raises(ValueError, match="comparison value does not match"):
        ValidationCheckRecord.model_validate(
            _validation_check("timestamp", value),
            strict=True,
        )

    output = _validate_local_qa_literal(tmp_path, "timestamp", value)

    assert output["valid"] is False


@pytest.mark.parametrize(
    ("result_type", "value"),
    (
        ("date", "2024-02-29"),
        ("date", "20240229"),
        ("date", "2024-W09-4"),
        ("date", "2024W094"),
        ("date", "2024-W09"),
        ("date", "2023-02-29"),
        ("date", "2024-W54-1"),
        ("date", "2024-060"),
        ("date", "0000-01-01"),
        ("date", "2026-08-31\n"),
        ("timestamp", "2026-08-31"),
        ("timestamp", "20260831"),
        ("timestamp", "2026-W36-1T10:30:00Z"),
        ("timestamp", "2026W361T103000Z"),
        ("timestamp", "2026-08-31 10:30:00"),
        ("timestamp", "2026-08-31😀10:30:00"),
        ("timestamp", "2026-08-31T24:00:00"),
        ("timestamp", "9999-12-31T24:00:00"),
        ("timestamp", "2026-08-31T10:30:00+05:30:15.5"),
        ("timestamp", "2026-08-31T10:30:00+05:60"),
        ("timestamp", "2026-08-31T10:30:00+24:00"),
        ("timestamp", "2026-08-31T10:30.5"),
        ("timestamp", "2026-08-31T"),
        ("timestamp", "2026-02-30T10:30:00Z"),
        ("timestamp", "08/31/2026 10:30:00"),
        ("timestamp", "2026-08-31T10:30:00Z\n"),
    ),
)
def test_local_qa_iso_literal_matrix_matches_server(
    tmp_path: Path,
    result_type: str,
    value: str,
) -> None:
    try:
        ValidationCheckRecord.model_validate(
            _validation_check(result_type, value),
            strict=True,
        )
        server_valid = True
    except ValueError:
        server_valid = False

    output = _validate_local_qa_literal(tmp_path, result_type, value)

    assert output["valid"] is server_valid


def test_code_readiness_prompts_for_required_applied_mapping(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, include_mappings=False)

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-code"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert ["applied_mapping_missing", 1] in output["blockers"]
    assert (
        "Complete and Apply the matching Logical or Dimensional Mapping"
        in output["resolution_prompt"]
    )


def test_logical_build_uses_only_bronze_eligible_scope(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, include_ineligible_scope=True)

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-build"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is True
    assert output["counts"]["scoped_objects"] == 1
    assert not any(
        blocker[0] == "catalog_object_missing" for blocker in output["blockers"]
    )


@pytest.mark.parametrize(
    ("include_profile", "profile_attribute_name", "profiled", "unprofiled"),
    (
        (False, "CustomerId", 0, 1),
        (True, "CustomerId", 1, 0),
        (True, "MissingAttribute", 0, 1),
    ),
)
def test_logical_build_reports_bounded_profile_coverage(
    tmp_path: Path,
    include_profile: bool,
    profile_attribute_name: str,
    profiled: int,
    unprofiled: int,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(
        session,
        include_profile=include_profile,
        profile_attribute_name=profile_attribute_name,
    )

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-build"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is True
    assert output["counts"] == {
        "scoped_objects": 1,
        "scoped_attributes": 1,
        "profiled_attributes": profiled,
        "unprofiled_attributes": unprofiled,
        "catalog_objects": 3,
        "attributes": 3,
    }


def test_logical_support_uses_authoritative_physical_tenant_and_system(
    tmp_path: Path,
) -> None:
    authoritative_source = {
        "tenant_code": "PHYSICAL_TENANT",
        "system_code": "GDS",
        "connection_code": "MAIN",
        "object_schema": "source",
        "object_name": "Customer",
    }
    references = {
        "authoritative": authoritative_source,
        "session_tenant": {**authoritative_source, "tenant_code": "TENANT_A"},
        "upstream_system": {**authoritative_source, "system_code": "SOURCE"},
    }

    outputs = {}
    for name, source_object in references.items():
        session = initialized_session(tmp_path / name)
        write_ready_snapshots(
            session,
            physical_source_tenant_code=authoritative_source["tenant_code"],
            physical_source_system_code=authoritative_source["system_code"],
        )
        added = run_helper(
            "task-add",
            "--session",
            str(session),
            "--area",
            "model",
            "--title",
            "Validate Logical support identity",
            "--plan",
            '["Validate exact physical Object reference"]',
        )
        logical_entity = {
            "logical_entity_name": "IdentityCheck",
            "logical_entity_status": "active",
            "sources": [
                {
                    "support_source_type": "object",
                    "source_object": source_object,
                    "status": "active",
                }
            ],
        }
        written = run_helper(
            "upsert",
            "--session",
            str(session),
            "--area",
            "model",
            "--dataset",
            "logical_entity",
            "--record",
            json.dumps(logical_entity, separators=(",", ":")),
            "--expected-digest",
            "empty",
        )
        validated = run_helper(
            "validate", "--session", str(session), "--area", "model"
        )

        assert added.returncode == 0, added.stderr
        assert written.returncode == 0, written.stderr
        assert validated.returncode == 0, validated.stderr
        outputs[name] = json.loads(validated.stdout)

    assert outputs["authoritative"]["valid"] is True
    for name in ("session_tenant", "upstream_system"):
        assert outputs[name]["valid"] is False
        assert any(
            issue[0] == "logical_entity"
            and "model_scope_reference_invalid" in issue[2]
            and "eligible Bronze source" in issue[2]
            for issue in outputs[name]["issues"]
        )


def test_local_model_validation_rejects_missing_physical_attribute(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Validate Profile Attribute",
        "--plan",
        '["Validate exact physical Attribute references"]',
    )
    assert added.returncode == 0, added.stderr
    source = _physical("source", "Customer")
    profile = {
        **{field: source[field] for field in OBJECT_KEY},
        "attribute_name": "MissingAttribute",
        "row_count": 1,
        "non_null_count": 1,
        "null_count": 0,
    }
    written = run_helper(
        "upsert",
        "--session",
        str(session),
        "--area",
        "model",
        "--dataset",
        "profiling_profile",
        "--record",
        json.dumps(profile, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    validated = run_helper("validate", "--session", str(session), "--area", "model")

    assert written.returncode == 0, written.stderr
    assert validated.returncode == 0, validated.stderr
    output = json.loads(validated.stdout)
    assert output["valid"] is False
    assert any(
        issue[0] == "profiling_profile"
        and "model_scope_reference_invalid" in issue[2]
        and "eligible Bronze source" in issue[2]
        for issue in output["issues"]
    )


def test_local_model_validation_rejects_unmapped_silver_sibling_attribute(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, include_unmapped_silver_attribute=True)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Validate Dimensional Attribute",
        "--plan",
        '["Validate applied Logical Mapping Attribute eligibility"]',
    )
    assert added.returncode == 0, added.stderr
    silver = _physical("silver", "CustomerSilver")
    dimensional_attribute = {
        "dimensional_entity_name": "DimCustomer",
        "dimensional_attribute_name": "Name",
        "dimensional_attribute_status": "active",
        "sources": [
            {
                "support_source_type": "attribute",
                "source_attribute": {
                    **{field: silver[field] for field in OBJECT_KEY},
                    "attribute_name": "Name",
                },
            }
        ],
    }
    written = run_helper(
        "upsert",
        "--session",
        str(session),
        "--area",
        "model",
        "--dataset",
        "dimensional_attribute",
        "--record",
        json.dumps(dimensional_attribute, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    validated = run_helper("validate", "--session", str(session), "--area", "model")

    assert written.returncode == 0, written.stderr
    assert validated.returncode == 0, validated.stderr
    output = json.loads(validated.stdout)
    assert output["valid"] is False
    assert any(
        issue[0] == "dimensional_attribute"
        and "model_scope_reference_invalid" in issue[2]
        and "applied Logical Mapping" in issue[2]
        for issue in output["issues"]
    )


def test_registration_allows_independently_optional_model_policies(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, policies_present=False)

    outputs = {}
    for target in ("silver-registration", "gold-registration"):
        result = run_helper("readiness", "--session", str(session), "--target", target)
        assert result.returncode == 0, result.stderr
        outputs[target] = json.loads(result.stdout)

    assert outputs["silver-registration"]["ready"] is True
    assert outputs["gold-registration"]["ready"] is True
    assert all(
        blocker[0] != "policy_missing"
        for output in outputs.values()
        for blocker in output["blockers"]
    )


def test_mapping_readiness_groups_missing_scope_and_gives_exact_prompt(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, silver_in_scope=False)

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-mapping"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert ["scope_missing", 1] in output["blockers"]
    assert "authorized scope owner" in output["resolution_prompt"]
    assert output["examples"][0][0] == "scope_missing"


def test_mapping_readiness_requires_layer_target_eligibility(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, logical_target_eligible=False)

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-mapping"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert ["scope_missing", 1] in output["blockers"]
    assert "authorized scope owner" in output["resolution_prompt"]


def test_logical_mapping_requires_bronze_eligible_executable_source(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, bronze_source_eligible=False)

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-mapping"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert ["lineage_missing", 1] in output["blockers"]


def test_dimensional_mapping_uses_dimensional_source_and_target_eligibility(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(
        session,
        dimensional_source_eligible=False,
        dimensional_target_eligible=False,
    )

    result = run_helper(
        "readiness", "--session", str(session), "--target", "dimensional-mapping"
    )

    assert result.returncode == 0, result.stderr
    blockers = json.loads(result.stdout)["blockers"]
    assert ["scope_missing", 1] in blockers
    assert ["lineage_missing", 1] in blockers


def test_dimensional_build_requires_dimensional_source_eligible_scope(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session, dimensional_source_eligible=False)

    result = run_helper(
        "readiness", "--session", str(session), "--target", "dimensional-build"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is False
    assert output["counts"]["silver_targets"] == 1
    assert ["scope_missing", 1] in output["blockers"]
    assert not any(
        blocker[0] == "silver_target_missing" for blocker in output["blockers"]
    )


def test_readiness_reports_stale_inputs_without_reading_rows(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["stale"] = ["model"]
    state_path.write_text(json.dumps(state) + "\n")

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-build"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is False
    assert ["snapshot_stale", 1] in output["blockers"]
    assert output["counts"] == {}


def test_local_stage_preparation_trace_uses_no_duplicate_setup_calls(
    tmp_path: Path,
) -> None:
    """Exercise local helper choreography only, not evidence reads or remote MCP calls."""
    session = initialized_session(tmp_path)
    write_ready_snapshots(session)
    commands: list[str] = []

    def call(command: str, *arguments: str) -> dict[str, object]:
        commands.append(command)
        result = run_helper(command, "--session", str(session), *arguments)
        assert result.returncode == 0, result.stderr
        assert len(result.stdout.encode()) <= 4096
        return json.loads(result.stdout)

    ready = call("readiness", "--target", "silver-registration")
    assert ready["ready"] is True
    inputs = {item[0]: item[1:] for item in ready["inputs"]}
    plan = [
        f"Inputs: metadata={inputs['metadata'][0]}; "
        f"model={inputs['model'][0]}@{inputs['model'][1]}",
        "Prepare one selected Silver Object record for governed handoff",
    ]
    call(
        "task-add",
        "--area",
        "metadata",
        "--title",
        "Register Vendor Silver",
        "--plan",
        json.dumps(plan, separators=(",", ":")),
    )
    target = _physical("silver", "VendorSilver")
    batch = call(
        "upsert-batch",
        "--area",
        "metadata",
        "--changes",
        json.dumps({"silver_object": [target]}, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    review = call("review", "--area", "metadata")
    validation = call("validate", "--area", "metadata")
    assert review["digest"] == validation["digest"] == batch["digest"]
    accepted = call(
        "accept", "--area", "metadata", "--digest", str(validation["digest"])
    )
    assert accepted["stage"]["records"] == 1
    call(
        "draft-cache",
        "--area",
        "metadata",
        "--id",
        "00000000-0000-4000-8000-000000000123",
        "--revision",
        "0",
        "--status",
        "active",
    )
    reconciled = call(
        "reconcile",
        "--area",
        "metadata",
        "--server",
        "{}",
    )
    assert reconciled["classification"] == "non_overlap"
    assert commands == [
        "readiness",
        "task-add",
        "upsert-batch",
        "review",
        "validate",
        "accept",
        "draft-cache",
        "reconcile",
    ]
    assert "inspect" not in commands
