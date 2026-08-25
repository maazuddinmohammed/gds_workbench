(function (root, factory) {
  "use strict";
  let core = root.GDSCore;
  if (typeof module === "object" && module.exports) core = require("../core.js");
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSMetadataValidation = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  function validateReferences(datasets) {
    const byType = new Map();
    for (const value of datasets.values()) {
      byType.set(value.definition.record_type || value.definition.name, value);
    }
    const issues = [];
    for (const value of datasets.values()) {
      const references = Array.isArray(value.schema["x-gds-references"])
        ? value.schema["x-gds-references"]
        : [];
      value.records.forEach((record, recordIndex) => {
        if (core.active(record) === false) return;
        for (const reference of references) {
          const target = byType.get(reference.target_record_type);
          if (!target) {
            issues.push({
              code: "invalid_reference_contract",
              dataset: value.definition.name,
              record: recordIndex + 1,
            });
            continue;
          }
          const values = reference.columns.map((field) => record[field]);
          const nulls = values.filter((item) => item === null || item === undefined).length;
          if (nulls === values.length && reference.nullable === true) continue;
          if (nulls > 0) {
            issues.push({
              code: "partial_null_reference",
              dataset: value.definition.name,
              record: recordIndex + 1,
            });
            continue;
          }
          const wanted = core.stableStringify(
            values.map((item, index) =>
              core.normalize("metadata", reference.target_columns[index], item),
            ),
          );
          const found = target.records.some(
            (candidate) =>
              core.active(candidate) !== false &&
              core.stableStringify(
                reference.target_columns.map((field) =>
                  core.normalize("metadata", field, candidate[field]),
                ),
              ) === wanted,
          );
          if (!found) {
            issues.push({
              code: "broken_reference",
              dataset: value.definition.name,
              record: recordIndex + 1,
              target: reference.target_record_type,
            });
          }
        }
      });
    }
    return issues;
  }

  function validateUniqueConstraints(datasets) {
    const groups = new Map();
    for (const value of datasets.values()) {
      const type = value.definition.record_type || value.definition.name;
      if (!groups.has(type)) groups.set(type, []);
      groups.get(type).push(value);
    }
    const issues = [];
    for (const values of groups.values()) {
      const constraints = new Map();
      for (const value of values) {
        for (const constraint of Array.isArray(value.schema["x-gds-unique-constraints"])
          ? value.schema["x-gds-unique-constraints"]
          : []) {
          if (Array.isArray(constraint) && constraint.every((field) => typeof field === "string")) {
            constraints.set(core.stableStringify(constraint), constraint);
          }
        }
      }
      for (const constraint of constraints.values()) {
        const seen = new Map();
        for (const value of values) {
          value.records.forEach((record, index) => {
            const key = core.stableStringify(
              constraint.map((field) => core.normalize("metadata", field, record[field])),
            );
            const firstDataset = seen.get(key);
            if (firstDataset && firstDataset !== value.definition.name) {
              issues.push({
                code: "duplicate_unique_constraint",
                dataset: value.definition.name,
                record: index + 1,
                message: `Effective zone datasets duplicate (${constraint.join(", ")}).`,
              });
            } else if (!firstDataset) {
              seen.set(key, value.definition.name);
            }
          });
        }
      }
    }
    return issues;
  }

  return { validateReferences, validateUniqueConstraints };
});
