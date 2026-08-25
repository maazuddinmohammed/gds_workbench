(function (root, factory) {
  "use strict";
  let common = root.GDSCommonValidation;
  let modelValidation = root.GDSModelValidation;
  let core = root.GDSCore;
  if (typeof module === "object" && module.exports) {
    common = require("./validation/common.js");
    modelValidation = require("./validation/model.js");
    core = require("./core.js");
  }
  const api = factory(common, modelValidation, core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSModel = api;
})(typeof globalThis === "object" ? globalThis : this, function (common, modelValidation, core) {
  "use strict";

  const MAPPING_DATASETS = new Set(["mapping_object", "mapping_attribute"]);
  const TARGET_FIELDS = [
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
    "source_system_code",
  ];

  function reviewGroups(definition, records) {
    if (!MAPPING_DATASETS.has(definition?.name) || !Array.isArray(records)) return [];
    const groups = new Map();
    for (const record of records) {
      const values = TARGET_FIELDS.map((field) => record[field] ?? null);
      const normalized = values.map((value, index) =>
        core.normalize("model", TARGET_FIELDS[index], value),
      );
      const key = core.stableStringify(normalized);
      if (!groups.has(key)) {
        groups.set(key, {
          label: `${values[1]} · ${values[3]}.${values[4]} · from ${values[5]}`,
          records: [],
        });
      }
      groups.get(key).records.push(record);
    }
    return [...groups.entries()]
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([, group]) => group);
  }

  function validate(loaded) {
    const effective = new Map();
    for (const [name, value] of loaded) {
      effective.set(name, { records: value.effective, pending: value.pending });
    }
    return [
      ...common.validateLoaded("model", loaded),
      ...modelValidation.validateGraph(effective),
    ];
  }

  return { label: "Model", reviewGroups, validate };
});
