"""Plain authoring guidance for Model Snapshot and Change Set datasets."""

from __future__ import annotations

from typing import cast

from gds_etl_workbench.domain.snapshots.description import (
    DatasetColumnAcceptedValues,
    DatasetColumnDescription,
)

_COMMON_RULES = (
    "Use exact natural-key names from the current Snapshot; never database IDs.",
    "Use only active, authorized records from this Model and its source Tenant.",
    "Applied status values are active, inactive, or deprecated; resolve review questions locally.",
)

_DATASET_RULES: dict[str, tuple[str, ...]] = {
    "model_details": (
        "Treat Model policy as authoritative when it differs from default naming guidance.",
    ),
    "model_input_scope": (
        "Select only Source or Bronze Objects whose source Tenant is the Model Tenant.",
        (
            "When equivalent Source and Bronze Objects are selected, use Bronze unless "
            "the user directs otherwise."
        ),
    ),
    "profiling_profile": (
        (
            "Profile every selected Attribute needed to understand shape, quality, keys, "
            "or relationships."
        ),
        (
            "For Source, query only its foreign-catalog catalog/schema/Object/Attribute "
            "coordinates; missing coordinates are a blocking error."
        ),
        "For Bronze, query the physical Object schema, Object name, and Attribute name.",
    ),
    "analysis_result": (
        (
            "Record tested grain, identity, functional-dependency, and relationship findings; "
            "keep unsupported or inconclusive findings explicit."
        ),
    ),
    "modeling_assertion_document": (
        "Describe the local evidence document without storing raw prompts or physical rows.",
    ),
    "modeling_assertion_record": (
        "Keep each assertion atomic, traceable, and applicable to at least one modeling layer.",
    ),
    "conceptual_object": (
        (
            "Model compact business concepts, not one Conceptual Object per physical Object "
            "or Logical Entity."
        ),
        "Define the business process and what one occurrence of each concept represents.",
        "Classify coverage through supports; never duplicate the Logical model.",
        "Use PascalCase by default unless user or Model policy says otherwise.",
    ),
    "conceptual_relationship": (
        "Use business relationships and evidence-backed high-level cardinality.",
    ),
    "logical_submodel": ("Group the normalized operational model by coherent business area.",),
    "logical_entity": (
        (
            "Build a normalized operational Entity with a clear grain, supported identity, "
            "and complete in-scope coverage."
        ),
        (
            "Apply 1NF, 2NF, and 3NF where supported; split different grains, repeating groups, "
            "partial dependencies, transitive dependencies, and genuine associations."
        ),
        (
            "A physical Object maps one-to-one only after checking grain, dependencies, "
            "header/detail structure, history, and cross-System consolidation."
        ),
        "Use PascalCase by default unless user or Model policy says otherwise.",
    ),
    "logical_attribute": (
        "Include every physical target Attribute, including audit and constant-valued Attributes.",
        "Place each Attribute with the Entity whose whole key determines it.",
        "Use PascalCase; identifier Attributes end in ID unless user or Model policy overrides it.",
    ),
    "logical_relationship": (
        "Reference existing Logical Entities and Attributes and provide relationship evidence.",
    ),
    "dimensional_submodel": ("Group Facts and Dimensions around a coherent business process.",),
    "dimensional_entity": (
        (
            "Follow the Kimball sequence: select the business process, declare fact grain, "
            "identify Dimensions, then identify Facts."
        ),
        "Use PascalCase by default unless user or Model policy says otherwise.",
    ),
    "dimensional_attribute": (
        (
            "Include every physical target Attribute, including technical, audit, and "
            "constant-valued Attributes."
        ),
        (
            "Use PascalCase; dimensional key Attributes end in Key unless user or Model "
            "policy overrides it."
        ),
    ),
    "dimensional_relationship": (
        "Reference existing Dimensional Entities and Attributes and preserve the declared grain.",
    ),
    "model_object_binding": (
        "Bind each modeled Entity to exactly one already-registered Silver or Gold Object.",
        "Logical bindings target Silver; Dimensional bindings target Gold.",
        (
            "The target Object source Tenant must equal the Model Tenant even though its "
            "physical Connection belongs to GDS."
        ),
    ),
    "model_attribute_binding": (
        "Bind every modeled Attribute exactly once to an Attribute of its parent bound Object.",
        "Do not omit audit, technical, or constant-valued Attributes.",
    ),
    "mapping_dependency": (
        "Record source-System dependency order used by Mapping and Code Generation.",
    ),
    "mapping_object": (
        "Author one target-oriented Mapping per bound target Entity and source System.",
        "Store the complete transformation in mapping_transformation_document.",
        (
            "An Output Template is advisory; without one, use the plugin standard JSON "
            "shape unless the user requests another format."
        ),
    ),
    "mapping_attribute": (
        (
            "Describe how one bound target Attribute is populated for one "
            "target/source-System Mapping."
        ),
        (
            "The transformation document is flexible JSON and may describe direct, "
            "derived, or constant logic."
        ),
    ),
    "generated_code": (
        "Code Generation decides whether Systems share one file or use separate files.",
        "artifact_name is a file name only; Process metadata owns deployment paths.",
        "Preflight SQL locally when possible; do not persist execution results.",
    ),
    "generated_code_source_system": (
        "List every source System covered by the named Code Artifact.",
    ),
    "validation_group": (
        "Store Validation definitions only; preflight execution results stay local.",
    ),
    "validation_check": (
        (
            "Author technical or functional checks from current Mapping and Code without "
            "waiting for orchestration load completion."
        ),
        "Store the check definition, never a preflight result.",
    ),
}

_FIELD_GUIDANCE: dict[str, str] = {
    "modeling_assertion_record_key": (
        "Use the exact stable Assertion Record key from the current Model Snapshot."
    ),
    "tenant_code": "Use the exact Tenant code from the current Snapshot.",
    "system_code": "Use the exact System code from the current Snapshot.",
    "connection_code": "Use the exact Connection code from the current Snapshot.",
    "source_system_code": "Use the exact contributing source System code.",
    "object_schema": "Use the registered physical Object schema, not a foreign-catalog schema.",
    "object_name": "Use the registered physical Object name.",
    "attribute_name": "Use the registered physical target Attribute name.",
    "modeled_entity_type": "Use logical_entity or dimensional_entity to select the modeled layer.",
    "modeled_entity_name": "Use the exact current Logical or Dimensional Entity name.",
    "modeled_attribute_name": (
        "Use the exact current modeled Attribute name under the named Entity."
    ),
    "logical_entity_type_detail": (
        "Use null unless logical_entity_type is other; other requires a nonblank detail."
    ),
    "output_template_code": (
        "Use an advisory Output Template code, or null when no template applies."
    ),
    "mapping_transformation_document": (
        "Store one complete, bounded JSON object describing the target transformation."
    ),
    "attribute_mapping_transformation_document": (
        "Store bounded flexible JSON for this target Attribute, or null."
    ),
    "artifact_name": "Use a file name only, without a directory or path separator.",
    "generated_code_content": (
        "Store the complete file content. The server derives content and input digests."
    ),
    "object_dependency_order": "Use zero or a positive execution dependency order.",
    "source_system_dependency_order": "Use zero or a positive source-System dependency order.",
    "is_active": (
        "Use true for current records and false only for an intentional inactive replacement."
    ),
}


def model_dataset_population_rules(dataset: str) -> tuple[str, ...]:
    """Return short, plain rules for one known Model dataset."""
    rules = _DATASET_RULES.get(dataset)
    if rules is None:
        raise ValueError(f"Unknown Model dataset: {dataset}")
    return _COMMON_RULES + rules


def enrich_model_dataset_schema(dataset: str, schema: dict[str, object]) -> None:
    """Attach compact, human-readable guidance to a generated JSON Schema."""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("Model dataset schema has no properties.")
    required_value = schema.get("required", [])
    if not isinstance(required_value, list):
        raise ValueError("Model dataset schema has invalid required fields.")
    required = {value for value in cast(list[object], required_value) if isinstance(value, str)}
    rules = model_dataset_population_rules(dataset)
    columns: list[dict[str, object]] = []
    for name, raw_property in cast(dict[str, object], properties).items():
        if not isinstance(raw_property, dict):
            raise ValueError("Model dataset property schema is invalid.")
        property_schema = cast(dict[str, object], raw_property)
        data_types = _data_types(property_schema)
        enum_values = _enum_values(property_schema)
        constraints = _constraints(property_schema)
        description = _FIELD_GUIDANCE.get(
            name,
            f"Populate {name} from current Snapshot evidence and the active workflow guide.",
        )
        property_schema["description"] = description
        property_schema["x-gds-population-guidance"] = description
        column = DatasetColumnDescription(
            name=name,
            data_types=tuple(data_types),
            required=name in required,
            nullable="null" in data_types,
            description=description,
            population_guidance=description,
            accepted_values=DatasetColumnAcceptedValues(
                kind=("literal" if enum_values else "constrained" if constraints else "freeform"),
                values=tuple(enum_values),
                references=(),
                constraints=constraints,
            ),
            examples=(),
        )
        columns.append(column.model_dump(mode="json"))
    _enrich_nested_field_guidance(schema)
    if dataset == "logical_entity":
        schema["allOf"] = [
            {
                "if": {
                    "properties": {"logical_entity_type": {"const": "other"}},
                    "required": ["logical_entity_type"],
                },
                "then": {"properties": {"logical_entity_type_detail": {"type": "string"}}},
                "else": {"properties": {"logical_entity_type_detail": {"type": "null"}}},
            }
        ]
    schema["x-gds-population-rules"] = list(rules)
    schema["x-gds-columns"] = columns


def _enrich_nested_field_guidance(schema: dict[str, object]) -> None:
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        return
    for raw_definition in cast(dict[str, object], definitions).values():
        if not isinstance(raw_definition, dict):
            continue
        properties = cast(dict[str, object], raw_definition).get("properties")
        if not isinstance(properties, dict):
            continue
        for name, raw_property in cast(dict[str, object], properties).items():
            if not isinstance(raw_property, dict):
                continue
            description = _FIELD_GUIDANCE.get(
                name,
                f"Populate {name} from current Snapshot evidence and the active workflow guide.",
            )
            property_schema = cast(dict[str, object], raw_property)
            property_schema["description"] = description
            property_schema["x-gds-population-guidance"] = description


def _data_types(schema: dict[str, object]) -> list[str]:
    raw_type = schema.get("type")
    if isinstance(raw_type, str):
        return [raw_type]
    if isinstance(raw_type, list):
        return [value for value in cast(list[object], raw_type) if isinstance(value, str)]
    types: list[str] = []
    for branch_name in ("anyOf", "oneOf"):
        branches = schema.get(branch_name)
        if not isinstance(branches, list):
            continue
        for branch in cast(list[object], branches):
            if not isinstance(branch, dict):
                continue
            branch_type = cast(dict[str, object], branch).get("type")
            if isinstance(branch_type, str) and branch_type not in types:
                types.append(branch_type)
    return types or ["object"]


def _enum_values(schema: dict[str, object]) -> list[str | int | float | bool | None]:
    values: list[str | int | float | bool | None] = []
    candidates: list[object] = []
    if isinstance(schema.get("enum"), list):
        candidates.extend(cast(list[object], schema["enum"]))
    for branch_name in ("anyOf", "oneOf"):
        branches = schema.get(branch_name)
        if isinstance(branches, list):
            for branch in cast(list[object], branches):
                if not isinstance(branch, dict):
                    continue
                branch_schema = cast(dict[str, object], branch)
                branch_enum = branch_schema.get("enum")
                if isinstance(branch_enum, list):
                    candidates.extend(cast(list[object], branch_enum))
    for value in candidates:
        if value is None or type(value) in {str, int, float, bool}:
            scalar = cast(str | int | float | bool | None, value)
            if scalar not in values:
                values.append(scalar)
    return values


def _constraints(schema: dict[str, object]) -> dict[str, object]:
    names = {
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "uniqueItems",
    }
    return {name: schema[name] for name in names if name in schema}
