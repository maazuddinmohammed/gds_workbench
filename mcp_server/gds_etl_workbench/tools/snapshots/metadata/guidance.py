"""Model-friendly authoring guidance for shared Metadata dataset contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from gds_etl_workbench.tools.snapshots.dataset_description import (
    DatasetColumnAcceptedValues,
    DatasetColumnDescription,
    DatasetColumnReference,
    DatasetDescription,
    JsonScalar,
)

from .contracts import DATASETS, DatasetDefinition

_CONSTRAINT_KEYS = (
    "format",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minItems",
    "maxItems",
)


@dataclass(frozen=True, slots=True)
class ColumnGuidance:
    description: str
    population_guidance: str
    examples: tuple[JsonScalar, ...] = ()


_EXACT_GUIDANCE = {
    "attribute_custom_code": ColumnGuidance(
        "Optional implementation code or expression associated with the Attribute.",
        "Use null when no governed custom code is required; otherwise provide only the "
        "expression expected by the downstream metadata consumer.",
    ),
    "attribute_data_type": ColumnGuidance(
        "Physical data type of the Attribute.",
        "Use the data-type spelling accepted by the owning platform, including precision "
        "or scale when applicable.",
        ("varchar(200)",),
    ),
    "attribute_nullability": ColumnGuidance(
        "Whether the physical Attribute permits null values.",
        "Use true when null is permitted and false when every row must contain a value.",
        (True,),
    ),
    "attribute_ordinal_position": ColumnGuidance(
        "One-based position of the Attribute within its Object.",
        "Use a positive integer unique within the Object and preserve the intended column order.",
        (1,),
    ),
    "batch_attribute_name": ColumnGuidance(
        "Optional Attribute used to identify or partition ingestion batches for the Object.",
        "Use null when the Object has no batch Attribute; otherwise use an Attribute name "
        "belonging to this Object.",
        ("batch_id",),
    ),
    "copy_group_control_initial_load_date": ColumnGuidance(
        "Initial effective date recorded for this Copy Group control state.",
        "Use an ISO 8601 date or null when the initial-load date has not been established.",
        ("2026-01-01",),
    ),
    "copy_group_control_last_run_time": ColumnGuidance(
        "Timestamp of the most recently completed run represented by this control state.",
        "Use an ISO 8601 timestamp with an offset, or null before the first completed run.",
        ("2026-01-01T12:00:00Z",),
    ),
    "copy_group_control_last_run_value": ColumnGuidance(
        "Last incremental watermark or cursor value stored for this control state.",
        "Use the exact serialized value expected by the incremental extraction logic; use "
        "null when no watermark exists.",
    ),
    "copy_source_file_delimiter": ColumnGuidance(
        "Delimiter used when reading a delimited source file.",
        "Use null for non-delimited sources; otherwise provide the exact delimiter characters.",
        (",",),
    ),
    "copy_source_file_name": ColumnGuidance(
        "Optional fixed source filename used by the Copy.",
        "Use null when files are selected by another mechanism; do not populate both a fixed "
        "name and a conflicting file pattern.",
        ("orders.csv",),
    ),
    "copy_source_file_pattern": ColumnGuidance(
        "Optional source-file matching pattern used by the Copy.",
        "Use null when no pattern is required; otherwise use the pattern syntax expected by "
        "the source connector.",
        ("orders_*.csv",),
    ),
    "copy_source_incremental_sql_script": ColumnGuidance(
        "Optional source SQL used for incremental Copy execution.",
        "Use null when incremental extraction is not SQL-driven; otherwise provide the "
        "governed source query without credentials.",
    ),
    "copy_source_initial_sql_script": ColumnGuidance(
        "Optional source SQL used for the initial Copy execution.",
        "Use null when initial extraction is not SQL-driven; otherwise provide the governed "
        "source query without credentials.",
    ),
    "copy_source_order": ColumnGuidance(
        "Execution order of the Copy within its Copy Group.",
        "Use a positive integer unique within the Copy Group; lower values execute first.",
        (1,),
    ),
    "copy_source_record_limit": ColumnGuidance(
        "Optional source-row limit represented as an integer string.",
        "Use null for no limit; otherwise provide only a base-10 integer string.",
        ("100000",),
    ),
    "copy_source_record_limit_attribute": ColumnGuidance(
        "Optional source Attribute used with record-limiting logic.",
        "Use null when the record limit does not depend on an Attribute; otherwise use a "
        "source Attribute name.",
        ("created_time",),
    ),
    "fc_attribute_name": ColumnGuidance(
        "Optional foreign-catalog name of the Attribute.",
        "Use null when the Connection does not use a foreign catalog; otherwise copy the "
        "Attribute name exactly as exposed by that catalog.",
    ),
    "fc_object_name": ColumnGuidance(
        "Optional foreign-catalog name of the Object.",
        "Use null when the Connection does not use a foreign catalog; otherwise copy the "
        "Object name exactly as exposed by that catalog.",
    ),
    "fc_object_schema": ColumnGuidance(
        "Optional foreign-catalog schema containing the Object.",
        "Use null when the Connection does not use a foreign catalog; otherwise copy the "
        "schema exactly as exposed by that catalog.",
    ),
    "foreign_catalog": ColumnGuidance(
        "Optional external catalog associated with the Connection.",
        "Use null when has_foreign_catalog is false; otherwise provide the exact accessible "
        "catalog name.",
        ("source_catalog",),
    ),
    "gds_admin_catalog": ColumnGuidance(
        "Catalog containing administrative GDS metadata for the Tenant.",
        "Provide the exact accessible catalog name configured for GDS administration.",
        ("gds_admin",),
    ),
    "gds_connection_code": ColumnGuidance(
        "Connection code of the optional GDS data-store Connection for the Tenant.",
        "Populate this together with gds_connection_tenant_code and "
        "gds_connection_system_code, or set all three fields to null.",
    ),
    "gds_connection_system_code": ColumnGuidance(
        "System code of the optional GDS data-store Connection for the Tenant.",
        "Populate this together with gds_connection_tenant_code and gds_connection_code, "
        "or set all three fields to null.",
    ),
    "gds_connection_tenant_code": ColumnGuidance(
        "Tenant code owning the optional GDS data-store Connection.",
        "Populate this together with gds_connection_system_code and gds_connection_code, "
        "or set all three fields to null.",
    ),
    "has_foreign_catalog": ColumnGuidance(
        "Whether the Connection exposes its Objects through a foreign catalog.",
        "Use true only when foreign_catalog and foreign-catalog Object names are meaningful.",
        (False,),
    ),
    "is_active": ColumnGuidance(
        "Whether the record is active for normal governed use.",
        "Use true for an effective record and false to retain it as inactive history.",
        (True,),
    ),
    "is_global_data_store": ColumnGuidance(
        "Whether the Connection is the governed global data-store Connection.",
        "Use true only for a Connection intentionally designated as a global data store.",
        (False,),
    ),
    "is_locked": ColumnGuidance(
        "Whether the Object is protected from Metadata Change Set modification.",
        "Preserve the current value. A locked applied Object cannot be changed through a "
        "Metadata Change Set.",
        (False,),
    ),
    "is_mapped": ColumnGuidance(
        "Whether the Attribute participates in an ingestion Attribute Mapping.",
        "Use true when the Attribute is intentionally mapped; otherwise use false.",
        (True,),
    ),
    "is_masking_required": ColumnGuidance(
        "Whether downstream handling must mask the Attribute.",
        "Use true when the Attribute is classified as requiring masking; otherwise use false.",
        (False,),
    ),
    "is_member_group_required": ColumnGuidance(
        "Whether each Copy Group control record must identify a Member Group.",
        "Use true when execution is partitioned by Member Group; otherwise use false.",
        (False,),
    ),
    "is_meta_data": ColumnGuidance(
        "Whether the Attribute contains operational metadata rather than business data.",
        "Use true for audit, lineage, or framework-maintained Attributes; otherwise use false.",
        (False,),
    ),
    "is_natural_key": ColumnGuidance(
        "Whether the Attribute is part of the Object's business or natural key.",
        "Use true only when the Attribute participates in the stable business identity.",
        (False,),
    ),
    "is_purge": ColumnGuidance(
        "Whether the Attribute participates in purge behavior.",
        "Use true only when governed purge processing uses this Attribute.",
        (False,),
    ),
    "is_surrogate_key": ColumnGuidance(
        "Whether the Attribute is a generated surrogate key.",
        "Use true only for a generated technical identifier, not a business key.",
        (False,),
    ),
    "member_group_initial_load_date": ColumnGuidance(
        "Initial load date assigned to the Member Group.",
        "Use an ISO 8601 date or null when the Member Group has no fixed initial date.",
        ("2026-01-01",),
    ),
    "object_transformation": ColumnGuidance(
        "Optional transformation expression or document associated with the Object.",
        "Use null for directly represented Objects; otherwise provide only governed "
        "transformation content and never credentials.",
    ),
    "process_execution_order": ColumnGuidance(
        "Execution order of the Process within its Process Group.",
        "Use a positive integer representing the intended order; lower values execute first.",
        (1,),
    ),
    "process_executable": ColumnGuidance(
        "Executable, notebook, procedure, or job name invoked by the Process.",
        "Provide the exact executable identifier understood at process_location.",
        ("load_orders",),
    ),
    "process_location": ColumnGuidance(
        "Location containing the Process executable.",
        "Provide the governed workspace path, schema, or runtime location expected by the "
        "selected Process Type.",
        ("/Shared/etl",),
    ),
    "tenant_catalog": ColumnGuidance(
        "Primary data catalog assigned to the Tenant.",
        "Provide the exact accessible catalog name used for the Tenant's governed data.",
        ("acme_data",),
    ),
    "tenant_visibility": ColumnGuidance(
        "Visibility boundary of the Tenant.",
        "Use private for Tenant-scoped visibility or global only for intentionally shared "
        "Tenant metadata.",
        ("private",),
    ),
}

_EXAMPLES = {
    "project_code": "DATA_PLATFORM",
    "project_name": "Enterprise Data Platform",
    "tenant_code": "ACME",
    "tenant_name": "Acme",
    "system_code": "ERP",
    "system_name": "Enterprise ERP",
    "connection_code": "SOURCE",
    "connection_name": "ERP Source",
    "object_schema": "sales",
    "object_name": "orders",
    "attribute_name": "customer_id",
    "zone_code": "source",
    "copy_group_name": "Daily Orders",
    "member_group_name": "North America",
    "process_group_name": "Silver Orders",
    "chunk_type_name": "date_range",
    "file_type_name": "csv",
    "data_operation_name": "merge",
    "process_type_name": "notebook",
}


def build_metadata_dataset_description(
    definition: DatasetDefinition,
    properties: dict[str, object],
    required_fields: set[str],
) -> DatasetDescription:
    """Describe every field using the exact schema plus curated authoring guidance."""
    columns: list[DatasetColumnDescription] = []
    for name in definition.row_model.model_fields:
        raw_schema = properties.get(name)
        if not isinstance(raw_schema, dict):
            raise ValueError(f"{definition.name}.{name} has no property schema")
        property_schema = cast(dict[str, object], raw_schema)
        guidance = _column_guidance(name)
        references = _column_references(definition, name)
        fixed_values = dict(definition.fixed_values)
        value_contract = _accepted_values(
            name,
            property_schema,
            fixed_values=fixed_values,
            references=references,
        )
        population_guidance = _population_guidance(
            definition,
            name,
            guidance.population_guidance,
            fixed_values=fixed_values,
            references=references,
        )
        column = DatasetColumnDescription(
            name=name,
            data_types=tuple(_data_types(property_schema)),
            required=name in required_fields,
            nullable="null" in _data_types(property_schema),
            description=guidance.description,
            population_guidance=population_guidance,
            accepted_values=value_contract,
            examples=guidance.examples or _examples(name),
        )
        column_document = column.model_dump(mode="json")
        property_schema["description"] = guidance.description
        property_schema["x-gds-population-guidance"] = population_guidance
        property_schema["x-gds-accepted-values"] = column_document["accepted_values"]
        if column.examples:
            property_schema["examples"] = column_document["examples"]
        columns.append(column)
    return DatasetDescription(
        population_rules=metadata_population_rules(definition),
        columns=tuple(columns),
    )


def metadata_population_rules(definition: DatasetDefinition) -> tuple[str, ...]:
    """Publish dataset-level rules that cannot be explained by one field alone."""
    rules = [
        "Supply every required column. A required nullable column must still be present; "
        "use null only when its column guidance permits it.",
        (
            f"The normalized natural key is ({', '.join(definition.canonical_key)}); "
            "one record must be unique by this complete key."
        ),
    ]
    if not definition.change_set_eligible:
        rules.append(
            "This dataset is read-only Snapshot context and cannot be staged in a Metadata "
            "Change Set."
        )
    for constraint in definition.unique_constraints:
        if constraint != definition.canonical_key:
            rules.append(f"Values must also be unique by ({', '.join(constraint)}).")
    for field, value in definition.fixed_values:
        rules.append(f"{field} must be exactly {value!r} in this dataset.")
    for reference in definition.references:
        candidates = [
            candidate.name
            for candidate in DATASETS
            if candidate.record_type == reference.target_record_type
        ]
        nullable = "may all be null" if reference.nullable else "must all be populated"
        rules.append(
            f"Reference columns ({', '.join(reference.columns)}) {nullable} and, when "
            f"populated, must match ({', '.join(reference.target_columns)}) in one of: "
            f"{', '.join(candidates)}."
        )
    if definition.name == "tenant":
        rules.append(
            "gds_connection_tenant_code, gds_connection_system_code, and "
            "gds_connection_code must be populated together or all set to null."
        )
    return tuple(rules)


def _column_guidance(name: str) -> ColumnGuidance:
    exact = _EXACT_GUIDANCE.get(name)
    if exact is not None:
        return exact
    label = _label(name)
    if name.endswith("_description"):
        subject = _label(name.removesuffix("_description"))
        return ColumnGuidance(
            f"Plain-language description of the {subject}.",
            "Provide concise business or operational context; use null when no description "
            "is available.",
        )
    if name.endswith("_code"):
        return ColumnGuidance(
            f"Stable code identifying the {label.removesuffix(' Code')}.",
            "Use the canonical code from the referenced record when a reference is declared; "
            "otherwise use a stable nonblank code and do not use a database ID.",
            _examples(name),
        )
    if name.endswith("_name"):
        return ColumnGuidance(
            f"Name identifying the {label.removesuffix(' Name')}.",
            "Use the exact name from the referenced record when a reference is declared; "
            "otherwise provide a stable nonblank name.",
            _examples(name),
        )
    if name.endswith("_schema"):
        return ColumnGuidance(
            f"Schema containing the {label.removesuffix(' Schema')}.",
            "Use the exact platform schema name. Preserve case only when the owning platform "
            "treats it as significant.",
            _examples(name),
        )
    raise ValueError(f"Metadata column guidance is missing for {name}")


def _accepted_values(
    name: str,
    schema: dict[str, object],
    *,
    fixed_values: dict[str, object],
    references: tuple[DatasetColumnReference, ...],
) -> DatasetColumnAcceptedValues:
    constraints = _constraints(schema)
    if name in fixed_values:
        return DatasetColumnAcceptedValues(
            kind="fixed",
            values=(_json_scalar(fixed_values[name]),),
            references=references,
            constraints=constraints,
        )
    enum_values = _enum_values(schema)
    if enum_values:
        return DatasetColumnAcceptedValues(
            kind="literal",
            values=tuple(_json_scalar(value) for value in enum_values),
            references=references,
            constraints=constraints,
        )
    if [value for value in _data_types(schema) if value != "null"] == ["boolean"]:
        return DatasetColumnAcceptedValues(
            kind="literal",
            values=(False, True),
            references=references,
            constraints=constraints,
        )
    if references:
        return DatasetColumnAcceptedValues(
            kind="reference",
            values=(),
            references=references,
            constraints=constraints,
        )
    return DatasetColumnAcceptedValues(
        kind="constrained" if constraints else "freeform",
        values=(),
        references=(),
        constraints=constraints,
    )


def _column_references(
    definition: DatasetDefinition,
    name: str,
) -> tuple[DatasetColumnReference, ...]:
    result: list[DatasetColumnReference] = []
    for reference in definition.references:
        if name not in reference.columns:
            continue
        position = reference.columns.index(name)
        result.append(
            DatasetColumnReference(
                record_type=reference.target_record_type,
                datasets=tuple(
                    candidate.name
                    for candidate in DATASETS
                    if candidate.record_type == reference.target_record_type
                ),
                column=reference.target_columns[position],
                composite_columns=reference.columns,
                target_columns=reference.target_columns,
                nullable=reference.nullable,
            )
        )
    return tuple(result)


def _population_guidance(
    definition: DatasetDefinition,
    name: str,
    base: str,
    *,
    fixed_values: dict[str, object],
    references: tuple[DatasetColumnReference, ...],
) -> str:
    additions: list[str] = []
    if name in fixed_values:
        additions.append(f"For this dataset, use exactly {fixed_values[name]!r}.")
    if references:
        targets = "; ".join(
            f"column {reference.column} in dataset(s) {', '.join(reference.datasets)}"
            for reference in references
        )
        additions.append(
            f"The value must be copied from the referenced value source(s): {targets} "
            "Populate every field in each composite reference together."
        )
    if name in definition.canonical_key:
        additions.append(
            "This field is part of the natural key; changing it identifies a different record."
        )
    return " ".join((base, *additions))


def _data_types(schema: dict[str, object]) -> list[str]:
    result: list[str] = []
    raw_type = schema.get("type")
    if isinstance(raw_type, str):
        result.append(raw_type)
    elif isinstance(raw_type, list):
        result.extend(item for item in cast(list[object], raw_type) if isinstance(item, str))
    raw_any_of = schema.get("anyOf")
    if isinstance(raw_any_of, list):
        for branch in cast(list[object], raw_any_of):
            if isinstance(branch, dict):
                for item in _data_types(cast(dict[str, object], branch)):
                    if item not in result:
                        result.append(item)
    return result


def _enum_values(schema: dict[str, object]) -> list[object]:
    if "const" in schema:
        return [schema["const"]]
    raw_enum = schema.get("enum")
    if isinstance(raw_enum, list):
        return cast(list[object], raw_enum)
    raw_any_of = schema.get("anyOf")
    if isinstance(raw_any_of, list):
        values: list[object] = []
        for branch in cast(list[object], raw_any_of):
            if isinstance(branch, dict):
                values.extend(_enum_values(cast(dict[str, object], branch)))
        return values
    return []


def _json_scalar(value: object) -> JsonScalar:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise ValueError("Metadata accepted value is not a JSON scalar")


def _constraints(schema: dict[str, object]) -> dict[str, object]:
    result = {key: schema[key] for key in _CONSTRAINT_KEYS if key in schema}
    raw_any_of = schema.get("anyOf")
    if isinstance(raw_any_of, list):
        for branch in cast(list[object], raw_any_of):
            if isinstance(branch, dict):
                result.update(_constraints(cast(dict[str, object], branch)))
    return result


def _examples(name: str) -> tuple[JsonScalar, ...]:
    direct = _EXAMPLES.get(name)
    if direct is not None:
        return (direct,)
    for prefix in (
        "source_",
        "target_",
        "object_",
        "connection_",
        "scope_",
    ):
        if name.startswith(prefix):
            inherited = _EXAMPLES.get(name.removeprefix(prefix))
            if inherited is not None:
                return (inherited,)
    return ()


def _label(name: str) -> str:
    return name.replace("_", " ").replace("gds", "GDS").replace("fc", "foreign-catalog").title()
