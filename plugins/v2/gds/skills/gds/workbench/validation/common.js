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
    return month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1];
  }

  function validTime(value) {
    const match = /^(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/.exec(
      value,
    );
    if (!match) return false;
    return (
      Number(match[1]) <= 23 &&
      Number(match[2]) <= 59 &&
      Number(match[3]) <= 59 &&
      (match[4] === undefined || (Number(match[5]) <= 23 && Number(match[6]) <= 59))
    );
  }

  function validFormat(value, format) {
    if (format === "date") return validDate(value);
    if (format === "date-time") {
      const split = value.indexOf("T");
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
      if (Number.isInteger(schema.minLength) && value.length < schema.minLength) {
        issues.push(`${location}: shorter than minLength`);
      }
      if (Number.isInteger(schema.maxLength) && value.length > schema.maxLength) {
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

  return { validateLoaded, validateSchema };
});
