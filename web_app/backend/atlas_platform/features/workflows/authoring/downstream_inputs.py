"""Natural-key prompt projections for the frozen downstream authoring stages."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from functools import cache, cached_property
from typing import Any, cast

from atlas_mcp.application.mapping_context import (
    project_mapping_inputs as _sql_inputs,
)
from atlas_mcp.application.mapping_context import (
    without_internal_fields as _without_internal_fields,
)
from atlas_mcp.domain.errors import InvalidRequestError
from atlas_mcp.domain.modeling_records import normalize_project_key_value

from .context_inputs import OBJECT_FIELDS, natural_key
from .context_readers import FrozenContextReaders, ReaderSpecs
from .mapping_fk_evidence import mapping_fk_evidence, select_fk_evidence
from .validation_evidence import validation_basis


def downstream_reader_specs(workflow: str) -> ReaderSpecs:
    if workflow == "mapping":
        return {
            "get_mapping_basis": ("mapping_basis", "candidate_refs", ("ref",)),
            "get_mapping_fk_evidence": (
                "mapping_basis",
                "target_attribute_names",
                ("attribute_name",),
            ),
            "get_mapping_target": ("target_metadata", None, ()),
            "get_mapping_sources": ("source_evidence", "source_object_keys", OBJECT_FIELDS),
            "get_existing_mapping": ("existing_mapping", None, ()),
            "get_mapping_support": ("mapping_support", None, ()),
            "get_mapping_support_records": ("mapping_support_records", None, ()),
        }
    if workflow == "code_generation":
        return {
            "get_code_target": ("target_metadata", None, ()),
            "get_code_sources": ("source_metadata", "source_object_keys", OBJECT_FIELDS),
            "get_code_source_systems": ("source_systems", "source_system_names", ("system_code",)),
            "get_object_transformations": (
                "object_transformations",
                "source_system_names",
                ("source_system_code",),
            ),
            "get_attribute_transformations": (
                "attribute_transformations",
                "target_attribute_names",
                ("target_attribute_name",),
            ),
        }
    if workflow == "validation":
        return {
            "get_mapping_evidence": ("mapping_evidence", "target_object_keys", OBJECT_FIELDS),
            "get_validation_basis": ("validation_basis", "detail_refs", ("ref",)),
            "get_current_code": (
                "current_code",
                "artifact_keys",
                (
                    "modeled_entity_type",
                    "modeled_entity_schema_name",
                    "modeled_entity_name",
                    "artifact_name",
                ),
            ),
            "get_applied_groups": ("applied_groups", "group_names", ("validation_group_name",)),
            "get_applied_checks": ("applied_checks", "group_names", ("validation_group_name",)),
        }
    raise InvalidRequestError("The downstream prompt workflow is unavailable.")


class DownstreamContextReaders(FrozenContextReaders):
    """Resolve nested physical keys without flattening their evidence records."""

    defer_fk_details: bool = False
    mapping_pair_pages: Callable[[tuple[str, ...]], list[dict[str, Any]]] | None = None

    @property
    def prompt_values(self) -> dict[str, Any]:
        values = super().prompt_values
        for name in ("target_metadata", "mapping_support"):
            value = values.get(name)
            if isinstance(value, list):
                values[name] = value[0]
        return values

    @property
    def allowed_tool_names(self) -> tuple[str, ...]:
        return tuple(definition.name for definition in self.definitions)

    @cached_property
    def _mapping_directory(self) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        cards = self._values.get("mapping_basis")
        if cards is None:
            cards = compact_mapping_basis(self.prompt_values)
        core: list[dict[str, Any]] = []
        candidates: dict[str, list[dict[str, Any]]] = {}
        for card in cards:
            record = card["record"]
            if card["kind"] == "source" and record["role"] == "candidate":
                candidates[record["ref"]] = [card]
            elif card["kind"] == "column" and record["source"] in candidates:
                candidates[record["source"]].append(card)
                continue
            core.append(card)
        return core, candidates

    @cached_property
    def _validation_directory(self) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        return validation_basis(self._values, fits=lambda card: self._fits([card], "x" * 64, None))

    def _select(self, tool: str, selection: Any) -> Any:
        variable, selector, fields = self._specs[tool]
        if tool == "get_mapping_fk_evidence":
            cards, _ = self._mapping_directory
            roles = [card for card in cards if card["kind"] == "fk_role"]
            if not selection:
                return roles
            wanted = {normalize_project_key_value(name) for name in selection}
            if not wanted <= {
                normalize_project_key_value(card["record"]["target_attribute_name"])
                for card in roles
            }:
                self._invalid()
            return select_fk_evidence(
                cards,
                [
                    card["record"]
                    for card in roles
                    if normalize_project_key_value(card["record"]["target_attribute_name"])
                    in wanted
                ],
                core=False,
            )
        if variable == "validation_basis":
            core, details = self._validation_directory
            if not selection:
                return core
            selected: list[dict[str, Any]] = []
            for value in dict.fromkeys(selection):
                ref, separator, name = value.partition(":")
                rows = details.get(ref)
                if rows is None:
                    self._invalid()
                if separator:
                    rows = [
                        row
                        for row in rows
                        if (
                            row["kind"] in {"target_attribute", "source_attribute"}
                            and row["record"].get("attribute_name") == name
                        )
                        or (
                            row["kind"] == "attribute_transformation"
                            and row["record"].get("target_attribute_name") == name
                        )
                    ]
                    if not rows:
                        self._invalid()
                selected.extend(rows)
            return selected
        if variable == "mapping_basis":
            if self.mapping_pair_pages is not None:
                try:
                    rows = self.mapping_pair_pages(tuple(selection or ()))
                    if self.defer_fk_details and not selection:
                        return select_fk_evidence(
                            rows, [c["record"] for c in rows if c["kind"] == "fk_role"], core=True
                        )
                    return rows
                except KeyError:
                    self._invalid()
            core, candidates = self._mapping_directory
            if not selection:
                if self.defer_fk_details:
                    return select_fk_evidence(
                        core, [c["record"] for c in core if c["kind"] == "fk_role"], core=True
                    )
                return core
            wanted = set(selection)
            if not wanted <= candidates.keys():
                self._invalid()
            if len(wanted) == 1:
                return candidates[selection[0]]
            return [card for ref, group in candidates.items() if ref in wanted for card in group]
        rows = self._values.get(variable)
        if selection in (None, []):
            return rows
        if tool == "get_code_sources" and selection == "directory":
            return [
                {**row, "object": {**row["object"], "attributes": []}}
                for row in cast(list[dict[str, Any]], rows)
            ]
        if selector == "source_keys":
            if not isinstance(rows, list):
                self._invalid()

            def mixed_key(value: dict[str, Any]) -> tuple[Any, ...]:
                modeled = "entity_schema_name" in value
                return (
                    "modeled" if modeled else "physical",
                    *natural_key(
                        value,
                        ("entity_type", "entity_schema_name", "entity_name")
                        if modeled
                        else OBJECT_FIELDS,
                    ),
                )

            wanted = {mixed_key(item) for item in selection}
            source_rows = cast(list[dict[str, Any]], rows)
            if not wanted <= {mixed_key(row["object"]) for row in source_rows}:
                self._invalid()
            return [row for row in source_rows if mixed_key(row["object"]) in wanted]
        if selector in {
            "source_object_keys",
            "source_entity_keys",
            "target_object_keys",
            "group_names",
        }:
            if not isinstance(rows, list):
                self._invalid()
            rows = cast(list[dict[str, Any]], rows)
            wanted = {
                natural_key({fields[0]: item} if isinstance(item, str) else item, fields)
                for item in selection
            }

            def key(row: dict[str, Any]) -> tuple[Any, ...]:
                value = (
                    row["object"]
                    if selector in {"source_object_keys", "source_entity_keys"}
                    else row["context"]["target_metadata"]
                    if selector == "target_object_keys"
                    else row
                )
                return natural_key(value, fields)

            available_rows = self._values["applied_groups"] if selector == "group_names" else rows
            if not wanted <= {key(row) for row in available_rows}:
                self._invalid()
            matched = [row for row in rows if key(row) in wanted]
            if tool != "get_code_sources" or not any("attribute_names" in s for s in selection):
                return matched
            # A source can appear for multiple selected Systems. Preserve every branch
            # and the registered column order when narrowing the columns of that source.
            if len(wanted) != len(selection):
                self._invalid()
            filters = {
                natural_key(s, fields): {
                    normalize_project_key_value(n) for n in s["attribute_names"]
                }
                for s in selection
                if "attribute_names" in s
            }
            for index, row in enumerate(matched):
                requested = filters.get(key(row))
                if requested is None:
                    continue
                obj = row["object"]
                columns = [
                    col
                    for col in obj["attributes"]
                    if normalize_project_key_value(col["attribute_name"]) in requested
                ]
                if len(columns) != len(requested):
                    self._invalid()
                matched[index] = {**row, "object": {**obj, "attributes": columns}}
            return matched
        return super()._select(tool, selection)


def build_downstream_readers(
    workflow: str,
    values: dict[str, Any],
    *,
    max_result_bytes: int | None,
    max_page_records: int,
    max_cumulative_result_bytes: int | None,
) -> DownstreamContextReaders:
    specs = downstream_reader_specs(workflow)
    sources = values.get("source_evidence", [])
    if workflow == "mapping" and sources:
        has_modeled = any("entity_schema_name" in row.get("object", {}) for row in sources)
        has_physical = any("object_schema" in row.get("object", {}) for row in sources)
        if has_modeled:
            specs["get_mapping_sources"] = (
                "source_evidence",
                "source_keys" if has_physical else "source_entity_keys",
                OBJECT_FIELDS
                if has_physical
                else ("entity_type", "entity_schema_name", "entity_name"),
            )
    tool_values = deepcopy(values)
    for variable, _, _ in specs.values():
        if isinstance(tool_values.get(variable), dict):
            tool_values[variable] = [tool_values[variable]]
    return DownstreamContextReaders(
        workflow=workflow,
        values=tool_values,
        readers=specs,
        max_result_bytes=max_result_bytes,
        max_page_records=max_page_records,
        max_cumulative_result_bytes=max_cumulative_result_bytes,
    )


def compact_mapping_basis(
    values: Mapping[str, Any], *, source_refs: Sequence[str] | None = None, include_fk: bool = True
) -> list[dict[str, Any]]:
    """One target, one field per ordinal and a pageable dictionary of eligible inputs."""
    target = values["target_metadata"]
    header = values["existing_mapping"][0]
    readiness: dict[str, Any] = (
        values["readiness"]["headers"][0] if values["readiness"]["headers"] else {}
    )
    actions = {
        row["modeled_attribute_name"]: row["action"]
        for row in readiness.get("attribute_actions", ())
    }
    saved = {
        row["modeled_attribute_name"]: row["transformation_document"]
        for row in header["attribute_mappings"]
        if row["transformation_document"] is not None
    }
    support = values["mapping_support_records"]
    lineage = {
        card["record"]["modeled_attribute_name"]: card["record"]
        for card in support
        if card["evidence_type"] == "target_attribute_lineage"
    }
    target_record = {key: value for key, value in target.items() if key != "attributes"}
    target_record.update(
        action=readiness.get("action"),
        object_dependency_order=max(
            header["object_dependency_order"], readiness.get("required_dependency_order", 0)
        ),
    )
    if header["transformation_document"] is not None:
        target_record["saved"] = header["transformation_document"]
    cards: list[dict[str, Any]] = [{"kind": "target", "record": target_record}]
    deferred_lookups = set(values["readiness"].get("deferred_dependency_attributes", ()))
    for attribute in sorted(target["attributes"], key=lambda row: row["ordinal_position"]):
        name = attribute["attribute_name"]
        field = {
            **attribute,
            **{
                key: val
                for key, val in lineage.get(name, {}).items()
                if key != "modeled_attribute_name"
            },
            "action": actions.get(name),
            "has_saved_rule": name in saved,
        }
        if name in saved:
            field["saved"] = saved[name]
        if name in deferred_lookups:
            field["defer_lookup"] = True
        cards.append({"kind": "field", "record": field})

    # Ordering is for navigation only. Even a late candidate may be needed by a
    # scoped Context rule or saved custom document, so retain its active columns.
    source_order = {"support": 0, "lookup": 1, "candidate": 2}
    sources = sorted(values["source_evidence"], key=lambda s: source_order.get(s["role"], 3))
    candidates: list[dict[str, Any]] = []
    for number, source in enumerate(sources, start=1):
        directory = candidates if source["role"] == "candidate" else cards
        obj = source["object"]
        ref = f"s{number}" if source_refs is None else source_refs[number - 1]
        columns = [
            column
            for column in obj["attributes"]
            if column.get("is_active", True) and column.get("status", "active") == "active"
        ]
        fields = [
            key
            for key in (
                "attribute_name",
                "attribute_data_type",
                "attribute_description",
                "attribute_definition",
                "attribute_inferred_data_type",
                "attribute_nullability",
                "is_nullable",
                "is_natural_key",
                "is_primary_key",
                "is_surrogate_key",
                "is_audit_column",
                "is_pii",
            )
            if any(column.get(key) is not None for column in columns)
        ]
        directory.append(
            {
                "kind": "source",
                "record": {
                    **{
                        key: obj[key]
                        for key in (
                            *OBJECT_FIELDS,
                            "tenant_catalog",
                            "object_description",
                            "zone_code",
                            "batch_attribute_name",
                            "entity_type",
                            "entity_schema_name",
                            "entity_name",
                            "entity_definition",
                            "entity_kind",
                            "grain",
                        )
                        if key in obj and (obj[key] is not None or key == "batch_attribute_name")
                    },
                    "ref": ref,
                    "role": source["role"],
                    "rationale": source["rationale"],
                    "column_fields": fields,
                },
            }
        )
        # A wide table never becomes a single unpageable evidence item.
        directory.extend(
            {"kind": "column", "record": {"source": ref, "values": [col.get(k) for k in fields]}}
            for col in columns
        )
    cards.extend(
        {"kind": card["evidence_type"], "record": card["record"]}
        for card in support
        if card["evidence_type"] != "target_attribute_lineage"
    )
    cards.extend(candidates)
    if include_fk:
        cards.extend(
            mapping_fk_evidence(
                cards,
                sources,
                (card["record"] for card in cards if card["kind"] == "analysis_relationship"),
            )
        )
    return cards


def project_downstream_inputs(
    workflow: str, context: dict[str, Any], *, include_mapping_basis: bool = True
) -> dict[str, Any]:
    """Project existing prepared rows; broken nominal-key joins fail before rendering."""
    if context.get("__gds_downstream_inputs__") == workflow:
        values = deepcopy(context["values"])
        if workflow == "mapping" and include_mapping_basis and "mapping_basis" not in values:
            values["mapping_basis"] = compact_mapping_basis(values)
        return values
    try:
        if workflow == "mapping":
            header = context["headers"][0]
            entity_attributes = {
                row["attribute_id"]: row["attribute_name"]
                for row in header["modeled_entity"]["attributes"]
            }
            templates = {
                row["output_template_id"]: row for row in context["output_templates"]["definitions"]
            }
            mapped_header = _without_internal_fields(header)
            for original, projected in zip(
                header["attribute_mappings"], mapped_header["attribute_mappings"], strict=True
            ):
                projected["modeled_attribute_name"] = entity_attributes[
                    original["modeled_attribute_id"]
                ]
            readiness = _without_internal_fields(context["readiness"])
            for original_header, projected_header in zip(
                context["readiness"]["headers"], readiness["headers"], strict=True
            ):
                for original, projected in zip(
                    original_header["attribute_actions"],
                    projected_header["attribute_actions"],
                    strict=True,
                ):
                    projected["modeled_attribute_name"] = entity_attributes[
                        original["modeled_attribute_id"]
                    ]
            selected = context["run"]["output_template_selections"]

            def template(kind: str) -> Any:
                selection = selected[kind]
                return (
                    None
                    if selection is None
                    else _without_internal_fields(templates[selection["output_template_id"]])
                )

            values = {
                "mapping_route": context["run"]["route"],
                "mapping_support": deepcopy(context.get("mapping_support", {})),
                "mapping_support_records": deepcopy(context.get("mapping_support_records", [])),
                "operation": context["run"]["operation"],
                "target_metadata": _without_internal_fields(context["target"]),
                "source_evidence": _without_internal_fields(context["sources"]),
                "existing_mapping": [mapped_header],
                "authoring_policy": _without_internal_fields(context["authoring"]),
                "readiness": readiness,
                "source_system": _without_internal_fields(context["source_system"]),
                "object_output_template": template("mapping_object"),
                "attribute_output_template": template("mapping_attribute"),
            }
            if include_mapping_basis:
                values["mapping_basis"] = compact_mapping_basis(values)
            return values
        if workflow == "code_generation":
            target = context["targets"][0]
            return {
                **_sql_inputs(target["context"], workflow="code_generation"),
                "target_ref": target["target_ref"],
                "artifact_requirements": deepcopy(target["context"]["artifact_requirements"]),
            }
        if workflow == "validation":
            targets = [
                {
                    "modeled_entity_type": row["modeled_entity_type"],
                    "modeled_entity_schema_name": row["modeled_entity_schema_name"],
                    "modeled_entity_name": row["modeled_entity_name"],
                    "context": _sql_inputs(row["context"], workflow="validation"),
                }
                for row in context["mapping_targets"]
            ]
            return {
                "system_ref": context["system_ref"],
                "system_scope": deepcopy(context["scope"]),
                "mapping_evidence": targets,
                "current_code": deepcopy(context["generated_code"]),
                "applied_groups": deepcopy(context["applied_validation_groups"]),
                "applied_checks": deepcopy(context["applied_validation_checks"]),
            }
    except KeyError, TypeError, ValueError, IndexError:
        raise InvalidRequestError(
            "The frozen downstream prompt context has broken references."
        ) from None
    raise InvalidRequestError("The downstream prompt workflow is unavailable.")


@cache
def downstream_input_contracts(workflow: str) -> dict[str, tuple[dict[str, Any], str, Any]]:
    from .downstream_contracts import CONTRACTS

    return {
        name: (item["value_schema"], item["description"], item["example"])
        for name, item in CONTRACTS[workflow].items()
    }
