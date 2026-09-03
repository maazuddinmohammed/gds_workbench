(function (root, factory) {
  "use strict";
  let core = root.GDSCore;
  if (typeof module === "object" && module.exports) core = require("../core.js");
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSCommonValidation = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  function same(left, right) {
    return core.stableStringify(left) === core.stableStringify(right);
  }

  function validDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return false;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1];
  }

  function validTime(value) {
    const match = /^(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|([+-])(\d{2}):(\d{2}))?$/.exec(
      value,
    );
    if (!match) return false;
    return (
      Number(match[1]) <= 23 &&
      Number(match[2]) <= 59 &&
      (match[3] === undefined || Number(match[3]) <= 59) &&
      (match[4] === undefined || (Number(match[5]) <= 23 && Number(match[6]) <= 59))
    );
  }

  function validFormat(value, format) {
    if (format === "date") return validDate(value);
    if (format === "date-time") {
      const split = value.search(/[Tt ]/);
      return split > 0 && validDate(value.slice(0, split)) && validTime(value.slice(split + 1));
    }
    if (format === "time") return validTime(value);
    if (format === "uuid") {
      return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
        value,
      );
    }
    return true;
  }

  function utf8Bytes(value) {
    if (typeof TextEncoder === "function") return new TextEncoder().encode(value).length;
    if (typeof Buffer === "function") return Buffer.byteLength(value, "utf8");
    return unescape(encodeURIComponent(value)).length;
  }

  function jsonBytes(value) {
    return utf8Bytes(JSON.stringify(value));
  }

  function normalized(value) {
    return core.normalize("model", "value", value);
  }

  function sameNormalized(left, right) {
    return core.stableStringify(left.map(normalized)) === core.stableStringify(right.map(normalized));
  }

  function uniqueNormalized(values) {
    const keys = values.map((value) => core.stableStringify(normalized(value)));
    return new Set(keys).size === keys.length;
  }

  function sourceKey(source) {
    if (source?.support_source_type === "assertion") {
      return ["assertion", normalized(source.assertion_record?.modeling_assertion_record_key)];
    }
    const physical = source?.source_object || source?.source_attribute;
    if (!physical) return [source?.support_source_type, null];
    const fields = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"];
    if (source.support_source_type === "attribute") fields.push("attribute_name");
    return [source.support_source_type, ...fields.map((field) => normalized(physical[field]))];
  }

  function uniqueSources(values) {
    const keys = values.map((value) => core.stableStringify(sourceKey(value)));
    return new Set(keys).size === keys.length;
  }

  const FORBIDDEN_ASSERTION_KEYS = new Set([
    "binary_content", "connection_string", "content", "credentials", "file_content",
    "payload", "physical_rows", "prompt", "raw", "raw_content", "raw_physical_rows", "rows",
    "raw_prompt", "raw_rows", "secret", "token", "tool_output", "workbook_content",
    "worksheet_content",
  ]);

  const SUPPORTED_RECORD_RULES = new Set([
    "tenant_gds_connection_key",
    "ingestion_object_endpoints",
    "ingestion_attribute_endpoints",
    "copy_record_limit",
    "model_details_policy",
    "profiling_profile",
    "analysis_result",
    "modeling_assertion_document",
    "modeling_assertion_record",
    "conceptual_object",
    "conceptual_relationship",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "mapping_object",
    "mapping_attribute",
    "generated_code",
    "validation_group",
    "validation_check",
  ]);

  function assertionJsonIssues(value, maximumBytes, location) {
    const issues = [];
    if (jsonBytes(value) > maximumBytes) issues.push(`${location}: JSON value is too large`);
    let nodes = 0;
    const pending = [[value, 0]];
    while (pending.length) {
      const [item, depth] = pending.pop();
      nodes += 1;
      if (nodes > 4096 || depth > 12) {
        issues.push(`${location}: JSON value is too complex`);
        break;
      }
      if (typeof item === "string" && [...item].length > 32768) {
        issues.push(`${location}: JSON value contains an oversized string`);
      } else if (Array.isArray(item)) {
        item.forEach((child) => pending.push([child, depth + 1]));
      } else if (item && typeof item === "object") {
        for (const [key, child] of Object.entries(item)) {
          const normalizedKey = key.trim().toLowerCase().replaceAll("-", "_");
          const compact = normalizedKey.replaceAll("_", "");
          if (
            FORBIDDEN_ASSERTION_KEYS.has(normalizedKey) || compact.includes("secret") ||
            compact.includes("credential") || compact.includes("connectionstring") ||
            compact.includes("rawprompt") || compact.includes("rawrows") ||
            compact.includes("tooloutput") || compact.includes("filecontent") ||
            compact.includes("workbookcontent") || compact.includes("worksheetcontent")
          ) {
            issues.push(`${location}.${key}: prohibited raw content`);
          }
          pending.push([child, depth + 1]);
        }
      }
    }
    return issues;
  }

  function validationLiteralMatches(resultType, value) {
    if (resultType === "boolean") return typeof value === "boolean";
    if (resultType === "integer") return Number.isInteger(value);
    if (resultType === "decimal") return typeof value === "number" && Number.isFinite(value);
    if (resultType === "text") return typeof value === "string";
    const basicDate = (item) => /^\d{8}$/.test(item) &&
      validDate(`${item.slice(0, 4)}-${item.slice(4, 6)}-${item.slice(6, 8)}`);
    if (resultType === "date") {
      return typeof value === "string" && (validDate(value) || basicDate(value));
    }
    if (resultType === "timestamp") {
      if (typeof value !== "string") return false;
      if (validDate(value) || basicDate(value)) return true;
      const split = value.search(/[Tt ]/);
      return split > 0 && validDate(value.slice(0, split)) && validTime(value.slice(split + 1));
    }
    return false;
  }

  function validateRecordRule(value, rule, location) {
    const issues = [];
    const add = (message) => issues.push(`${location}: ${message}`);
    if (!SUPPORTED_RECORD_RULES.has(rule)) {
      add(`unsupported record validation rule ${rule}`);
      return issues;
    }
    const endpoint = (prefix, attribute = false) => [
      `${prefix}_tenant_code`, `${prefix}_system_code`, `${prefix}_connection_code`,
      `${prefix}_object_schema`, `${prefix}_object_name`,
      ...(attribute ? [`${prefix}_attribute_name`] : []),
    ].map((field) => value[field]);
    const validateRelationship = (layer) => {
      if (sameNormalized(
        [value[`from_${layer}_entity_name`], value[`from_${layer}_attribute_name`]],
        [value[`to_${layer}_entity_name`], value[`to_${layer}_attribute_name`]],
      )) add(`${layer} Relationship endpoints must be different`);
    };

    if (rule === "tenant_gds_connection_key") {
      const fields = ["gds_connection_tenant_code", "gds_connection_system_code", "gds_connection_code"];
      const present = fields.map((field) => value[field] !== null);
      if (present.some(Boolean) && !present.every(Boolean)) add("GDS Connection key must be entirely present or absent");
    } else if (rule === "ingestion_object_endpoints") {
      if (sameNormalized(endpoint("source"), endpoint("target"))) add("Ingestion Object Mapping endpoints must be different");
    } else if (rule === "ingestion_attribute_endpoints") {
      if (sameNormalized(endpoint("source", true), endpoint("target", true))) add("Ingestion Attribute Mapping endpoints must be different");
    } else if (rule === "copy_record_limit") {
      if (value.copy_source_record_limit !== null) {
        try {
          const limit = BigInt(value.copy_source_record_limit);
          if (limit < -9223372036854775808n || limit > 9223372036854775807n) add("Copy source record limit must fit PostgreSQL BIGINT");
        } catch (_error) { add("Copy source record limit must fit PostgreSQL BIGINT"); }
      }
    } else if (rule === "model_details_policy") {
      for (const field of ["silver_model_naming_instructions", "gold_model_naming_instructions"]) {
        if (value[field] !== null && utf8Bytes(value[field]) > 32768) add(`${field} exceeds 32,768 UTF-8 bytes`);
      }
      for (const field of ["silver_model_audit_columns_template", "gold_model_technical_columns_template", "gold_model_audit_columns_template"]) {
        if (value[field] !== null && jsonBytes(value[field]) > 262144) add(`${field} exceeds 262,144 JSON bytes`);
      }
    } else if (rule === "profiling_profile") {
      if (value.non_null_count + value.null_count !== value.row_count) add("Profile non-null and null counts must equal row count");
      if (value.blank_count !== null && value.blank_count > value.non_null_count) add("Profile blank count cannot exceed non-null count");
      if (value.distinct_count !== null && value.distinct_count > value.non_null_count) add("Profile distinct count cannot exceed non-null count");
      if (value.min_data_length !== null && value.max_data_length !== null && value.min_data_length > value.max_data_length) add("Profile minimum length cannot exceed maximum length");
      const decimal = (raw, wholeDigits, decimalPlaces) => {
        if (typeof raw !== "string" && typeof raw !== "number") return null;
        if (typeof raw === "number" && !Number.isFinite(raw)) return null;
        const text = String(raw);
        const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(text);
        if (!match || (match[3] || "").length > decimalPlaces) return null;
        const significantWhole = match[2].replace(/^0+/, "") || "0";
        if (significantWhole.length > wholeDigits) return null;
        const numeric = Number(text);
        return Number.isFinite(numeric) ? numeric : null;
      };
      if (value.avg_data_length !== null) {
        const number = decimal(value.avg_data_length, 14, 6);
        if (number === null || number < 0) add("Profile average length is invalid");
      }
      for (const field of ["percent_populated", "percent_duplicates", "percent_null", "percent_blank", "percent_distinct"]) {
        if (value[field] === null) continue;
        const number = decimal(value[field], 3, 4);
        if (number === null || number < 0 || number > 100) add(`${field} must be between 0 and 100 with at most four decimal places`);
      }
    } else if (rule === "analysis_result") {
      const fields = ["validation_policy_version", "validation_result", "validation_source_non_null_count", "validation_source_distinct_count", "validation_target_non_null_count", "validation_target_distinct_count", "validation_source_missing_target_count", "validation_unused_target_count", "validation_duplicate_target_key_count"];
      const present = fields.map((field) => value[field] !== null);
      if (present.some(Boolean) && !present.every(Boolean)) add("Analysis validation fields must all be present or all be absent");
      if (sameNormalized(endpoint("from", true), endpoint("to", true))) add("Analysis endpoints must be different");
    } else if (rule === "modeling_assertion_document") {
      issues.push(...assertionJsonIssues(value.modeling_assertion_document_metadata, 65536, `${location}.modeling_assertion_document_metadata`));
    } else if (rule === "modeling_assertion_record") {
      if ([...value.modeling_assertion_text].length > 262144) add("Assertion Record text is too large");
      issues.push(...assertionJsonIssues(value.modeling_assertion_details, 262144, `${location}.modeling_assertion_details`));
      if (value.modeling_assertion_source_location !== null) issues.push(...assertionJsonIssues(value.modeling_assertion_source_location, 65536, `${location}.modeling_assertion_source_location`));
      if (!uniqueNormalized(value.modeling_assertion_applicable_layers)) add("Assertion applicable layers must be unique");
    } else if (rule === "conceptual_object") {
      if (!uniqueNormalized(value.conceptual_object_aliases)) add("Conceptual Object aliases must be unique");
      if (!uniqueSources(value.supports)) add("Conceptual Object supports must be unique");
    } else if (rule === "conceptual_relationship") {
      if (sameNormalized([value.from_conceptual_object_name], [value.to_conceptual_object_name])) add("Conceptual Relationship endpoints must be different");
      if (!uniqueSources(value.supports)) add("Conceptual Relationship supports must be unique");
    } else if (rule === "logical_entity") {
      if (!uniqueNormalized(value.submodels.map((item) => item.submodel_name))) add("Logical Entity Submodel memberships must be unique");
      if (!uniqueSources(value.sources)) add("Logical Entity sources must be unique");
    } else if (rule === "logical_attribute") {
      if (value.logical_attribute_is_natural_key && value.logical_attribute_is_surrogate_key) add("A Logical Attribute cannot be both natural and surrogate key");
      if ((value.logical_attribute_is_primary_key || value.logical_attribute_is_natural_key || value.logical_attribute_is_surrogate_key) && value.logical_attribute_is_nullable) add("A Logical key Attribute cannot be nullable");
      if (!uniqueSources(value.sources)) add("Logical Attribute sources must be unique");
    } else if (rule === "logical_relationship") {
      validateRelationship("logical");
    } else if (rule === "dimensional_entity") {
      if ((value.dimensional_entity_type === "fact") !== (value.dimensional_fact_type !== null)) add("Dimensional fact type is required only for facts");
      if (["fact", "bridge"].includes(value.dimensional_entity_type) && value.dimensional_entity_grain_definition === null) add("Fact and bridge Entities require a grain definition");
      if (!uniqueNormalized(value.submodels.map((item) => item.submodel_name))) add("Dimensional Entity Submodel memberships must be unique");
      if (!uniqueSources(value.sources)) add("Dimensional Entity sources must be unique");
    } else if (rule === "dimensional_attribute") {
      if (value.dimensional_attribute_key_role !== "none" && !["key", "technical"].includes(value.dimensional_attribute_role)) add("A Dimensional key role requires a key or technical Attribute");
      const measure = [value.dimensional_attribute_additivity, value.dimensional_attribute_default_aggregation, value.dimensional_attribute_aggregation_basis];
      if (value.dimensional_attribute_role === "measure") {
        if (measure[0] === null || measure[1] === null) add("A measure requires additivity and default aggregation");
        if (measure[0] !== null && measure[0] !== "additive" && measure[2] === null) add("A non-additive measure requires an aggregation basis");
      } else if (measure.some((item) => item !== null)) add("Measure policy fields are valid only for measures");
      if (value.dimensional_attribute_is_audit_column !== (value.dimensional_attribute_role === "audit")) add("Dimensional audit flag and role must agree");
      if (!uniqueSources(value.sources)) add("Dimensional Attribute sources must be unique");
    } else if (rule === "dimensional_relationship") {
      validateRelationship("dimensional");
    } else if (rule === "mapping_object") {
      if (value.mapping_transformation_document !== null && jsonBytes(value.mapping_transformation_document) > 524288) add("Mapping transformation document exceeds 524,288 bytes");
    } else if (rule === "mapping_attribute") {
      if (value.attribute_mapping_transformation_document !== null && jsonBytes(value.attribute_mapping_transformation_document) > 65536) add("Attribute Mapping document exceeds 65,536 bytes");
    } else if (rule === "generated_code") {
      if ([...value.generated_code_content].some((character) => character.codePointAt(0) < 32 && !["\t", "\n", "\r"].includes(character))) add("Generated Code contains an unsupported control character");
      if (value.artifact_name.trim() !== value.artifact_name || value.artifact_name.includes("/") || value.artifact_name.includes("\\")) add("Artifact name must be a file name, not a path");
      if ([".", ".."].includes(value.artifact_name)) add("Artifact name is invalid");
    } else if (rule === "validation_group") {
      if (value.validation_group_description !== null && utf8Bytes(value.validation_group_description) > 16384) add("Validation Group description is too large");
    } else if (rule === "validation_check") {
      if (value.validation_check_description !== null && utf8Bytes(value.validation_check_description) > 16384) add("Validation Check description is too large");
      for (const field of ["validation_query_sql", "validation_comparison_query_sql"]) if (value[field] !== null && utf8Bytes(value[field]) > 100000) add(`${field} exceeds 100,000 bytes`);
      if (value.validation_comparison_value !== null && jsonBytes(value.validation_comparison_value) > 65536) add("Validation comparison value is too large");
      const operator = value.validation_comparison_operator;
      const resultType = value.validation_result_data_type;
      const valueType = value.validation_comparison_value_type;
      const comparison = value.validation_comparison_value;
      const query = value.validation_comparison_query_sql;
      let shape = false;
      if (operator === "executes_successfully") shape = resultType === null && valueType === "none" && comparison === null && query === null;
      else if (["is_null", "is_not_null"].includes(operator)) shape = resultType !== null && valueType === "none" && comparison === null && query === null;
      else if (["is_true", "is_false"].includes(operator)) shape = resultType === "boolean" && valueType === "none" && comparison === null && query === null;
      else if (["equal", "not_equal"].includes(operator)) shape = resultType !== null && ((valueType === "literal" && comparison !== null && query === null) || (valueType === "query" && comparison === null && query !== null));
      else if (["greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal"].includes(operator)) shape = ["integer", "decimal", "date", "timestamp"].includes(resultType) && ((valueType === "literal" && comparison !== null && query === null) || (valueType === "query" && comparison === null && query !== null));
      else shape = resultType !== null && valueType === "literal_list" && Array.isArray(comparison) && comparison.length >= 1 && comparison.length <= 10000 && query === null;
      if (!shape) add("Validation assertion shape is invalid");
      const values = Array.isArray(comparison) ? comparison : [comparison];
      if (["literal", "literal_list"].includes(valueType) && !values.every((item) => validationLiteralMatches(resultType, item))) add("Validation comparison value does not match its result type");
    }
    return issues;
  }

  function validateRecordContract(value, schema, location) {
    const contract = schema["x-gds-record-validation"];
    if (contract === undefined) return [];
    if (!contract || contract.version !== "1.0" || !Array.isArray(contract.rules)) {
      return [`${location}: record validation contract is invalid`];
    }
    return contract.rules.flatMap((rule) => validateRecordRule(value, rule, location));
  }

  function validateSchema(value, schema, rootSchema, location, seen) {
    rootSchema = rootSchema || schema;
    location = location || "$";
    seen = seen || new Set();
    if (!schema || typeof schema !== "object") return [`${location}: schema is invalid`];
    if (typeof schema.$ref === "string") {
      if (!schema.$ref.startsWith("#/$defs/")) return [`${location}: unsupported schema reference`];
      const target = rootSchema.$defs?.[schema.$ref.slice(8)];
      if (!target || seen.has(target)) return [`${location}: unresolved schema reference`];
      return validateSchema(value, target, rootSchema, location, new Set([...seen, target]));
    }
    if (Array.isArray(schema.anyOf)) {
      if (
        !schema.anyOf.some(
          (option) => validateSchema(value, option, rootSchema, location).length === 0,
        )
      ) {
        return [`${location}: value does not match any allowed schema`];
      }
    }
    if (Array.isArray(schema.oneOf)) {
      const matches = schema.oneOf.filter(
        (option) => validateSchema(value, option, rootSchema, location).length === 0,
      ).length;
      if (matches !== 1) {
        return [`${location}: value must match exactly one allowed schema`];
      }
    }
    const issues = [];
    if (Array.isArray(schema.allOf)) {
      for (const option of schema.allOf) {
        issues.push(...validateSchema(value, option, rootSchema, location, seen));
      }
    }
    if (schema.if && typeof schema.if === "object" && !Array.isArray(schema.if)) {
      const conditionMatches = validateSchema(value, schema.if, rootSchema, location).length === 0;
      const branch = conditionMatches ? schema.then : schema.else;
      if (branch && typeof branch === "object" && !Array.isArray(branch)) {
        issues.push(...validateSchema(value, branch, rootSchema, location, seen));
      }
    }
    if (Object.prototype.hasOwnProperty.call(schema, "const") && !same(value, schema.const)) {
      return [`${location}: fixed value is required`];
    }
    if (Array.isArray(schema.enum) && !schema.enum.some((item) => same(item, value))) {
      return [`${location}: value is not allowed`];
    }

    const types = Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];
    const actual =
      value === null
        ? "null"
        : Array.isArray(value)
          ? "array"
          : typeof value === "number" && Number.isInteger(value)
            ? "integer"
            : typeof value;
    if (types.length && !types.includes(actual) && !(actual === "integer" && types.includes("number"))) {
      return [`${location}: expected ${types.join(" or ")}`];
    }

    if (typeof value === "string") {
      const characterLength = [...value].length;
      if (Number.isInteger(schema.minLength) && characterLength < schema.minLength) {
        issues.push(`${location}: shorter than minLength`);
      }
      if (Number.isInteger(schema.maxLength) && characterLength > schema.maxLength) {
        issues.push(`${location}: longer than maxLength`);
      }
      if (typeof schema.pattern === "string") {
        try {
          if (!new RegExp(schema.pattern, "u").test(value)) issues.push(`${location}: fails pattern`);
        } catch (_error) {
          issues.push(`${location}: schema pattern is invalid`);
        }
      }
      if (typeof schema.format === "string" && !validFormat(value, schema.format)) {
        issues.push(`${location}: fails ${schema.format} format`);
      }
    }
    if (typeof value === "number") {
      if (!Number.isFinite(value)) {
        issues.push(`${location}: number must be finite`);
      } else {
        if (typeof schema.minimum === "number" && value < schema.minimum) {
          issues.push(`${location}: below minimum`);
        }
        if (typeof schema.maximum === "number" && value > schema.maximum) {
          issues.push(`${location}: above maximum`);
        }
        if (typeof schema.exclusiveMinimum === "number" && value <= schema.exclusiveMinimum) {
          issues.push(`${location}: not above exclusiveMinimum`);
        }
        if (typeof schema.exclusiveMaximum === "number" && value >= schema.exclusiveMaximum) {
          issues.push(`${location}: not below exclusiveMaximum`);
        }
      }
    }
    if (Array.isArray(value)) {
      if (Number.isInteger(schema.minItems) && value.length < schema.minItems) {
        issues.push(`${location}: fewer than minItems`);
      }
      if (Number.isInteger(schema.maxItems) && value.length > schema.maxItems) {
        issues.push(`${location}: more than maxItems`);
      }
      if (schema.items) {
        value.forEach((item, index) => {
          issues.push(...validateSchema(item, schema.items, rootSchema, `${location}[${index}]`));
        });
      }
    }
    if (value && !Array.isArray(value) && typeof value === "object") {
      const properties = schema.properties || {};
      for (const required of schema.required || []) {
        if (!Object.prototype.hasOwnProperty.call(value, required)) {
          issues.push(`${location}.${required}: required field is missing`);
        }
      }
      if (schema.additionalProperties === false) {
        for (const field of Object.keys(value)) {
          if (!Object.prototype.hasOwnProperty.call(properties, field)) {
            issues.push(`${location}.${field}: additional property is forbidden`);
          }
        }
      }
      for (const [field, child] of Object.entries(value)) {
        if (Object.prototype.hasOwnProperty.call(properties, field)) {
          issues.push(
            ...validateSchema(child, properties[field], rootSchema, `${location}.${field}`),
          );
        }
      }
      // Pydantic runs these model-level rules only after field/schema validation.
      // Match that order and avoid evaluating incomplete records.
      if (!issues.length) issues.push(...validateRecordContract(value, schema, location));
    }
    return issues;
  }

  function validateLoaded(area, loaded) {
    const issues = [];
    for (const [datasetName, value] of loaded) {
      if (value.overlayError) {
        issues.push({
          code: "effective_overlay",
          dataset: datasetName,
          message: value.overlayError,
        });
      }
      if (value.schema["x-gds-change-set-eligible"] !== true && value.pending.length) {
        issues.push({
          code: "dataset_not_change_set_eligible",
          dataset: datasetName,
          message: "Dataset is not Change Set eligible.",
        });
      }
      const seen = new Set();
      const baseline = new Map();
      for (const record of value.baseline || []) {
        try {
          baseline.set(
            core.stableStringify(core.key(area, value.definition, record)),
            record,
          );
        } catch (_error) {
          // Canonical-key issues are reported on pending records below.
        }
      }
      value.pending.forEach((record, index) => {
        for (const message of validateSchema(record, value.schema)) {
          issues.push({ code: "schema", dataset: datasetName, record: index + 1, message });
        }
        if (!record || Array.isArray(record) || typeof record !== "object") return;
        try {
          const key = core.stableStringify(core.key(area, value.definition, record));
          if (seen.has(key)) {
            issues.push({
              code: "duplicate_canonical_key",
              dataset: datasetName,
              record: index + 1,
              message: "Pending record duplicates a canonical key.",
            });
          }
          seen.add(key);
          const original = baseline.get(key);
          const locked = original && Object.entries(original).some(
            ([field, fieldValue]) =>
              fieldValue === true && (field === "is_locked" || field.endsWith("_is_locked")),
          );
          if (locked && core.stableStringify(original) !== core.stableStringify(record)) {
            issues.push({
              code: "locked_record",
              dataset: datasetName,
              record: index + 1,
              message: "Locked records cannot be changed locally.",
            });
          }
        } catch (error) {
          issues.push({
            code: "canonical_key",
            dataset: datasetName,
            record: index + 1,
            message: error.message,
          });
        }
      });
      const constraints = value.schema["x-gds-unique-constraints"];
      if (constraints !== undefined && !Array.isArray(constraints)) {
        issues.push({
          code: "invalid_unique_constraint_contract",
          dataset: datasetName,
          message: "Unique constraint metadata must be an array.",
        });
      }
      for (const constraint of Array.isArray(constraints) ? constraints : []) {
        if (
          !Array.isArray(constraint) ||
          !constraint.length ||
          constraint.some((field) => typeof field !== "string" || !field)
        ) {
          issues.push({
            code: "invalid_unique_constraint_contract",
            dataset: datasetName,
            message: "Unique constraint fields are invalid.",
          });
          continue;
        }
        const unique = new Set();
        (value.effective || []).forEach((record, index) => {
          if (!record || Array.isArray(record) || typeof record !== "object") return;
          const key = core.stableStringify(
            constraint.map((field) => core.normalize(area, field, record[field])),
          );
          if (unique.has(key)) {
            issues.push({
              code: "duplicate_unique_constraint",
              dataset: datasetName,
              record: index + 1,
              message: `Effective records duplicate (${constraint.join(", ")}).`,
            });
          }
          unique.add(key);
        });
      }
    }
    return issues;
  }

  return {
    supportedRecordRules: [...SUPPORTED_RECORD_RULES].sort(),
    validateLoaded,
    validateSchema,
  };
});
