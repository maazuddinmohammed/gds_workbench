"""Natural-key prompt projections for the frozen downstream authoring stages."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from typing import Any, cast

from gds_etl_workbench.domain.errors import InvalidRequestError

from .context_inputs import OBJECT_FIELDS, natural_key
from .context_readers import FrozenContextReaders, ReaderSpecs


def downstream_reader_specs(workflow: str) -> ReaderSpecs:
    if workflow == "mapping":
        return {
            "get_mapping_target": ("target_metadata", None, ()),
            "get_mapping_sources": ("source_evidence", "source_object_keys", OBJECT_FIELDS),
            "get_existing_mapping": ("existing_mapping", None, ()),
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
            "get_current_code": (
                "current_code",
                "artifact_keys",
                ("modeled_entity_type", "modeled_entity_name", "artifact_name"),
            ),
            "get_applied_groups": ("applied_groups", "group_names", ("validation_group_name",)),
            "get_applied_checks": ("applied_checks", "group_names", ("validation_group_name",)),
        }
    raise InvalidRequestError("The downstream prompt workflow is unavailable.")


class DownstreamContextReaders(FrozenContextReaders):
    """Resolve nested physical keys without flattening their evidence records."""

    @property
    def prompt_values(self) -> dict[str, Any]:
        values = super().prompt_values
        target = values.get("target_metadata")
        if isinstance(target, list):
            values["target_metadata"] = target[0]
        return values

    @property
    def allowed_tool_names(self) -> tuple[str, ...]:
        return tuple(definition.name for definition in self.definitions)

    def _select(self, tool: str, selection: Any) -> Any:
        variable, selector, fields = self._specs[tool]
        rows = self._values.get(variable)
        if selection in (None, []):
            return rows
        if selector in {"source_object_keys", "target_object_keys", "group_names"}:
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
                    if selector == "source_object_keys"
                    else row["context"]["target_metadata"]
                    if selector == "target_object_keys"
                    else row
                )
                return natural_key(value, fields)

            available_rows = self._values["applied_groups"] if selector == "group_names" else rows
            if not wanted <= {key(row) for row in available_rows}:
                self._invalid()
            return [row for row in rows if key(row) in wanted]
        return super()._select(tool, selection)


def build_downstream_readers(
    workflow: str,
    values: dict[str, Any],
    *,
    max_result_bytes: int,
    max_page_records: int,
    max_cumulative_result_bytes: int,
) -> DownstreamContextReaders:
    specs = downstream_reader_specs(workflow)
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


_DOCUMENT_FIELDS = {
    "transformation",
    "transformation_document",
    "mapping_transformation_document",
    "attribute_mapping_transformation_document",
    "audit_columns_template",
    "technical_columns_template",
    "example",
    "validation_comparison_value",
}


def _without_internal_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [_without_internal_fields(item) for item in cast(list[Any], value)]
    if not isinstance(value, dict):
        return deepcopy(value)
    return {
        name: deepcopy(item) if name in _DOCUMENT_FIELDS else _without_internal_fields(item)
        for name, item in cast(dict[str, Any], value).items()
        if not name.endswith("_id")
        and name not in {"ids", "schema_digest", "schema_digest_is_valid"}
    }


def _sql_inputs(context: dict[str, Any]) -> dict[str, Any]:
    systems = {row["source_system_id"]: row["system_code"] for row in context["source_systems"]}
    objects = {row["mapping_object_id"]: row for row in context["object_mappings"]}
    sources: list[dict[str, Any]] = []
    for row in context["physical_sources"]:
        sources.append(
            {
                **_without_internal_fields(row),
                "source_system_code": systems[row["selected_source_system_id"]],
            }
        )
    object_mappings: list[dict[str, Any]] = []
    for row in context["object_mappings"]:
        object_mappings.append(
            {
                **_without_internal_fields(row),
                "source_system_code": systems[row["source_system_id"]],
            }
        )
    attributes: list[dict[str, Any]] = []
    for row in context["attribute_mappings"]:
        entity = objects[row["mapping_object_id"]]["entity"]
        attributes.append(
            {
                **_without_internal_fields(row),
                "source_system_code": systems[row["source_system_id"]],
                "modeled_entity_type": entity["entity_type"],
                "modeled_entity_name": entity["entity_name"],
            }
        )
    return {
        "target_metadata": _without_internal_fields(context["target"]),
        "source_metadata": sources,
        "source_systems": _without_internal_fields(context["source_systems"]),
        "object_transformations": object_mappings,
        "attribute_transformations": attributes,
    }


def project_downstream_inputs(workflow: str, context: dict[str, Any]) -> dict[str, Any]:
    """Project existing prepared rows; broken nominal-key joins fail before rendering."""
    if context.get("__gds_downstream_inputs__") == workflow:
        return deepcopy(context["values"])
    try:
        if workflow == "mapping":
            header = context["headers"][0]
            entity_attributes = {
                row["attribute_id"]: row["attribute_name"]
                for row in header["modeled_entity"]["attributes"]
            }
            target_attributes = {
                row["attribute_id"]: row["attribute_name"]
                for row in context["target"]["attributes"]
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
                projected["target_attribute_name"] = target_attributes[
                    original["target_attribute_id"]
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

            return {
                "mapping_route": context["run"]["route"],
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
        if workflow == "code_generation":
            target = context["targets"][0]
            return {
                **_sql_inputs(target["context"]),
                "target_ref": target["target_ref"],
                "sql_generation_guide": target["context"].get("guide", {}).get("content"),
            }
        if workflow == "validation":
            targets = [
                {
                    "modeled_entity_type": row["modeled_entity_type"],
                    "modeled_entity_name": row["modeled_entity_name"],
                    "context": _sql_inputs(row["context"]),
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
    except (KeyError, TypeError, ValueError, IndexError):
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
