(function (root, factory) {
  "use strict";
  let core = root.GDSCore;
  if (typeof module === "object" && module.exports) core = require("../core.js");
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSModelValidation = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  function recordType(value) {
    return value.schema?.["x-gds-record-type"] ||
      value.definition?.record_type ||
      value.definition?.name;
  }

  function active(record) {
    return core.active(record) !== false;
  }

  function candidateGroups(model, metadata) {
    const groups = new Map();
    function add(area, datasets) {
      if (!(datasets instanceof Map)) return;
      for (const value of datasets.values()) {
        const type = recordType(value);
        if (typeof type !== "string" || !type) continue;
        if (!groups.has(type)) groups.set(type, []);
        const source = value.records || value.effective || value.baseline || [];
        groups.get(type).push({ area, records: source });
      }
    }
    add("model", model);
    add("metadata", metadata);
    return groups;
  }

  function validateReferences(model, metadata) {
    const targets = candidateGroups(model, metadata);
    const issues = [];
    for (const [datasetName, value] of model) {
      const references = value.schema?.["x-gds-references"];
      if (references === undefined) continue;
      if (!Array.isArray(references)) {
        issues.push({
          code: "invalid_reference_contract",
          dataset: datasetName,
          message: "Reference metadata must be an array.",
        });
        continue;
      }
      value.records.forEach((record, recordIndex) => {
        if (!active(record)) return;
        for (const reference of references) {
          const columns = reference?.columns;
          const targetColumns = reference?.target_columns;
          const candidates = targets.get(reference?.target_record_type) || [];
          if (
            !Array.isArray(columns) ||
            !columns.length ||
            !Array.isArray(targetColumns) ||
            columns.length !== targetColumns.length ||
            !candidates.length
          ) {
            issues.push({
              code: "invalid_reference_contract",
              dataset: datasetName,
              record: recordIndex + 1,
              target: reference?.target_record_type,
            });
            continue;
          }
          const values = columns.map((field) => record[field]);
          const nullCount = values.filter((item) => item === null || item === undefined).length;
          if (nullCount === values.length && reference.nullable === true) continue;
          if (nullCount > 0) {
            issues.push({
              code: "partial_null_reference",
              dataset: datasetName,
              record: recordIndex + 1,
              target: reference.target_record_type,
            });
            continue;
          }
          const found = candidates.some((candidate) => {
            const wanted = core.stableStringify(
              values.map((item, index) =>
                core.normalize(candidate.area, targetColumns[index], item),
              ),
            );
            return candidate.records.some(
              (target) =>
                active(target) &&
                core.stableStringify(
                  targetColumns.map((field) =>
                    core.normalize(candidate.area, field, target[field]),
                  ),
                ) === wanted,
            );
          });
          if (!found) {
            issues.push({
              code: "broken_reference",
              dataset: datasetName,
              record: recordIndex + 1,
              target: reference.target_record_type,
            });
          }
        }
      });
    }
    return issues;
  }

  function validateGraph(model, metadata = null) {
    return validateReferences(model, metadata);
  }

  return { validateGraph, validateReferences };
});
