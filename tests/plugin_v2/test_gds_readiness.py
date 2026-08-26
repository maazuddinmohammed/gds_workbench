from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


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
                area == "model" and name == "model_scope"
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
    silver_in_scope: bool = True,
    include_mappings: bool = True,
    include_ineligible_scope: bool = False,
    logical_target_eligible: bool = True,
    bronze_source_eligible: bool = True,
    dimensional_source_eligible: bool = True,
    dimensional_target_eligible: bool = True,
    policies_present: bool = True,
) -> None:
    source = _physical("source", "Customer")
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
                [_attribute(silver, "CustomerId")],
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
        },
    )


def initialized_session(tmp_path: Path) -> Path:
    result = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert result.returncode == 0, result.stderr
    return Path(json.loads(result.stdout)["path"])


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


def test_readiness_supports_all_eight_targets_without_returning_rows(
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
    )

    outputs = {}
    for target in targets:
        result = run_helper("readiness", "--session", str(session), "--target", target)
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
