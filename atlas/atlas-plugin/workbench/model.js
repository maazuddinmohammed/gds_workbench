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

  const GROUP_FIELDS = new Map([
    ["model_object_binding", ["modeled_entity_type", "modeled_entity_name"]],
    ["model_attribute_binding", ["modeled_entity_type", "modeled_entity_name"]],
    [
      "mapping_object",
      ["modeled_entity_type", "modeled_entity_name", "source_system_code"],
    ],
    [
      "mapping_attribute",
      ["modeled_entity_type", "modeled_entity_name", "source_system_code"],
    ],
  ]);

  function entityTypeLabel(value) {
    return String(value ?? "unspecified")
      .split("_")
      .filter(Boolean)
      .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
      .join(" ");
  }

  function reviewGroups(definition, records) {
    const fields = GROUP_FIELDS.get(definition?.name);
    if (!fields || !Array.isArray(records)) return [];
    const groups = new Map();
    for (const record of records) {
      const values = fields.map((field) => record[field] ?? null);
      const normalized = values.map((value, index) =>
        core.normalize("model", fields[index], value),
      );
      const key = core.stableStringify(normalized);
      if (!groups.has(key)) {
        const entity = `${entityTypeLabel(values[0])} ${values[1] ?? "unspecified"}`;
        const suffix = fields.includes("source_system_code")
          ? `source System ${values[2] ?? "unspecified"}`
          : "Model Binding";
        groups.set(key, {
          label: `${entity} · ${suffix}`,
          records: [],
        });
      }
      groups.get(key).records.push(record);
    }
    return [...groups.entries()]
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([, group]) => group);
  }

  function validate(loaded, metadataLoaded = null, context = {}) {
    const effective = new Map();
    for (const [name, value] of loaded) {
      effective.set(name, {
        definition: value.definition,
        schema: value.schema,
        records: value.effective,
        baseline: value.baseline,
        pending: value.pending,
      });
    }
    const metadata = metadataLoaded instanceof Map
      ? new Map(
        [...metadataLoaded].map(([name, value]) => [
          name,
          {
            definition: value.definition,
            schema: value.schema,
            records: value.effective ?? value.baseline ?? value.records ?? [],
          },
        ]),
      )
      : null;
    return [
      ...common.validateLoaded("model", loaded),
      ...modelValidation.validateGraph(effective, metadata, context),
    ];
  }

  return { label: "Model", reviewGroups, validate };
});
