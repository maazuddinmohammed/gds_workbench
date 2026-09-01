from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, LiteralString

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
)
from gds_etl_workbench.tools.modeling.code_generation_authoring import (
    register_code_generation_authoring_tools,
)
from gds_etl_workbench.tools.modeling.mapping_authoring import (
    register_mapping_authoring_tools,
)

PROFILE_DIGEST = "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"


@dataclass
class FakeDatabase:
    context: dict[str, object]
    generator_references: dict[str, object] = field(default_factory=dict)
    generator_target_context: dict[str, object] | None = field(
        default_factory=lambda: {
            "mapping_context_digest": "c" * 64,
            "source_context_digest": "d" * 64,
        }
    )
    audit_records: list[ToolCallLogRecord] = field(default_factory=list)
    isolations: list[ReadIsolation] = field(default_factory=list)

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def readiness(self) -> ReadinessRecord:
        return ReadinessRecord(ready=True, code="ready")

    async def expire_tenant_locks(self) -> int:
        return 0

    async def append_tool_call_log(self, record: ToolCallLogRecord) -> None:
        self.audit_records.append(record)

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        self.isolations.append(isolation)
        yield FakeReadTransaction(self)


@dataclass
class FakeReadTransaction:
    database: FakeDatabase

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "FROM model.model\n" in query:
            assert parameters == (7,)
            return {
                "model_id": 7,
                "tenant_id": 3,
                "model_name": "Customer Model",
                "model_revision": 4,
            }
        if "mapping_authoring_context_v1" in query:
            return {"context": self.database.context}
        if "code_generation_reference_context_v1" in query:
            return {"references": self.database.generator_references}
        if "code_generation_target_context_v1" in query:
            assert parameters == (7, "logical_entity", 101)
            return self.database.generator_target_context
        raise AssertionError("unexpected query")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError("unexpected query")


def _server(database: FakeDatabase) -> MCPServer[None]:
    identity = IdentityProvider(AuthMode.DEV)
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="mapping-authoring-test", middleware=[audit])
    register_mapping_authoring_tools(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
    )
    register_code_generation_authoring_tools(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
    )
    return server


@pytest.mark.asyncio
async def test_mapping_authoring_context_is_bounded_and_digest_bound() -> None:
    database = FakeDatabase(_context())

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "get_model_mapping_authoring_context",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )

    assert result.is_error is False
    assert result.structured_content is not None
    content = result.structured_content
    assert content["model_revision"] == 4
    assert content["route"] == "logical_to_silver"
    assert content["profile"]["schema_digest"] == PROFILE_DIGEST
    assert content["proof"] == {
        "model_revision": 4,
        "target_object_id": 101,
        "source_system_id": 201,
        "profile_schema_digest": PROFILE_DIGEST,
        "context_digest": content["context_digest"],
        "header_count": 1,
        "target_attribute_count": 1,
    }
    assert len(content["context_digest"]) == 64
    assert database.isolations[-1] is ReadIsolation.REPEATABLE_READ
    assert len(database.audit_records) == 1


@pytest.mark.asyncio
async def test_mapping_candidate_materializes_complete_natural_key_changes() -> None:
    database = FakeDatabase(_context())

    async with Client(_server(database)) as client:
        prepared = await client.call_tool(
            "get_model_mapping_authoring_context",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )
        assert prepared.structured_content is not None
        result = await client.call_tool(
            "validate_and_materialize_mapping_candidate",
            {
                "model_id": 7,
                "model_revision": 4,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
                "context_digest": prepared.structured_content["context_digest"],
                "candidate": _candidate(),
            },
        )

    assert result.is_error is False
    assert result.structured_content is not None
    content = result.structured_content
    assert content["model_revision"] == 4
    assert content["context_digest"] == prepared.structured_content["context_digest"]
    assert content["proof"] == {
        "contract": "mapping-authoring@1.0",
        "model_id": 7,
        "model_revision": 4,
        "modeled_entity_type": "logical_entity",
        "target_object_id": 101,
        "source_system_id": 201,
        "profile_schema_digest": PROFILE_DIGEST,
        "context_digest": content["context_digest"],
        "candidate_digest": content["candidate_digest"],
        "change_count": 2,
        "record_count": 2,
    }
    assert [change["dataset"] for change in content["changes"]] == [
        "mapping_object",
        "mapping_attribute",
    ]
    object_record = content["changes"][0]["records"][0]
    assert object_record["tenant_code"] == "DEMO"
    assert object_record["object_name"] == "customer"
    assert object_record["source_system_code"] == "CRM"
    assert object_record["modeled_entity_name"] == "Customer"
    attribute_record = content["changes"][1]["records"][0]
    assert attribute_record["attribute_name"] == "customer_id"
    assert attribute_record["modeled_attribute_name"] == "CustomerId"
    materialize_audit = database.audit_records[-1]
    assert materialize_audit.tool_name == "validate_and_materialize_mapping_candidate"
    assert "candidate" not in materialize_audit.input_metadata


@pytest.mark.asyncio
async def test_mapping_candidate_rejects_stale_context_digest() -> None:
    database = FakeDatabase(_context())

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "validate_and_materialize_mapping_candidate",
            {
                "model_id": 7,
                "model_revision": 4,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
                "context_digest": "0" * 64,
                "candidate": _candidate(),
            },
        )

    assert result.is_error is True
    assert "prepare it again" in result.content[0].text


@pytest.mark.asyncio
async def test_mapping_candidate_rejects_secret_shaped_content_safely() -> None:
    database = FakeDatabase(_context())
    candidate = _candidate()
    package = candidate["package"]
    assert isinstance(package, dict)
    package["artifact_generation_instructions"] = "Use password=supersecretvalue"

    async with Client(_server(database)) as client:
        prepared = await client.call_tool(
            "get_model_mapping_authoring_context",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )
        assert prepared.structured_content is not None
        result = await client.call_tool(
            "validate_and_materialize_mapping_candidate",
            {
                "model_id": 7,
                "model_revision": 4,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
                "context_digest": prepared.structured_content["context_digest"],
                "candidate": candidate,
            },
        )

    assert result.is_error is True
    assert "secret-shaped" in result.content[0].text
    assert "supersecretvalue" not in result.content[0].text


@pytest.mark.asyncio
async def test_mapping_candidate_rejects_source_attribute_outside_context() -> None:
    database = FakeDatabase(_context())
    candidate = _candidate()
    mappings = candidate["attribute_mappings"]
    assert isinstance(mappings, list) and isinstance(mappings[0], dict)
    transformation = mappings[0]["transformation"]
    assert isinstance(transformation, dict)
    source_columns = transformation["source_columns"]
    assert isinstance(source_columns, list) and isinstance(source_columns[0], dict)
    source_columns[0]["source_attribute_id"] = 999

    async with Client(_server(database)) as client:
        prepared = await client.call_tool(
            "get_model_mapping_authoring_context",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )
        assert prepared.structured_content is not None
        result = await client.call_tool(
            "validate_and_materialize_mapping_candidate",
            {
                "model_id": 7,
                "model_revision": 4,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
                "context_digest": prepared.structured_content["context_digest"],
                "candidate": candidate,
            },
        )

    assert result.is_error is True
    assert "source Attribute is outside" in result.content[0].text


@pytest.mark.asyncio
async def test_mapping_candidate_rejects_incomplete_target_coverage() -> None:
    context = _context()
    target = context["target"]
    assert isinstance(target, dict)
    attributes = target["attributes"]
    assert isinstance(attributes, list)
    attributes.append(
        {
            "attribute_id": 302,
            "attribute_name": "customer_name",
            "data_type": "STRING",
            "nullable": True,
            "ordinal": 2,
            "definition": "Customer name.",
        }
    )
    database = FakeDatabase(context)

    async with Client(_server(database)) as client:
        prepared = await client.call_tool(
            "get_model_mapping_authoring_context",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )
        assert prepared.structured_content is not None
        result = await client.call_tool(
            "validate_and_materialize_mapping_candidate",
            {
                "model_id": 7,
                "model_revision": 4,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
                "context_digest": prepared.structured_content["context_digest"],
                "candidate": _candidate(),
            },
        )

    assert result.is_error is True
    assert "coverage is incomplete" in result.content[0].text


@pytest.mark.asyncio
async def test_mapping_candidate_rejects_locked_header_change() -> None:
    context = _context()
    headers = context["headers"]
    assert isinstance(headers, list) and isinstance(headers[0], dict)
    headers[0]["is_locked"] = True
    database = FakeDatabase(context)

    async with Client(_server(database)) as client:
        prepared = await client.call_tool(
            "get_model_mapping_authoring_context",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )
        assert prepared.structured_content is not None
        result = await client.call_tool(
            "validate_and_materialize_mapping_candidate",
            {
                "model_id": 7,
                "model_revision": 4,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
                "context_digest": prepared.structured_content["context_digest"],
                "candidate": _candidate(),
            },
        )

    assert result.is_error is True
    assert "locked Mapping header" in result.content[0].text


@pytest.mark.asyncio
async def test_mapping_candidate_rejects_dependency_reason_drift() -> None:
    context = _context()
    context["source_dependencies"] = [
        {
            "predecessor_source_system_id": 202,
            "reason": "Must complete first.",
        }
    ]
    candidate = _candidate()
    package = candidate["package"]
    assert isinstance(package, dict)
    package["source_system_dependencies"] = [
        {
            "predecessor_source_system_id": 202,
            "reason": "Different reason.",
        }
    ]
    database = FakeDatabase(context)

    async with Client(_server(database)) as client:
        prepared = await client.call_tool(
            "get_model_mapping_authoring_context",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )
        assert prepared.structured_content is not None
        result = await client.call_tool(
            "validate_and_materialize_mapping_candidate",
            {
                "model_id": 7,
                "model_revision": 4,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
                "context_digest": prepared.structured_content["context_digest"],
                "candidate": candidate,
            },
        )

    assert result.is_error is True
    assert "dependencies or load keys changed" in result.content[0].text


@pytest.mark.asyncio
async def test_mapping_context_rejects_noncontract_existing_documents() -> None:
    context = _context()
    headers = context["headers"]
    assert isinstance(headers, list) and isinstance(headers[0], dict)
    package = _candidate()["package"]
    assert isinstance(package, dict)
    package["unexpected"] = {"unbounded": "payload"}
    headers[0]["mapping_object_id"] = 901
    headers[0]["existing"] = {
        "object_dependency_order": 0,
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic Databricks SQL.",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_package_document": package,
        "object_mapping_transformation_document": _candidate()["headers"][0][
            "transformation"
        ],
        "status": "active",
        "is_locked": False,
        "attributes": [],
    }
    database = FakeDatabase(context)

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "get_model_mapping_authoring_context",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )

    assert result.is_error is True
    assert "Mapping authoring context is unavailable" in result.content[0].text


@pytest.mark.asyncio
async def test_code_generation_document_is_exact_name_only_and_digest_bound() -> None:
    context = _context()
    headers = context["headers"]
    assert isinstance(headers, list) and isinstance(headers[0], dict)
    headers[0]["mapping_object_id"] = 901
    headers[0]["existing"] = {
        "object_dependency_order": 0,
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic Databricks SQL.",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_package_document": _candidate()["package"],
        "object_mapping_transformation_document": _candidate()["headers"][0][
            "transformation"
        ],
        "status": "active",
        "is_locked": False,
        "attributes": [
            {
                "mapping_attribute_id": 902,
                "modeled_attribute_id": 601,
                "target_attribute_id": 301,
                "transformation": _candidate()["attribute_mappings"][0][
                    "transformation"
                ],
                "status": "active",
                "is_locked": False,
            }
        ],
    }
    database = FakeDatabase(
        context,
        generator_references={
            "source_predecessors": [],
            "target_predecessors": [],
            "provenance": [
                {
                    "lineage_kind": "original_ingestion",
                    "reference_id": 801,
                    "source_system_id": 201,
                    "source_system_code": "CRM",
                    "source_system_name": "CRM",
                    "connection_code": "CRM_SOURCE",
                    "source_object_name": "customer",
                    "lineage_path": ["crm.customer -> bronze.customer"],
                }
            ],
        },
    )

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "get_model_code_generation_document",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )

    assert result.is_error is False
    assert result.structured_content is not None
    content = result.structured_content
    assert content["document"]["target"]["fqn"] == "demo_catalog.silver.customer"
    assert (
        content["document"]["executable_sources"][0]["used_columns"][0]["name"]
        == "customer_id"
    )
    assert content["document"]["target_columns"][0]["contributors"][0] == {
        "entity_name": "Customer",
        "attribute_name": "CustomerId",
        "source_alias": "customer_source",
        "source_column_name": "customer_id",
    }
    serialized = json.dumps(content["document"])
    assert '"object_id"' not in serialized
    assert '"attribute_id"' not in serialized
    assert content["proof"]["contract"] == "generator-document@1.0"
    assert content["proof"]["document_digest"] == content["document_digest"]
    assert content["target_mapping_context_digest"] == "c" * 64
    assert content["target_source_context_digest"] == "d" * 64
    assert database.isolations[-1] is ReadIsolation.REPEATABLE_READ
    generator_audit = database.audit_records[-1]
    assert generator_audit.tool_name == "get_model_code_generation_document"
    assert "document" not in generator_audit.input_metadata


@pytest.mark.asyncio
async def test_code_generation_document_requires_canonical_target_context() -> None:
    context = _context()
    headers = context["headers"]
    assert isinstance(headers, list) and isinstance(headers[0], dict)
    headers[0]["mapping_object_id"] = 901
    headers[0]["existing"] = {
        "object_dependency_order": 0,
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic Databricks SQL.",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_package_document": _candidate()["package"],
        "object_mapping_transformation_document": _candidate()["headers"][0][
            "transformation"
        ],
        "status": "active",
        "is_locked": False,
        "attributes": [
            {
                "mapping_attribute_id": 902,
                "modeled_attribute_id": 601,
                "target_attribute_id": 301,
                "transformation": _candidate()["attribute_mappings"][0][
                    "transformation"
                ],
                "status": "active",
                "is_locked": False,
            }
        ],
    }
    database = FakeDatabase(
        context,
        generator_references={
            "source_predecessors": [],
            "target_predecessors": [],
            "provenance": [],
        },
        generator_target_context=None,
    )

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "get_model_code_generation_document",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )

    assert result.is_error is True
    assert "target context is unavailable" in result.content[0].text


@pytest.mark.asyncio
async def test_code_generation_rejects_applied_package_for_another_target() -> None:
    context = _context()
    headers = context["headers"]
    assert isinstance(headers, list) and isinstance(headers[0], dict)
    package = _candidate()["package"]
    assert isinstance(package, dict)
    package["target_object_id"] = 999
    headers[0]["mapping_object_id"] = 901
    headers[0]["existing"] = {
        "object_dependency_order": 0,
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic Databricks SQL.",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_package_document": package,
        "object_mapping_transformation_document": _candidate()["headers"][0][
            "transformation"
        ],
        "status": "active",
        "is_locked": False,
        "attributes": [
            {
                "mapping_attribute_id": 902,
                "modeled_attribute_id": 601,
                "target_attribute_id": 301,
                "transformation": _candidate()["attribute_mappings"][0][
                    "transformation"
                ],
                "status": "active",
                "is_locked": False,
            }
        ],
    }
    database = FakeDatabase(
        context,
        generator_references={
            "source_predecessors": [],
            "target_predecessors": [],
            "provenance": [
                {
                    "lineage_kind": "original_ingestion",
                    "reference_id": 801,
                    "source_system_id": 201,
                    "source_system_code": "CRM",
                    "source_system_name": "CRM",
                    "connection_code": "CRM_SOURCE",
                    "source_object_name": "customer",
                    "lineage_path": ["crm.customer -> bronze.customer"],
                }
            ],
        },
    )

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "get_model_code_generation_document",
            {
                "model_id": 7,
                "modeled_entity_type": "logical_entity",
                "target_object_id": 101,
                "source_system_id": 201,
            },
        )

    assert result.is_error is True
    assert "Mapping package identity" in result.content[0].text


def _candidate() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "package": {
            "schema_version": "1.0",
            "package_ref": "customer_crm",
            "route": "logical_to_silver",
            "target_object_id": 101,
            "source_system_id": 201,
            "artifact_type": "sql_file",
            "artifact_generation_instructions": "Generate deterministic Databricks SQL.",
            "pydantic_profile": {
                "key": "mapping.standard",
                "version": "1.0.0",
                "schema_digest": PROFILE_DIGEST,
            },
            "executable_sources": [
                {
                    "object_id": 401,
                    "alias": "customer_source",
                    "role": "Customer source",
                    "batch_rule": None,
                }
            ],
            "non_executable_provenance": [
                {
                    "lineage_kind": "original_ingestion",
                    "source_system_id": 201,
                    "source_object_id": 401,
                    "ingestion_object_mapping_ids": [801],
                    "prior_object_mapping_ids": [],
                    "executable_source_aliases": ["customer_source"],
                }
            ],
            "runtime_parameters": [],
            "source_system_dependencies": [],
            "target_dependencies": [],
            "steps": [
                {
                    "name": "load_customer",
                    "depends_on": [],
                    "inputs": ["customer_source"],
                    "output": "customer_rows",
                    "logic": "Load governed Customer rows.",
                }
            ],
            "grain_and_deduplication": "One row per Customer.",
            "load": {
                "write_mode": "merge",
                "merge_keys": [301],
                "partition_basis": None,
                "concurrent_system_write_mode": "idempotent_merge",
                "concurrent_write_basis": "Customer key.",
            },
        },
        "headers": [
            {
                "header_ref": "customer",
                "disposition": "author",
                "object_dependency_order": 0,
                "transformation": {
                    "schema_version": "1.0",
                    "transformation_kind": "direct",
                    "source_aliases": ["customer_source"],
                    "joins": [],
                    "unions": [],
                    "filters": [],
                    "aggregations": [],
                    "entity_contribution_logic": "Customer source contributes Customer rows.",
                    "rationale": "The governed CRM source directly represents Customer.",
                },
                "status": "active",
            }
        ],
        "attribute_mappings": [
            {
                "header_ref": "customer",
                "modeled_attribute_id": 601,
                "target_attribute_id": 301,
                "disposition": "create",
                "transformation": {
                    "schema_version": "1.0",
                    "transformation_kind": "direct",
                    "source_columns": [
                        {
                            "source_alias": "customer_source",
                            "source_attribute_id": 402,
                        }
                    ],
                    "step_output": None,
                    "expression": None,
                    "logic": "Copy the governed Customer key.",
                },
                "status": "active",
            }
        ],
        "target_attribute_dispositions": [
            {
                "target_attribute_id": 301,
                "disposition": "mapped",
                "reason": None,
            }
        ],
        "coverage": {
            "expected_header_refs": ["customer"],
            "returned_header_refs": ["customer"],
            "expected_target_attribute_ids": [301],
            "returned_target_attribute_ids": [301],
        },
    }


def _context() -> dict[str, object]:
    return {
        "target": {
            "object_id": 101,
            "tenant_code": "DEMO",
            "tenant_catalog": "demo_catalog",
            "system_code": "CURATED",
            "connection_code": "TARGET",
            "object_schema": "silver",
            "object_name": "customer",
            "object_description": "Curated Customer.",
            "zone": "silver",
            "is_locked": False,
            "attributes": [
                {
                    "attribute_id": 301,
                    "attribute_name": "customer_id",
                    "data_type": "BIGINT",
                    "nullable": False,
                    "ordinal": 1,
                    "definition": "Customer key.",
                }
            ],
        },
        "source_system": {
            "system_id": 201,
            "system_code": "CRM",
            "system_name": "CRM",
            "dependency_order": 0,
        },
        "headers": [
            {
                "header_ref": "customer",
                "mapping_object_id": None,
                "modeled_entity_id": 501,
                "modeled_entity_name": "Customer",
                "modeled_entity_definition": "A customer.",
                "modeled_entity_kind": "business_entity",
                "grain": "One Customer.",
                "dependency_order": 0,
                "is_locked": False,
                "attributes": [
                    {
                        "modeled_attribute_id": 601,
                        "name": "CustomerId",
                        "definition": "Customer key.",
                        "data_type": "BIGINT",
                        "nullable": False,
                        "ordinal": 1,
                    }
                ],
                "sources": [
                    {
                        "source_mapping_id": 701,
                        "role": "Customer source",
                        "rationale": "Authoritative CRM source.",
                        "object": {
                            "object_id": 401,
                            "tenant_code": "DEMO",
                            "tenant_catalog": "demo_catalog",
                            "system_code": "CRM",
                            "connection_code": "BRONZE",
                            "object_schema": "bronze",
                            "object_name": "customer",
                            "zone": "bronze",
                            "batch_attribute_id": None,
                            "attributes": [
                                {
                                    "attribute_id": 402,
                                    "attribute_name": "customer_id",
                                    "data_type": "BIGINT",
                                    "nullable": False,
                                    "ordinal": 1,
                                    "definition": "Customer key.",
                                }
                            ],
                            "ingestion_mapping_ids": [801],
                            "prior_mapping_ids": [],
                        },
                    }
                ],
                "existing": None,
            }
        ],
        "source_dependencies": [],
        "target_dependencies": [],
    }
