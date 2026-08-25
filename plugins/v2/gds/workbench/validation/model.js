(function (root, factory) {
  "use strict";

  let core = root.GDSCore;
  if (typeof module === "object" && module.exports) core = require("../core.js");
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSModelValidation = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  const ANALYSIS_VALIDATION_FIELDS = [
    "validation_policy_version",
    "validation_result",
    "validation_source_non_null_count",
    "validation_source_distinct_count",
    "validation_target_non_null_count",
    "validation_target_distinct_count",
    "validation_source_missing_target_count",
    "validation_unused_target_count",
    "validation_duplicate_target_key_count",
  ];

  function records(datasets, name) {
    return datasets.get(name)?.records || [];
  }

  function changedRecords(datasets, name) {
    const value = datasets.get(name);
    return Array.isArray(value?.pending) ? value.pending : records(datasets, name);
  }

  function normalized(value) {
    return core.normalize("model", "value", value);
  }

  function names(datasets, dataset, field) {
    return new Set(records(datasets, dataset).map((record) => normalized(record[field])));
  }

  function pair(entity, attribute) {
    return core.stableStringify([normalized(entity), normalized(attribute)]);
  }

  function physicalObject(record) {
    return core.stableStringify(
      ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"].map(
        (field) => normalized(record?.[field]),
      ),
    );
  }

  function prefixedPhysicalObject(record, prefix) {
    return physicalObject(
      Object.fromEntries(
        ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"].map(
          (field) => [field, record?.[`${prefix}_${field}`]],
        ),
      ),
    );
  }

  function missing(issues, dataset, record, field) {
    issues.push({
      code: "reference_not_found",
      dataset,
      record: record + 1,
      field,
      message: "Referenced record is not present in the effective Model graph.",
    });
  }

  function sourceKey(source) {
    if (source?.support_source_type === "assertion") {
      return core.stableStringify([
        "assertion",
        normalized(source.assertion_record?.modeling_assertion_record_key),
      ]);
    }
    const physical = source?.source_object || source?.source_attribute || {};
    const values = [
      source?.support_source_type,
      ...["tenant_code", "system_code", "connection_code", "object_schema", "object_name"].map(
        (field) => normalized(physical[field]),
      ),
    ];
    if (source?.support_source_type === "attribute") {
      values.push(normalized(physical.attribute_name));
    }
    return core.stableStringify(values);
  }

  function validateNestedUniqueness(datasets, issues) {
    function check(dataset, record, index, field, key) {
      const values = Array.isArray(record[field]) ? record[field] : [];
      const seen = new Set();
      for (const value of values) {
        const nestedKey = key(value);
        if (seen.has(nestedKey)) {
          issues.push({
            code: "duplicate_nested_key",
            dataset,
            record: index + 1,
            field,
            message: `${field} contains a normalized duplicate.`,
          });
          return;
        }
        seen.add(nestedKey);
      }
    }

    records(datasets, "modeling_assertion_record").forEach((record, index) => {
      check(
        "modeling_assertion_record",
        record,
        index,
        "modeling_assertion_applicable_layers",
        normalized,
      );
    });
    for (const dataset of ["conceptual_object", "conceptual_relationship"]) {
      records(datasets, dataset).forEach((record, index) => {
        if (dataset === "conceptual_object") {
          check(dataset, record, index, "conceptual_object_aliases", normalized);
        }
        check(dataset, record, index, "supports", sourceKey);
      });
    }
    for (const layer of ["logical", "dimensional"]) {
      const entityDataset = `${layer}_entity`;
      records(datasets, entityDataset).forEach((record, index) => {
        check(entityDataset, record, index, "submodels", (membership) =>
          normalized(membership?.submodel_name),
        );
        check(entityDataset, record, index, "sources", sourceKey);
      });
      const attributeDataset = `${layer}_attribute`;
      records(datasets, attributeDataset).forEach((record, index) => {
        check(attributeDataset, record, index, "sources", sourceKey);
      });
    }
  }

  function validateRecordPolicies(datasets, issues) {
    function invalid(dataset, index, field, message) {
      issues.push({
        code: "record_policy_invalid",
        dataset,
        record: index + 1,
        field,
        message,
      });
    }

    function jsonBytes(value) {
      return new TextEncoder().encode(JSON.stringify(value)).length;
    }

    changedRecords(datasets, "profiling_profile").forEach((record, index) => {
      if (
        record.non_null_count + record.null_count !== record.row_count ||
        (record.blank_count != null && record.blank_count > record.non_null_count) ||
        (record.distinct_count != null && record.distinct_count > record.non_null_count) ||
        (record.min_data_length != null &&
          record.max_data_length != null &&
          record.min_data_length > record.max_data_length)
      ) {
        invalid(
          "profiling_profile",
          index,
          "profiling_counts",
          "Profiling counts or length bounds are inconsistent.",
        );
      }
    });

    changedRecords(datasets, "analysis_result").forEach((record, index) => {
      const validationValues = ANALYSIS_VALIDATION_FIELDS.map((field) => record[field]);
      if (
        validationValues.some((value) => value != null) &&
        validationValues.some((value) => value == null)
      ) {
        invalid(
          "analysis_result",
          index,
          "analysis_validation_group",
          "Analysis validation fields must all be present or all be absent.",
        );
      }
      const endpoint = (prefix) =>
        core.stableStringify(
          [
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
            "attribute_name",
          ].map((field) => normalized(record[`${prefix}_${field}`])),
        );
      if (endpoint("from") === endpoint("to")) {
        invalid("analysis_result", index, "analysis_endpoints", "Analysis endpoints must differ.");
      }
    });
    changedRecords(datasets, "conceptual_relationship").forEach((record, index) => {
      if (
        normalized(record.from_conceptual_object_name) ===
        normalized(record.to_conceptual_object_name)
      ) {
        invalid(
          "conceptual_relationship",
          index,
          "conceptual_relationship_endpoints",
          "Conceptual Relationship endpoints must differ.",
        );
      }
    });
    for (const layer of ["logical", "dimensional"]) {
      const dataset = `${layer}_relationship`;
      changedRecords(datasets, dataset).forEach((record, index) => {
        const endpoint = (prefix) =>
          pair(
            record[`${prefix}_${layer}_entity_name`],
            record[`${prefix}_${layer}_attribute_name`],
          );
        if (endpoint("from") === endpoint("to")) {
          invalid(
            dataset,
            index,
            `${layer}_relationship_endpoints`,
            `${layer} Relationship endpoints must differ.`,
          );
        }
      });
    }
    changedRecords(datasets, "logical_entity").forEach((record, index) => {
      if (
        (record.logical_entity_type === "other") !==
        (record.logical_entity_type_detail != null)
      ) {
        invalid(
          "logical_entity",
          index,
          "logical_entity_type_detail",
          "Logical Entity type detail is required only for other.",
        );
      }
    });
    changedRecords(datasets, "logical_attribute").forEach((record, index) => {
      const natural = record.logical_attribute_is_natural_key === true;
      const surrogate = record.logical_attribute_is_surrogate_key === true;
      const primary = record.logical_attribute_is_primary_key === true;
      if ((natural && surrogate) || ((primary || natural || surrogate) && record.logical_attribute_is_nullable === true)) {
        invalid(
          "logical_attribute",
          index,
          "logical_attribute_key_policy",
          "Logical key flags and nullability are inconsistent.",
        );
      }
    });
    changedRecords(datasets, "dimensional_entity").forEach((record, index) => {
      if (
        (record.dimensional_entity_type === "fact") !==
          (record.dimensional_fact_type != null) ||
        (new Set(["fact", "bridge"]).has(record.dimensional_entity_type) &&
          record.dimensional_entity_grain_definition == null)
      ) {
        invalid(
          "dimensional_entity",
          index,
          "dimensional_entity_policy",
          "Dimensional type, fact type, and grain are inconsistent.",
        );
      }
    });
    changedRecords(datasets, "dimensional_attribute").forEach((record, index) => {
      if (
        record.dimensional_attribute_key_role !== "none" &&
        !new Set(["key", "technical"]).has(record.dimensional_attribute_role)
      ) {
        invalid(
          "dimensional_attribute",
          index,
          "dimensional_attribute_key_role",
          "A Dimensional key role requires a key or technical Attribute.",
        );
      }
      const measure = [
        record.dimensional_attribute_additivity,
        record.dimensional_attribute_default_aggregation,
        record.dimensional_attribute_aggregation_basis,
      ];
      if (
        (record.dimensional_attribute_role === "measure" &&
          (measure[0] == null ||
            measure[1] == null ||
            (measure[0] !== "additive" && measure[2] == null))) ||
        (record.dimensional_attribute_role !== "measure" &&
          measure.some((value) => value != null))
      ) {
        invalid(
          "dimensional_attribute",
          index,
          "dimensional_attribute_measure_policy",
          "Dimensional measure policy fields are inconsistent.",
        );
      }
      if (
        record.dimensional_attribute_is_audit_column !==
        (record.dimensional_attribute_role === "audit")
      ) {
        invalid(
          "dimensional_attribute",
          index,
          "dimensional_attribute_audit_policy",
          "Dimensional audit flag and role must agree.",
        );
      }
    });
    changedRecords(datasets, "mapping_object").forEach((record, index) => {
      const authored = [
        record.artifact_type,
        record.artifact_generation_instructions,
        record.mapping_profile_key,
        record.mapping_profile_version,
        record.mapping_package_document,
        record.object_mapping_transformation_document,
      ];
      if (authored.some((value) => value == null) && authored.some((value) => value != null)) {
        invalid(
          "mapping_object",
          index,
          "mapping_authored_group",
          "Mapping authored fields must be entirely present or absent.",
        );
      }
      if (record.mapping_package_document != null && jsonBytes(record.mapping_package_document) > 524288) {
        invalid(
          "mapping_object",
          index,
          "mapping_package_document",
          "Mapping package document is too large.",
        );
      }
      const transformation = record.object_mapping_transformation_document;
      if (
        transformation != null &&
        (transformation.schema_version !== "1.0" ||
          !new Set(["direct", "derived"]).has(transformation.transformation_kind) ||
          jsonBytes(transformation) > 262144)
      ) {
        invalid(
          "mapping_object",
          index,
          "object_mapping_transformation_document",
          "Object Mapping transformation contract is invalid.",
        );
      }
    });
    changedRecords(datasets, "mapping_attribute").forEach((record, index) => {
      const transformation = record.attribute_mapping_transformation_document;
      if (
        transformation != null &&
        (transformation.schema_version !== "1.0" ||
          !new Set(["direct", "expression"]).has(transformation.transformation_kind) ||
          jsonBytes(transformation) > 65536)
      ) {
        invalid(
          "mapping_attribute",
          index,
          "attribute_mapping_transformation_document",
          "Attribute Mapping transformation contract is invalid.",
        );
      }
    });
  }

  function validateAssertionReference(issues, assertions, source, layer, dataset, index) {
    if (source?.support_source_type !== "assertion") return;
    const key = normalized(source.assertion_record?.modeling_assertion_record_key);
    const assertion = assertions.get(key);
    if (!assertion) {
      missing(issues, dataset, index, "modeling_assertion_record_key");
      return;
    }
    const layers = Array.isArray(assertion.modeling_assertion_applicable_layers)
      ? assertion.modeling_assertion_applicable_layers
      : [];
    if (!layers.includes(layer)) {
      issues.push({
        code: "assertion_layer_invalid",
        dataset,
        record: index + 1,
        field: "modeling_assertion_record_key",
        message: "Referenced Assertion does not apply to this modeling layer.",
      });
    }
  }

  function validateAssertions(datasets, issues) {
    const documents = names(
      datasets,
      "modeling_assertion_document",
      "modeling_assertion_document_name",
    );
    const assertions = new Map(
      records(datasets, "modeling_assertion_record").map((record) => [
        normalized(record.modeling_assertion_record_key),
        record,
      ]),
    );
    records(datasets, "modeling_assertion_record").forEach((record, index) => {
      if (!documents.has(normalized(record.modeling_assertion_document_name))) {
        missing(issues, "modeling_assertion_record", index, "modeling_assertion_document_name");
      }
    });
    for (const [dataset, layer, field] of [
      ["conceptual_object", "conceptual", "supports"],
      ["conceptual_relationship", "conceptual", "supports"],
      ["logical_entity", "logical", "sources"],
      ["logical_attribute", "logical", "sources"],
      ["dimensional_entity", "dimensional", "sources"],
      ["dimensional_attribute", "dimensional", "sources"],
    ]) {
      records(datasets, dataset).forEach((record, index) => {
        for (const source of Array.isArray(record[field]) ? record[field] : []) {
          validateAssertionReference(issues, assertions, source, layer, dataset, index);
        }
      });
    }
  }

  function validateConceptual(datasets, issues) {
    const conceptual = names(datasets, "conceptual_object", "conceptual_object_name");
    records(datasets, "conceptual_relationship").forEach((record, index) => {
      if (
        !conceptual.has(normalized(record.from_conceptual_object_name)) ||
        !conceptual.has(normalized(record.to_conceptual_object_name))
      ) {
        missing(issues, "conceptual_relationship", index, "conceptual_object_name");
      }
    });
  }

  function validateModeledLayer(datasets, layer, issues) {
    const entityDataset = `${layer}_entity`;
    const attributeDataset = `${layer}_attribute`;
    const relationshipDataset = `${layer}_relationship`;
    const entityField = `${layer}_entity_name`;
    const attributeField = `${layer}_attribute_name`;
    const submodels = names(datasets, `${layer}_submodel`, `${layer}_submodel_name`);
    const entities = names(datasets, entityDataset, entityField);
    const attributes = new Set();

    records(datasets, entityDataset).forEach((record, index) => {
      for (const membership of Array.isArray(record.submodels) ? record.submodels : []) {
        if (!submodels.has(normalized(membership.submodel_name))) {
          missing(issues, entityDataset, index, "submodel_name");
        }
      }
    });
    records(datasets, attributeDataset).forEach((record, index) => {
      if (!entities.has(normalized(record[entityField]))) {
        missing(issues, attributeDataset, index, entityField);
      }
      attributes.add(pair(record[entityField], record[attributeField]));
    });
    records(datasets, relationshipDataset).forEach((record, index) => {
      const endpoints = ["from", "to"].map((endpoint) =>
        pair(record[`${endpoint}_${entityField}`], record[`${endpoint}_${attributeField}`]),
      );
      if (endpoints.some((endpoint) => !attributes.has(endpoint))) {
        missing(issues, relationshipDataset, index, attributeField);
      }
    });
    return { entities, attributes };
  }

  function mappingObjectKey(record) {
    return core.stableStringify([
      physicalObject(record),
      normalized(record?.source_system_code),
      record?.modeled_entity_type,
      normalized(record?.modeled_entity_name),
    ]);
  }

  function validateMapping(datasets, logical, dimensional, issues) {
    const dependencies = new Set(
      records(datasets, "mapping_dependency").map((record) =>
        core.stableStringify([
          record.modeled_entity_type,
          normalized(record.source_system_code),
        ]),
      ),
    );
    const mappingObjects = new Set();
    records(datasets, "mapping_object").forEach((record, index) => {
      const dependency = core.stableStringify([
        record.modeled_entity_type,
        normalized(record.source_system_code),
      ]);
      if (!dependencies.has(dependency)) {
        missing(issues, "mapping_object", index, "mapping_dependency");
      }
      const entityNames =
        record.modeled_entity_type === "logical_entity"
          ? logical.entities
          : record.modeled_entity_type === "dimensional_entity"
            ? dimensional.entities
            : new Set();
      if (!entityNames.has(normalized(record.modeled_entity_name))) {
        missing(issues, "mapping_object", index, "modeled_entity_name");
      }
      mappingObjects.add(mappingObjectKey(record));
    });
    records(datasets, "mapping_attribute").forEach((record, index) => {
      if (!mappingObjects.has(mappingObjectKey(record))) {
        missing(issues, "mapping_attribute", index, "mapping_object");
      }
      const attributes =
        record.modeled_entity_type === "logical_entity"
          ? logical.attributes
          : record.modeled_entity_type === "dimensional_entity"
            ? dimensional.attributes
            : new Set();
      if (!attributes.has(pair(record.modeled_entity_name, record.modeled_attribute_name))) {
        missing(issues, "mapping_attribute", index, "modeled_attribute_name");
      }
    });
  }

  function validatePhysicalScope(datasets, scope, issues) {
    function requireScope(
      dataset,
      index,
      field,
      key,
      eligibilityField = null,
      message = "Referenced physical Object is not active in Model Scope.",
    ) {
      const scoped = scope.get(key);
      if (!scoped || (eligibilityField !== null && scoped[eligibilityField] !== true)) {
        issues.push({
          code: "model_scope_reference_invalid",
          dataset,
          record: index + 1,
          field,
          message,
        });
      }
    }

    for (const dataset of ["conceptual_object", "conceptual_relationship"]) {
      changedRecords(datasets, dataset).forEach((record, index) => {
        for (const support of Array.isArray(record.supports) ? record.supports : []) {
          if (support?.support_source_type === "object") {
            requireScope(
              dataset,
              index,
              "source_object",
              physicalObject(support.source_object),
              "is_bronze_source_eligible",
              "Referenced physical Object is not an eligible Bronze source.",
            );
          }
        }
      });
    }
    for (const layer of ["logical", "dimensional"]) {
      const eligibilityField =
        layer === "logical" ? "is_bronze_source_eligible" : "is_dimensional_source_eligible";
      const objectEligibilityMessage =
        layer === "logical"
          ? "Referenced physical Object is not an eligible Bronze source."
          : "Referenced physical Object is not an eligible Silver contribution from applied Logical Mapping.";
      const attributeEligibilityMessage =
        layer === "logical"
          ? "Referenced physical Attribute is not an eligible Bronze source."
          : "Referenced physical Attribute is not an eligible Silver contribution from applied Logical Mapping.";
      const entityDataset = `${layer}_entity`;
      changedRecords(datasets, entityDataset).forEach((record, index) => {
        for (const source of Array.isArray(record.sources) ? record.sources : []) {
          if (source?.support_source_type === "object") {
            requireScope(
              entityDataset,
              index,
              "source_object",
              physicalObject(source.source_object),
              eligibilityField,
              objectEligibilityMessage,
            );
          }
        }
      });
      const attributeDataset = `${layer}_attribute`;
      changedRecords(datasets, attributeDataset).forEach((record, index) => {
        for (const source of Array.isArray(record.sources) ? record.sources : []) {
          if (source?.support_source_type === "attribute") {
            requireScope(
              attributeDataset,
              index,
              "source_attribute",
              physicalObject(source.source_attribute),
              eligibilityField,
              attributeEligibilityMessage,
            );
          }
        }
      });
    }
    changedRecords(datasets, "profiling_profile").forEach((record, index) => {
      requireScope(
        "profiling_profile",
        index,
        "attribute_name",
        physicalObject(record),
        "is_bronze_source_eligible",
        "Referenced physical Attribute is not an eligible Bronze source.",
      );
    });
    changedRecords(datasets, "analysis_result").forEach((record, index) => {
      for (const endpoint of ["from", "to"]) {
        requireScope(
          "analysis_result",
          index,
          `${endpoint}_attribute_name`,
          prefixedPhysicalObject(record, endpoint),
          "is_bronze_source_eligible",
          "Referenced physical Attribute is not an eligible Bronze source.",
        );
      }
    });
    for (const dataset of ["mapping_object", "mapping_attribute"]) {
      changedRecords(datasets, dataset).forEach((record, index) => {
        const eligibilityField =
          record.modeled_entity_type === "logical_entity"
            ? "is_logical_mapping_target_eligible"
            : "is_dimensional_mapping_target_eligible";
        requireScope(
          dataset,
          index,
          dataset === "mapping_object" ? "object_name" : "attribute_name",
          physicalObject(record),
          eligibilityField,
          "Referenced Mapping target is not eligible for its modeled layer.",
        );
      });
    }
  }

  function validateGraph(datasets) {
    const issues = [];
    validateNestedUniqueness(datasets, issues);
    validateRecordPolicies(datasets, issues);
    validateAssertions(datasets, issues);
    validateConceptual(datasets, issues);
    const logical = validateModeledLayer(datasets, "logical", issues);
    const dimensional = validateModeledLayer(datasets, "dimensional", issues);
    const scope = new Map(
      records(datasets, "model_scope")
        .filter((record) => record.is_active === true)
        .map((record) => [physicalObject(record), record]),
    );
    validatePhysicalScope(datasets, scope, issues);
    validateMapping(datasets, logical, dimensional, issues);
    return issues;
  }

  return { validateGraph };
});
