(function (root) {
  "use strict";

  const METADATA_DATASETS = Object.freeze([
    "source_object", "source_attribute", "bronze_object", "bronze_attribute",
    "silver_object", "silver_attribute", "gold_object", "gold_attribute",
    "ingestion_object_mapping", "ingestion_attribute_mapping", "copy_group",
    "member_group", "copy_group_control", "copy", "process_group", "process"
  ]);
  const METADATA_SNAPSHOT_DATASETS = Object.freeze([
    "project", "tenant", "system", "connection", "tenant_metadata_discovery_scope",
    "system_type", "connection_type", "object_type", "zone", "chunk_type",
    "file_type", "data_operation", "process_type", ...METADATA_DATASETS
  ]);
  const MODEL_DATASETS = Object.freeze([
    "model_details", "model_scope", "profiling_profile", "analysis_result",
    "modeling_assertion_document", "modeling_assertion_record",
    "conceptual_object", "conceptual_relationship", "logical_submodel",
    "logical_entity", "logical_attribute", "logical_relationship",
    "dimensional_submodel", "dimensional_entity", "dimensional_attribute",
    "dimensional_relationship", "mapping_dependency", "mapping_object",
    "mapping_attribute"
  ]);
  const MAX_METADATA_DATASET_RECORDS = 50000;
  const MAX_MODEL_DATASET_RECORDS = 20000;
  const MAX_MODEL_TOTAL_RECORDS = 50000;
  const MAX_DATASET_BYTES = 16777216;
  const MAX_MODEL_SECTION_BYTES = 16777216;
  const metadataDatasets = new Set(METADATA_DATASETS);
  const metadataSnapshotDatasets = new Set(METADATA_SNAPSHOT_DATASETS);
  const modelDatasets = new Set(MODEL_DATASETS);

  const PROFILES = Object.freeze({
    metadata: Object.freeze({
      kind: "metadata",
      snapshotDirectory: "metadata-snapshot",
      changeSetDirectory: "change-set",
      controlFile: "change-set.json",
      serverIdField: "metadata_change_set_id",
      maxDatasetRecords: MAX_METADATA_DATASET_RECORDS
    }),
    model: Object.freeze({
      kind: "model",
      snapshotDirectory: "model-snapshot",
      changeSetDirectory: "model-change-set",
      controlFile: "model-change-set.json",
      serverIdField: "model_change_set_id",
      maxDatasetRecords: MAX_MODEL_DATASET_RECORDS
    })
  });

  function clone(value) {
    return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  }

  function safePathParts(path) {
    if (typeof path !== "string" || !path || path.includes("\\") || path.startsWith("/")) {
      throw new Error("Snapshot contains an unsafe file path.");
    }
    const parts = path.split("/");
    if (parts.some((part) => !part || part === "." || part === ".." || part.includes(":"))) {
      throw new Error("Snapshot contains an unsafe file path.");
    }
    return parts;
  }

  function parseJson(text, label) {
    try {
      return JSON.parse(String(text).replace(/^\uFEFF/, ""));
    } catch (error) {
      throw new Error(`${label} is not valid JSON (${error.message}).`);
    }
  }

  function parseRows(text, path) {
    const value = String(text).replace(/^\uFEFF/, "");
    if (/\.(jsonl|ndjson)$/i.test(path)) {
      const rows = [];
      value.split(/\r?\n/).forEach((line, index) => {
        if (!line.trim()) return;
        const row = parseJson(line, `${path} line ${index + 1}`);
        if (!isObject(row)) throw new Error(`${path} line ${index + 1} must be a JSON object.`);
        rows.push(row);
      });
      return rows;
    }
    const parsed = parseJson(value, path);
    if (!Array.isArray(parsed) || parsed.some((row) => !isObject(row))) {
      throw new Error(`${path} must contain one JSON array of objects.`);
    }
    return parsed;
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function schemaKind(schema) {
    const dataset = schema?.["x-gds-dataset"];
    if (modelDatasets.has(dataset)) return "model";
    if (metadataSnapshotDatasets.has(dataset)) return "metadata";
    throw new Error("Dataset schema does not identify a supported GDS dataset.");
  }

  function profileForManifest(manifest) {
    const profile = PROFILES[manifest?.snapshot_kind];
    if (!profile || manifest?.schema_version !== "2.0") {
      throw new Error("Only Metadata or Model Snapshot schema version 2.0 is supported.");
    }
    return profile;
  }

  function metadataKeyNormalization(schema) {
    const value = schema?.["x-gds-key-normalization"];
    if (!isObject(value) || value.version !== "1.0" ||
        value.string_field_suffixes?.join("\u001f") !== "_code\u001f_name\u001f_schema" ||
        value.trim_code_points?.join("\u001f") !== "U+0020" ||
        value.case !== "unicode-lowercase" || value.unicode_normalization !== "none" ||
        value.other_values !== "identity") {
      throw new Error("Dataset schema has no valid GDS key-normalization contract.");
    }
    return value;
  }

  function normalizeKeyValue(column, value, schema) {
    const kind = schemaKind(schema);
    if (kind === "model") {
      if (typeof value === "string") {
        // Python's casefold is broader than JavaScript lowercase. Server validation
        // remains authoritative for uncommon Unicode key collisions.
        return value.replace(/^ +| +$/g, "").toLocaleLowerCase("en-US");
      }
      if (value === null) return "null";
      return JSON.stringify(value);
    }
    const normalization = metadataKeyNormalization(schema);
    if (typeof value === "string" && normalization.string_field_suffixes.some((suffix) => column.endsWith(suffix))) {
      return value.replace(/^ +| +$/g, "").toLocaleLowerCase("en-US");
    }
    if (typeof value === "string") return value;
    if (value === null) return "null";
    return JSON.stringify(value);
  }

  function keyFor(record, columns, schema) {
    return JSON.stringify(columns.map((column) => {
      const value = record[column];
      return [value === null ? "null" : typeof value, normalizeKeyValue(column, value, schema)];
    }));
  }

  function canonicalColumns(schema) {
    const columns = schema && schema["x-gds-canonical-key"];
    const singleton = schema?.["x-gds-dataset"] === "model_details";
    if (!Array.isArray(columns) || (!columns.length && !singleton) || columns.some((name) => typeof name !== "string" || !name)) {
      throw new Error("Dataset schema has no valid GDS canonical key.");
    }
    return columns;
  }

  function assertEligibleSchema(dataset, schema) {
    const supported = metadataDatasets.has(dataset) || modelDatasets.has(dataset);
    if (!supported || schema?.["x-gds-dataset"] !== dataset || schema?.["x-gds-change-set-eligible"] !== true) {
      throw new Error(`${dataset} is not Change Set eligible.`);
    }
    if (schemaKind(schema) === "metadata") metadataKeyNormalization(schema);
  }

  function validDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return false;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(Date.UTC(year, month - 1, day));
    return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  }

  function validDateTime(value) {
    return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && !Number.isNaN(Date.parse(value));
  }

  function typeMatches(value, type) {
    if (!type) return true;
    if (type === "null") return value === null;
    if (type === "string") return typeof value === "string";
    if (type === "boolean") return typeof value === "boolean";
    if (type === "integer") return Number.isInteger(value);
    if (type === "number") return typeof value === "number" && Number.isFinite(value);
    if (type === "array") return Array.isArray(value);
    if (type === "object") return isObject(value);
    return true;
  }

  function fieldPath(parent, child) {
    return parent === "$" ? child : `${parent}.${child}`;
  }

  function resolveReference(rootSchema, reference) {
    if (typeof reference !== "string" || !reference.startsWith("#/$defs/")) {
      throw new Error("Snapshot schema contains an unsupported JSON Schema reference.");
    }
    const name = reference.slice(8).replace(/~1/g, "/").replace(/~0/g, "~");
    const resolved = rootSchema?.$defs?.[name];
    if (!isObject(resolved)) throw new Error("Snapshot schema contains a missing JSON Schema reference.");
    return resolved;
  }

  function validateValue(value, node, rootSchema, path = "$") {
    if (!isObject(node)) return [{ field: path, message: "Schema node is invalid." }];
    if (typeof node.$ref === "string") {
      const referenced = validateValue(value, resolveReference(rootSchema, node.$ref), rootSchema, path);
      const siblings = Object.fromEntries(Object.entries(node).filter(([key]) => key !== "$ref"));
      return Object.keys(siblings).length
        ? [...referenced, ...validateValue(value, siblings, rootSchema, path)]
        : referenced;
    }
    if (Array.isArray(node.allOf)) {
      return node.allOf.flatMap((candidate) => validateValue(value, candidate, rootSchema, path));
    }
    for (const keyword of ["anyOf", "oneOf"]) {
      if (!Array.isArray(node[keyword])) continue;
      const outcomes = node[keyword].map((candidate) => validateValue(value, candidate, rootSchema, path));
      const matches = outcomes.filter((errors) => errors.length === 0).length;
      if ((keyword === "anyOf" && matches > 0) || (keyword === "oneOf" && matches === 1)) return [];
      const closest = outcomes.sort((left, right) => left.length - right.length)[0] || [];
      return closest.length ? closest : [{ field: path, message: `Does not match ${keyword} allowed schema.` }];
    }

    const expectedTypes = Array.isArray(node.type) ? node.type : node.type ? [node.type] : [];
    if (expectedTypes.length && !expectedTypes.some((type) => typeMatches(value, type))) {
      return [{ field: path, message: `Expected ${expectedTypes.join(" or ")}.` }];
    }
    if (Object.prototype.hasOwnProperty.call(node, "const") && JSON.stringify(value) !== JSON.stringify(node.const)) {
      return [{ field: path, message: `Must equal ${JSON.stringify(node.const)}.` }];
    }
    if (Array.isArray(node.enum) && !node.enum.some((item) => JSON.stringify(item) === JSON.stringify(value))) {
      return [{ field: path, message: `Must be one of ${node.enum.map((item) => JSON.stringify(item)).join(", ")}.` }];
    }

    const errors = [];
    if (typeof value === "string") {
      if (Number.isInteger(node.minLength) && value.length < node.minLength) errors.push({ field: path, message: `Must contain at least ${node.minLength} characters.` });
      if (Number.isInteger(node.maxLength) && value.length > node.maxLength) errors.push({ field: path, message: `Must contain at most ${node.maxLength} characters.` });
      if (typeof node.pattern === "string") {
        try {
          if (!new RegExp(node.pattern, "u").test(value)) errors.push({ field: path, message: "Does not match the required text pattern." });
        } catch (_) {
          errors.push({ field: path, message: "The Snapshot schema contains an invalid text pattern." });
        }
      }
      if (node.format === "date" && !validDate(value)) errors.push({ field: path, message: "Must be a valid YYYY-MM-DD date." });
      if (node.format === "date-time" && !validDateTime(value)) errors.push({ field: path, message: "Must be a valid ISO 8601 date-time with a timezone." });
    }
    if (typeof value === "number") {
      if (typeof node.minimum === "number" && value < node.minimum) errors.push({ field: path, message: `Must be at least ${node.minimum}.` });
      if (typeof node.maximum === "number" && value > node.maximum) errors.push({ field: path, message: `Must be at most ${node.maximum}.` });
      if (typeof node.exclusiveMinimum === "number" && value <= node.exclusiveMinimum) errors.push({ field: path, message: `Must be greater than ${node.exclusiveMinimum}.` });
      if (typeof node.exclusiveMaximum === "number" && value >= node.exclusiveMaximum) errors.push({ field: path, message: `Must be less than ${node.exclusiveMaximum}.` });
    }
    if (Array.isArray(value)) {
      if (Number.isInteger(node.minItems) && value.length < node.minItems) errors.push({ field: path, message: `Must contain at least ${node.minItems} items.` });
      if (Number.isInteger(node.maxItems) && value.length > node.maxItems) errors.push({ field: path, message: `Must contain at most ${node.maxItems} items.` });
      if (node.uniqueItems === true) {
        const seen = new Set(value.map((item) => JSON.stringify(item)));
        if (seen.size !== value.length) errors.push({ field: path, message: "Array items must be unique." });
      }
      if (isObject(node.items)) {
        value.forEach((item, index) => errors.push(...validateValue(item, node.items, rootSchema, `${path}[${index}]`)));
      }
    }
    if (isObject(value)) {
      const properties = isObject(node.properties) ? node.properties : {};
      const required = Array.isArray(node.required) ? node.required : [];
      for (const field of required) {
        if (!Object.prototype.hasOwnProperty.call(value, field)) errors.push({ field: fieldPath(path, field), message: "Required field is missing." });
      }
      for (const [field, nested] of Object.entries(value)) {
        const nestedPath = fieldPath(path, field);
        if (path === "$" && (field.toLocaleLowerCase("en-US") === "id" || field.toLocaleLowerCase("en-US").endsWith("_id"))) {
          errors.push({ field: nestedPath, message: "Database IDs are forbidden." });
        } else if (Object.prototype.hasOwnProperty.call(properties, field)) {
          errors.push(...validateValue(nested, properties[field], rootSchema, nestedPath));
        } else if (node.additionalProperties === false) {
          errors.push({ field: nestedPath, message: "Unknown fields and database IDs are not allowed." });
        } else if (isObject(node.additionalProperties)) {
          errors.push(...validateValue(nested, node.additionalProperties, rootSchema, nestedPath));
        }
      }
    }
    return errors;
  }

  function validateSchema(schema, dataset, requireEligible = false) {
    if (!isObject(schema) || schema.type !== "object" || schema.additionalProperties !== false ||
        !isObject(schema.properties) || !Array.isArray(schema.required) ||
        schema["x-gds-dataset"] !== dataset || !Array.isArray(schema["x-gds-canonical-key"]) ||
        (requireEligible && schema["x-gds-change-set-eligible"] !== true)) {
      throw new Error("Snapshot dataset schema contract is invalid.");
    }
    const kind = schemaKind(schema);
    if (kind === "metadata") {
      if (!Array.isArray(schema["x-gds-unique-constraints"])) throw new Error("Snapshot dataset schema contract is invalid.");
      metadataKeyNormalization(schema);
    } else {
      if (schema["x-gds-database-ids-included"] !== false || !isObject(schema.$defs)) {
        throw new Error("Model dataset schema contract is invalid.");
      }
    }
    canonicalColumns(schema);
    return schema;
  }

  function validateRecord(record, schema) {
    const errors = validateValue(record, schema, schema, "$");
    for (const field of canonicalColumns(schema)) {
      if (!Object.prototype.hasOwnProperty.call(record, field)) {
        errors.push({ field, message: "Canonical-key value is required." });
      }
    }
    if (schemaKind(schema) === "model" && isObject(record)) {
      errors.push(...modelSemanticIssues(record, schema["x-gds-dataset"]));
    }
    return errors;
  }

  function normalizedText(value) {
    return typeof value === "string" ? value.replace(/^ +| +$/g, "").toLocaleLowerCase("en-US") : value;
  }

  function jsonBytes(value) {
    return new TextEncoder().encode(JSON.stringify(value)).byteLength;
  }

  function allOrNone(record, fields) {
    const present = fields.map((field) => record[field] !== null && record[field] !== undefined);
    return present.every(Boolean) || present.every((value) => !value);
  }

  function sameTextTuple(record, left, right) {
    return left.every((field, index) => normalizedText(record[field]) === normalizedText(record[right[index]]));
  }

  function sourceKey(source) {
    if (!isObject(source)) return JSON.stringify(source);
    const kind = source.support_source_type;
    if (kind === "assertion") return JSON.stringify([kind, normalizedText(source.assertion_record?.modeling_assertion_record_key)]);
    const physical = source.source_object || source.source_attribute;
    if (!isObject(physical)) return JSON.stringify(source);
    return JSON.stringify([
      kind,
      normalizedText(physical.tenant_code), normalizedText(physical.system_code),
      normalizedText(physical.connection_code), normalizedText(physical.object_schema),
      normalizedText(physical.object_name), normalizedText(physical.attribute_name)
    ]);
  }

  function duplicateIssue(values, key, field, message) {
    if (!Array.isArray(values)) return [];
    const keys = values.map(key);
    return new Set(keys).size === keys.length ? [] : [{ field, message }];
  }

  function modelSemanticIssues(record, dataset) {
    const errors = [];
    const issue = (field, message) => errors.push({ field, message });

    if (dataset === "model_details") {
      const silver = ["silver_model_naming_template", "silver_model_audit_columns_template"];
      const gold = ["gold_model_naming_template", "gold_model_technical_columns_template", "gold_model_audit_columns_template"];
      if (!allOrNone(record, silver)) issue(silver[0], "Silver Model policy fields must be entirely present or absent.");
      if (!allOrNone(record, gold)) issue(gold[0], "Gold Model policy fields must be entirely present or absent.");
      [...silver, ...gold].forEach((field) => {
        if (record[field] !== null && record[field] !== undefined && jsonBytes(record[field]) > 262144) issue(field, "Model policy template exceeds 256 KiB.");
      });
    }
    if (dataset === "profiling_profile") {
      if (record.non_null_count + record.null_count !== record.row_count) issue("row_count", "Non-null and null counts must equal row count.");
      if (record.blank_count !== null && record.blank_count > record.non_null_count) issue("blank_count", "Blank count cannot exceed non-null count.");
      if (record.distinct_count !== null && record.distinct_count > record.non_null_count) issue("distinct_count", "Distinct count cannot exceed non-null count.");
      if (record.min_data_length !== null && record.max_data_length !== null && record.min_data_length > record.max_data_length) issue("min_data_length", "Minimum length cannot exceed maximum length.");
    }
    if (dataset === "analysis_result" && sameTextTuple(
      record,
      ["from_tenant_code", "from_system_code", "from_connection_code", "from_object_schema", "from_object_name", "from_attribute_name"],
      ["to_tenant_code", "to_system_code", "to_connection_code", "to_object_schema", "to_object_name", "to_attribute_name"]
    )) issue("to_attribute_name", "Analysis endpoints must be different.");
    if (dataset === "modeling_assertion_record") {
      errors.push(...duplicateIssue(record.modeling_assertion_applicable_layers, normalizedText, "modeling_assertion_applicable_layers", "Applicable layers must be unique."));
    }
    if (dataset === "conceptual_object") {
      errors.push(...duplicateIssue(record.conceptual_object_aliases, normalizedText, "conceptual_object_aliases", "Conceptual aliases must be unique."));
      errors.push(...duplicateIssue(record.supports, sourceKey, "supports", "Conceptual supports must be unique by source key."));
    }
    if (dataset === "conceptual_relationship") {
      if (normalizedText(record.from_conceptual_object_name) === normalizedText(record.to_conceptual_object_name)) issue("to_conceptual_object_name", "Conceptual Relationship endpoints must be different.");
      errors.push(...duplicateIssue(record.supports, sourceKey, "supports", "Conceptual supports must be unique by source key."));
    }
    if (dataset === "logical_entity") {
      if ((record.logical_entity_type === "other") !== (record.logical_entity_type_detail !== null)) issue("logical_entity_type_detail", "Type detail is required only for type other.");
      errors.push(...duplicateIssue(record.submodels, (value) => normalizedText(value?.submodel_name), "submodels", "Submodel memberships must be unique."));
      errors.push(...duplicateIssue(record.sources, sourceKey, "sources", "Entity sources must be unique."));
    }
    if (dataset === "logical_attribute") {
      if (record.logical_attribute_is_natural_key && record.logical_attribute_is_surrogate_key) issue("logical_attribute_is_surrogate_key", "An Attribute cannot be both natural and surrogate key.");
      const anyKey = record.logical_attribute_is_primary_key || record.logical_attribute_is_natural_key || record.logical_attribute_is_surrogate_key;
      if (anyKey && record.logical_attribute_is_nullable) issue("logical_attribute_is_nullable", "A key Attribute cannot be nullable.");
      errors.push(...duplicateIssue(record.sources, sourceKey, "sources", "Attribute sources must be unique."));
    }
    if (dataset === "logical_relationship" && sameTextTuple(
      record,
      ["from_logical_entity_name", "from_logical_attribute_name"],
      ["to_logical_entity_name", "to_logical_attribute_name"]
    )) issue("to_logical_attribute_name", "Logical Relationship endpoints must be different.");
    if (dataset === "dimensional_entity") {
      if ((record.dimensional_entity_type === "fact") !== (record.dimensional_fact_type !== null)) issue("dimensional_fact_type", "Fact type is required only for facts.");
      if (["fact", "bridge"].includes(record.dimensional_entity_type) && record.dimensional_entity_grain_definition === null) issue("dimensional_entity_grain_definition", "Fact and bridge Entities require a grain definition.");
      errors.push(...duplicateIssue(record.submodels, (value) => normalizedText(value?.submodel_name), "submodels", "Submodel memberships must be unique."));
      errors.push(...duplicateIssue(record.sources, sourceKey, "sources", "Entity sources must be unique."));
    }
    if (dataset === "dimensional_attribute") {
      if (record.dimensional_attribute_key_role !== "none" && !["key", "technical"].includes(record.dimensional_attribute_role)) issue("dimensional_attribute_key_role", "A key role requires a key or technical Attribute.");
      const measureFields = [record.dimensional_attribute_additivity, record.dimensional_attribute_default_aggregation, record.dimensional_attribute_aggregation_basis];
      if (record.dimensional_attribute_role === "measure") {
        if (measureFields[0] === null || measureFields[1] === null) issue("dimensional_attribute_additivity", "A measure requires additivity and default aggregation.");
        if (measureFields[0] !== null && measureFields[0] !== "additive" && measureFields[2] === null) issue("dimensional_attribute_aggregation_basis", "A semi/non-additive measure requires an aggregation basis.");
      } else if (measureFields.some((value) => value !== null)) issue("dimensional_attribute_additivity", "Measure policy fields are valid only for measures.");
      if (record.dimensional_attribute_is_audit_column !== (record.dimensional_attribute_role === "audit")) issue("dimensional_attribute_is_audit_column", "Audit flag and role must agree.");
      errors.push(...duplicateIssue(record.sources, sourceKey, "sources", "Attribute sources must be unique."));
    }
    if (dataset === "dimensional_relationship" && sameTextTuple(
      record,
      ["from_dimensional_entity_name", "from_dimensional_attribute_name"],
      ["to_dimensional_entity_name", "to_dimensional_attribute_name"]
    )) issue("to_dimensional_attribute_name", "Dimensional Relationship endpoints must be different.");
    if (dataset === "mapping_object") {
      const authored = ["artifact_type", "artifact_generation_instructions", "mapping_profile_key", "mapping_profile_version", "mapping_package_document", "object_mapping_transformation_document"];
      if (!allOrNone(record, authored)) issue("artifact_type", "Mapping authored fields must be entirely present or absent.");
      if (record.mapping_package_document !== null && jsonBytes(record.mapping_package_document) > 524288) issue("mapping_package_document", "Mapping package document exceeds 512 KiB.");
      const transform = record.object_mapping_transformation_document;
      if (transform !== null && (!isObject(transform) || transform.schema_version !== "1.0" || !["direct", "derived"].includes(transform.transformation_kind) || jsonBytes(transform) > 262144)) issue("object_mapping_transformation_document", "Object Mapping transformation contract is invalid.");
    }
    if (dataset === "mapping_attribute") {
      const transform = record.attribute_mapping_transformation_document;
      if (transform !== null && (!isObject(transform) || transform.schema_version !== "1.0" || !["direct", "expression"].includes(transform.transformation_kind) || jsonBytes(transform) > 65536)) issue("attribute_mapping_transformation_document", "Attribute Mapping transformation contract is invalid.");
    }
    return errors;
  }

  function uniqueConstraints(schema) {
    const declared = Array.isArray(schema?.["x-gds-unique-constraints"])
      ? schema["x-gds-unique-constraints"].filter((group) => Array.isArray(group) && group.length)
      : [];
    const canonical = canonicalColumns(schema);
    return declared.length ? declared : [canonical];
  }

  function validateDataset(rows, schema) {
    if (!Array.isArray(rows)) return [{ row: null, field: "$", message: "Dataset must be one JSON array." }];
    const errors = [];
    const maxRecords = schemaKind(schema) === "model" ? MAX_MODEL_DATASET_RECORDS : MAX_METADATA_DATASET_RECORDS;
    if (rows.length > maxRecords) {
      errors.push({ row: null, field: "$", message: `Dataset exceeds ${maxRecords.toLocaleString("en-US")} records.` });
      return errors;
    }
    rows.forEach((row, index) => {
      validateRecord(row, schema).forEach((issue) => errors.push({ row: index, ...issue }));
    });
    for (const columns of uniqueConstraints(schema)) {
      const seen = new Map();
      rows.forEach((row, index) => {
        if (!isObject(row) || columns.some((field) => row[field] === undefined)) return;
        const key = keyFor(row, columns, schema);
        if (seen.has(key)) {
          const other = seen.get(key);
          const label = columns.length ? columns.join(", ") : "singleton dataset";
          const message = `Duplicates row ${other + 1} for ${label}.`;
          (columns.length ? columns : ["$"]).forEach((field) => errors.push({ row: index, field, message }));
        } else {
          seen.set(key, index);
        }
      });
    }
    return errors;
  }

  function serializeDataset(rows) {
    const content = JSON.stringify(rows, null, 2) + "\n";
    const bytes = new TextEncoder().encode(content).byteLength;
    if (bytes > MAX_DATASET_BYTES) throw new Error("Dataset exceeds the 16 MiB Stage limit.");
    return { content, bytes };
  }

  function mergeRecord(rows, record, schema, dataset) {
    assertEligibleSchema(dataset, schema);
    const recordErrors = validateRecord(record, schema);
    if (recordErrors.length) return { rows: clone(rows), action: "rejected", index: -1, errors: recordErrors };
    const columns = canonicalColumns(schema);
    const wanted = keyFor(record, columns, schema);
    const next = clone(rows);
    const index = next.findIndex((item) => keyFor(item, columns, schema) === wanted);
    const action = index < 0 ? "inserted" : "replaced";
    if (index < 0) next.push(clone(record)); else next[index] = clone(record);
    const errors = validateDataset(next, schema);
    return errors.length ? { rows: clone(rows), action: "rejected", index, errors } : { rows: next, action, index: index < 0 ? next.length - 1 : index, errors: [] };
  }

  function mergeRecords(rows, records, schema, dataset) {
    assertEligibleSchema(dataset, schema);
    if (!Array.isArray(records) || !records.length) {
      return { rows: clone(rows), action: "rejected", indexes: [], errors: [{ field: "$", message: "Choose at least one record." }] };
    }
    const columns = canonicalColumns(schema);
    const next = clone(rows);
    const indexByKey = new Map(next.map((item, index) => [keyFor(item, columns, schema), index]));
    const indexes = [];
    for (const record of records) {
      const recordErrors = validateRecord(record, schema);
      if (recordErrors.length) return { rows: clone(rows), action: "rejected", indexes: [], errors: recordErrors };
      const wanted = keyFor(record, columns, schema);
      let index = indexByKey.get(wanted);
      if (index === undefined) {
        index = next.length;
        next.push(clone(record));
        indexByKey.set(wanted, index);
      } else {
        next[index] = clone(record);
      }
      indexes.push(index);
    }
    const errors = validateDataset(next, schema);
    return errors.length
      ? { rows: clone(rows), action: "rejected", indexes: [], errors }
      : { rows: next, action: "merged", indexes, errors: [] };
  }

  function removeRecord(rows, keyRecord, schema, dataset) {
    assertEligibleSchema(dataset, schema);
    const columns = canonicalColumns(schema);
    const provided = Object.keys(keyRecord || {}).sort();
    if (provided.join("\u001f") !== [...columns].sort().join("\u001f")) throw new Error("Removal key must contain exactly the canonical-key fields.");
    const wanted = keyFor(keyRecord, columns, schema);
    const index = rows.findIndex((item) => keyFor(item, columns, schema) === wanted);
    if (index < 0) throw new Error("No matching local Change Set record was found.");
    const next = clone(rows);
    next.splice(index, 1);
    return next;
  }

  function createLocalState(manifest) {
    const profile = profileForManifest(manifest);
    if (typeof manifest.snapshot_id !== "string") {
      throw new Error("Snapshot manifest cannot initialize a local Change Set.");
    }
    if (profile.kind === "model") {
      if (!Number.isInteger(manifest.model_id) || manifest.model_id <= 0 || typeof manifest.model_name !== "string" || !manifest.model_name.trim() || !Number.isInteger(manifest.model_revision) || manifest.model_revision <= 0) {
        throw new Error("Model Snapshot identity is incomplete.");
      }
      return {
        format_version: "1.0",
        model: {
          model_id: manifest.model_id,
          model_name: manifest.model_name,
          model_revision: manifest.model_revision
        },
        snapshot: {
          snapshot_id: manifest.snapshot_id,
          path: "../model-snapshot",
          usage: "local",
          outdated_snapshot_warning_acknowledged: false
        },
        server_change_set: {
          model_change_set_id: null,
          draft_revision: null,
          status: "local"
        },
        datasets: {}
      };
    }
    if (typeof manifest.tenant_code !== "string" || !manifest.tenant_code.trim()) {
      throw new Error("Metadata Snapshot identity is incomplete.");
    }
    return {
      format_version: "1.0",
      tenant: { tenant_id: null, tenant_code: manifest.tenant_code },
      snapshot: {
        snapshot_id: manifest.snapshot_id,
        path: "../metadata-snapshot",
        usage: "local",
        outdated_snapshot_warning_acknowledged: false
      },
      server_change_set: {
        metadata_change_set_id: null,
        draft_revision: null,
        status: "local"
      },
      datasets: {}
    };
  }

  function sameRecord(left, right, schema) {
    const fields = Object.keys(schema?.properties || {});
    return fields.every((field) => JSON.stringify(left?.[field]) === JSON.stringify(right?.[field]));
  }

  function activeState(record) {
    if (record?.is_active === true) return true;
    if (record?.is_active === false) return false;
    const status = Object.entries(record || {}).find(([field]) => field.endsWith("_status"))?.[1];
    if (status === "active" || status === "needs_review") return true;
    if (status === "inactive" || status === "deprecated") return false;
    return null;
  }

  function classifyRecord(record, snapshotRows, schema) {
    const columns = canonicalColumns(schema);
    const wanted = keyFor(record, columns, schema);
    const base = snapshotRows.find((item) => keyFor(item, columns, schema) === wanted);
    if (!base) return "insert";
    if (sameRecord(record, base, schema)) return "no_change";
    if (activeState(base) === true && activeState(record) === false) return "deactivate";
    if (activeState(base) === false && activeState(record) === true) return "reactivate";
    return "update";
  }

  function diffRecord(record, baseline, schema) {
    const fields = Object.keys(schema?.properties || {});
    const changes = fields.filter((field) => JSON.stringify(record?.[field]) !== JSON.stringify(baseline?.[field]));
    let action = "insert";
    if (baseline) {
      if (!changes.length) action = "no_change";
      else if (activeState(baseline) === true && activeState(record) === false) action = "deactivate";
      else if (activeState(baseline) === false && activeState(record) === true) action = "reactivate";
      else action = "update";
    }
    return {
      action,
      changes: changes.map((field) => ({ field, before: baseline?.[field], after: record?.[field] }))
    };
  }

  const MODEL_AGGREGATE_FIELDS = Object.freeze({
    model_details: ["model_scope", "details"],
    model_scope: ["model_scope", "objects"],
    profiling_profile: ["profiling", "profiles"],
    analysis_result: ["analysis", "relationships"],
    modeling_assertion_document: ["assertion", "documents"],
    modeling_assertion_record: ["assertion", "records"],
    conceptual_object: ["conceptual", "objects"],
    conceptual_relationship: ["conceptual", "relationships"],
    logical_submodel: ["logical", "submodels"],
    logical_entity: ["logical", "entities"],
    logical_attribute: ["logical", "attributes"],
    logical_relationship: ["logical", "relationships"],
    dimensional_submodel: ["dimensional", "submodels"],
    dimensional_entity: ["dimensional", "entities"],
    dimensional_attribute: ["dimensional", "attributes"],
    dimensional_relationship: ["dimensional", "relationships"],
    mapping_dependency: ["mapping", "dependencies"],
    mapping_object: ["mapping", "objects"],
    mapping_attribute: ["mapping", "attributes"]
  });

  function datasetRows(datasets, name) {
    const value = datasets instanceof Map ? datasets.get(name) : datasets?.[name];
    if (!Array.isArray(value)) throw new Error(`${name} must be an array of Model records.`);
    return value;
  }

  function modelSnapshotFromDatasets(manifest, datasets) {
    if (profileForManifest(manifest).kind !== "model") throw new Error("A Model manifest is required.");
    let recordTotal = 0;
    for (const name of MODEL_DATASETS) {
      const rows = datasetRows(datasets, name);
      if (rows.length > MAX_MODEL_DATASET_RECORDS) throw new Error(`${name} exceeds ${MAX_MODEL_DATASET_RECORDS.toLocaleString("en-US")} records.`);
      recordTotal += rows.length;
    }
    if (recordTotal > MAX_MODEL_TOTAL_RECORDS) throw new Error(`Proposed Model Snapshot exceeds ${MAX_MODEL_TOTAL_RECORDS.toLocaleString("en-US")} total records.`);
    const details = datasetRows(datasets, "model_details");
    if (details.length !== 1 || !isObject(details[0])) throw new Error("model_details must contain exactly one record.");
    const snapshot = {
      schema_version: "1.0",
      model_id: manifest.model_id,
      model_name: details[0].model_name,
      model_revision: manifest.model_revision,
      model_scope: { details: clone(details[0]), objects: [] },
      profiling: { profiles: [] },
      analysis: { relationships: [] },
      assertion: { documents: [], records: [] },
      conceptual: { objects: [], relationships: [] },
      logical: { submodels: [], entities: [], attributes: [], relationships: [] },
      dimensional: { submodels: [], entities: [], attributes: [], relationships: [] },
      mapping: { dependencies: [], objects: [], attributes: [] }
    };
    for (const name of MODEL_DATASETS) {
      if (name === "model_details") continue;
      const [section, field] = MODEL_AGGREGATE_FIELDS[name];
      snapshot[section][field] = clone(datasetRows(datasets, name));
    }
    return snapshot;
  }

  function modelSnapshotToDatasets(snapshot) {
    if (!isObject(snapshot) || snapshot.schema_version !== "1.0" || !Number.isInteger(snapshot.model_id) || snapshot.model_id <= 0 || typeof snapshot.model_name !== "string" || !snapshot.model_name.trim() || !Number.isInteger(snapshot.model_revision) || snapshot.model_revision <= 0) {
      throw new Error("Proposed Model Snapshot identity is invalid.");
    }
    const datasets = {};
    for (const name of MODEL_DATASETS) {
      const [section, field] = MODEL_AGGREGATE_FIELDS[name];
      const value = snapshot?.[section]?.[field];
      if (name === "model_details") {
        if (!isObject(value)) throw new Error("Proposed Model Snapshot has invalid model details.");
        datasets[name] = [clone(value)];
      } else {
        if (!Array.isArray(value)) throw new Error(`Proposed Model Snapshot has invalid ${name} records.`);
        datasets[name] = clone(value);
      }
    }
    return datasets;
  }

  function overlayDataset(snapshotRows, pendingRows, schema) {
    if (!Array.isArray(snapshotRows) || !Array.isArray(pendingRows)) throw new Error("Model dataset overlay requires record arrays.");
    const columns = canonicalColumns(schema);
    const next = clone(snapshotRows);
    const indexes = new Map(next.map((record, index) => [keyFor(record, columns, schema), index]));
    for (const record of pendingRows) {
      const key = keyFor(record, columns, schema);
      const index = indexes.get(key);
      if (index === undefined) {
        indexes.set(key, next.length);
        next.push(clone(record));
      } else {
        next[index] = clone(record);
      }
    }
    return next;
  }

  function modelStageDocument(manifest, localState, pendingDatasets) {
    if (profileForManifest(manifest).kind !== "model" || localState?.model?.model_id !== manifest.model_id) {
      throw new Error("Local Model Change Set identity does not match the Snapshot.");
    }
    const serverId = localState.server_change_set?.model_change_set_id;
    const draftRevision = localState.server_change_set?.draft_revision;
    const bound = serverId !== null && serverId !== undefined;
    if (bound !== (draftRevision !== null && draftRevision !== undefined)) {
      throw new Error("Model Change Set ID and draft revision must be bound together.");
    }
    if (bound && (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(serverId) || !Number.isInteger(draftRevision) || draftRevision <= 0)) {
      throw new Error("Bound Model Change Set identity or draft revision is invalid.");
    }
    const changes = [];
    const sections = {};
    let recordTotal = 0;
    for (const dataset of MODEL_DATASETS) {
      const hasDataset = pendingDatasets instanceof Map
        ? pendingDatasets.has(dataset)
        : Object.prototype.hasOwnProperty.call(pendingDatasets || {}, dataset);
      if (!hasDataset) continue;
      const records = datasetRows(pendingDatasets, dataset);
      if (records.length > MAX_MODEL_DATASET_RECORDS) throw new Error(`${dataset} exceeds ${MAX_MODEL_DATASET_RECORDS.toLocaleString("en-US")} pending records.`);
      recordTotal += records.length;
      changes.push({ dataset, records: clone(records) });
      const section = MODEL_AGGREGATE_FIELDS[dataset][0];
      sections[section] ||= {};
      sections[section][dataset] = records;
    }
    if (!changes.length) throw new Error("A Model Stage payload requires at least one changed dataset.");
    if (recordTotal > MAX_MODEL_TOTAL_RECORDS) throw new Error(`Model Stage payload exceeds ${MAX_MODEL_TOTAL_RECORDS.toLocaleString("en-US")} total records.`);
    for (const [section, documentValue] of Object.entries(sections)) {
      const bytes = new TextEncoder().encode(JSON.stringify(documentValue)).byteLength;
      if (bytes > MAX_MODEL_SECTION_BYTES) throw new Error(`${section} Model Change Set section exceeds 16 MiB.`);
    }
    return {
      schema_version: "1.0",
      model_id: manifest.model_id,
      model_change_set_id: serverId ?? null,
      expected_draft_revision: draftRevision ?? null,
      changes
    };
  }

  function serializeJsonDocument(value) {
    const content = JSON.stringify(value, null, 2) + "\n";
    return { content, bytes: new TextEncoder().encode(content).byteLength };
  }

  root.GdsWorkbenchLogic = Object.freeze({
    ELIGIBLE_DATASETS: METADATA_DATASETS,
    METADATA_DATASETS,
    METADATA_SNAPSHOT_DATASETS,
    MODEL_DATASETS,
    PROFILES,
    MAX_DATASET_RECORDS: MAX_METADATA_DATASET_RECORDS,
    MAX_METADATA_DATASET_RECORDS,
    MAX_MODEL_DATASET_RECORDS,
    MAX_MODEL_TOTAL_RECORDS,
    MAX_DATASET_BYTES,
    MAX_MODEL_SECTION_BYTES,
    safePathParts,
    parseJson,
    parseRows,
    profileForManifest,
    schemaKind,
    normalizeKeyValue,
    canonicalColumns,
    validateSchema,
    validateRecord,
    validateDataset,
    serializeDataset,
    mergeRecord,
    mergeRecords,
    removeRecord,
    createLocalState,
    classifyRecord,
    diffRecord,
    modelSnapshotFromDatasets,
    modelSnapshotToDatasets,
    overlayDataset,
    modelStageDocument,
    serializeJsonDocument,
    clone,
    isObject
  });
})(typeof globalThis === "undefined" ? window : globalThis);
