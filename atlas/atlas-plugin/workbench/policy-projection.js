(function (root, factory) {
  "use strict";
  const node = typeof module === "object" && module.exports;
  const api = factory(node ? require("./core.js") : root.GDSCore);
  if (node) module.exports = api;
  root.AtlasPolicyProjection = api;
})(globalThis, function (core) {
  "use strict";
  // Ports of the web backend's deterministic projections so local drafts get the same
  // technical columns the web workflow adds: Logical surrogate + audit block
  // (features/logical/policy.py) and Gold surrogate, Type 2 history and audit block
  // (project_dimensional_gold_policy). Relationship-derived Fact/Bridge foreign keys
  // are not projected here. tests/atlas/test_policy_projection.py runs both sides.
  const DEFAULT_AUDIT = [
    ["SourceSystemID", "BIGINT", "Originating source System identifier."],
    ["IsDataValid", "BOOLEAN", "Framework data validation flag."],
    ["HashKey", "STRING", "Framework change-detection hash."],
    ["IsActive", "BOOLEAN", "Framework active-record flag."],
    ["GDSBatchID", "BIGINT", "Framework batch identifier."],
    ["PipelineRunID", "STRING", "Framework pipeline run identifier."],
    ["CreatedDate", "TIMESTAMP", "Framework record creation time."],
    ["UpdatedDate", "TIMESTAMP", "Framework record update time."],
    ["CreatedBy", "STRING", "Framework record creator."],
    ["UpdatedBy", "STRING", "Framework record updater."],
  ];
  const DEFAULT_TECHNICAL = {
    schema_version: "1.0",
    dimension_surrogate_key: {semantic_name_template: "{entity_name}Key", data_type: "BIGINT", nullable: false,
      definition_template: "Surrogate key for {entity_name}."},
    fact_bridge_foreign_key: {with_role_semantic_name_template: "{role_name}Key",
      without_role_semantic_name_template: "{entity_name}Key", definition_template: "Foreign key to {entity_name}."},
    type_2: {
      effective_from: {semantic_name: "RecordStartTime", data_type: "TIMESTAMP", nullable: false, definition: "Inclusive start of this dimension version."},
      effective_to: {semantic_name: "RecordEndTime", data_type: "TIMESTAMP", nullable: true, definition: "Exclusive end of this dimension version."},
      is_current: {semantic_name: "IsCurrentRecord", data_type: "BOOLEAN", nullable: false, definition: "Whether this is the current dimension version."},
    },
  };
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const norm = (value) => core.normalize("project", "value", value);
  const same = (left, right) => left !== undefined && right !== undefined && core.stableStringify(left) === core.stableStringify(right);
  const compareKeys = (left, right) => {
    for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
      const order = core.compareCodePoints(String(left[index]), String(right[index]));
      if (order) return order;
    }
    return left.length - right.length;
  };

  function effectiveAuditTemplate(template) {
    if (template !== null && template !== undefined) return clone(template);
    return {schema_version: "1.0", columns: DEFAULT_AUDIT.map(([semantic_name, data_type, definition]) =>
      ({semantic_name, data_type, nullable: true, definition}))};
  }

  function effectiveGoldTemplates(technical, audit) {
    const keys = clone(technical ?? DEFAULT_TECHNICAL);
    const columns = effectiveAuditTemplate(audit);
    for (const name of ["dimension_surrogate_key", "fact_bridge_foreign_key", "type_2"]) {
      if (Object.hasOwn(columns, name)) {
        const value = columns[name];
        delete columns[name];
        if (value !== null && value !== undefined) keys[name] = value;
      }
    }
    return [keys, columns];
  }

  function validColumn(column) {
    return column && typeof column === "object" && typeof column.semantic_name === "string" && column.semantic_name.trim() &&
      column.semantic_name.length <= 255 && typeof column.data_type === "string" && column.data_type.trim() && column.data_type.length <= 100 &&
      typeof column.nullable === "boolean" && (column.definition === null || column.definition === undefined ||
      (typeof column.definition === "string" && column.definition.trim() && column.definition.length <= 2000));
  }

  function auditPolicy(template, label) {
    const columns = template?.columns;
    if (!Array.isArray(columns) || columns.length > 32 || !columns.every(validColumn) ||
        new Set(columns.map((column) => norm(column.semantic_name))).size !== columns.length) {
      throw new Error(`The ${label} audit-column template is invalid.`);
    }
    return columns;
  }

  function layerKeys(layer) {
    const schema = `${layer}_entity_schema_name`, entity = `${layer}_entity_name`, attribute = `${layer}_attribute_name`;
    return {
      entity: (record) => [norm(record[schema]), norm(record[entity])],
      attribute: (record) => [norm(record[schema]), norm(record[entity]), norm(record[attribute])],
      text: (key) => core.stableStringify(key),
    };
  }

  function mergedRecords(baseline, changed, key, text) {
    const result = new Map();
    for (const record of [...baseline, ...changed]) result.set(text(key(record)), record);
    return result;
  }

  function changedAttributes(layer, keys, baselineAttributes, candidateAttributes, projected) {
    const byKey = new Map(candidateAttributes.map((record) => [keys.text(keys.attribute(record)), record]));
    for (const record of projected) byKey.set(keys.text(keys.attribute(record)), record);
    const applied = new Map(baselineAttributes.map((record) => [keys.text(keys.attribute(record)), record]));
    return [...byKey.entries()].filter(([text, record]) => !same(applied.get(text), record)).map(([, record]) => record);
  }

  function projectLogical(candidate, baseline, rawTemplate) {
    const columns = auditPolicy(effectiveAuditTemplate(rawTemplate), "Silver");
    const keys = layerKeys("logical");
    const entities = mergedRecords(baseline.entities, candidate.entities, keys.entity, keys.text);
    const attributes = mergedRecords(baseline.attributes, candidate.attributes, keys.attribute, keys.text);
    const appliedEntities = new Set(baseline.entities.map((record) => keys.text(keys.entity(record))));
    const projected = [];
    const ordered = [...entities.values()].sort((left, right) => compareKeys(keys.entity(left), keys.entity(right)));
    for (const entity of ordered) {
      if (entity.logical_entity_is_active !== true) continue;
      const entityKey = keys.entity(entity);
      const ownedBy = () => [...attributes.values()].filter((record) => compareKeys(keys.attribute(record).slice(0, 2), entityKey) === 0);
      let entityAttributes = ownedBy();
      if (!appliedEntities.has(keys.text(entityKey)) || entityAttributes.some((row) =>
        row.logical_attribute_is_surrogate_key && row.logical_attribute_ordinal_position === 1)) {
        const surrogates = entityAttributes.filter((row) => row.logical_attribute_is_surrogate_key);
        if (surrogates.length > 1) throw new Error("A new Logical Entity needs one own surrogate key.");
        let surrogate = surrogates[0];
        if (surrogate) {
          if (surrogate.sources?.length || surrogate.logical_attribute_is_nullable) throw new Error("An own generated surrogate cannot have physical sources.");
        } else {
          const name = `${entity.logical_entity_name}ID`;
          if (attributes.has(keys.text([...entityKey, norm(name)]))) throw new Error("The generated key name conflicts with a business Attribute.");
          surrogate = {
            logical_entity_schema_name: entity.logical_entity_schema_name, logical_entity_name: entity.logical_entity_name,
            logical_attribute_name: name, logical_attribute_definition: `Generated identifier for ${entity.logical_entity_name}.`,
            logical_attribute_data_type: "BIGINT", logical_attribute_is_nullable: false, logical_attribute_is_natural_key: false,
            logical_attribute_is_surrogate_key: true, logical_attribute_ordinal_position: 1, logical_attribute_is_audit_column: false,
            logical_attribute_is_active: true, logical_attribute_is_locked: false, sources: [],
          };
        }
        const surrogateKey = keys.text(keys.attribute(surrogate));
        const rows = [surrogate, ...entityAttributes.filter((row) => keys.text(keys.attribute(row)) !== surrogateKey)
          .sort((left, right) => left.logical_attribute_ordinal_position - right.logical_attribute_ordinal_position ||
            compareKeys(keys.attribute(left), keys.attribute(right)))];
        entityAttributes = rows.map((row, index) => {
          const desired = {...row, logical_attribute_ordinal_position: index + 1};
          attributes.set(keys.text(keys.attribute(desired)), desired);
          projected.push(desired);
          return desired;
        });
      }
      const nextOrdinal = 1 + Math.max(0, ...entityAttributes.filter((record) => !record.logical_attribute_is_audit_column)
        .map((record) => record.logical_attribute_ordinal_position));
      columns.forEach((column, offset) => {
        const key = keys.text([...entityKey, norm(column.semantic_name)]);
        const existing = attributes.get(key);
        if (existing && (!existing.logical_attribute_is_audit_column || norm(existing.logical_attribute_data_type) !== norm(column.data_type) ||
            existing.logical_attribute_is_nullable !== column.nullable || (existing.sources?.length && norm(column.semantic_name) !== "sourcesystemid"))) {
          throw new Error("A configured Logical audit column conflicts with an existing Attribute.");
        }
        const desired = {
          logical_entity_schema_name: entity.logical_entity_schema_name, logical_entity_name: entity.logical_entity_name,
          logical_attribute_name: column.semantic_name, logical_attribute_definition: column.definition || column.semantic_name,
          logical_attribute_data_type: column.data_type, logical_attribute_is_nullable: column.nullable,
          logical_attribute_is_natural_key: existing ? existing.logical_attribute_is_natural_key : false,
          logical_attribute_is_surrogate_key: false, logical_attribute_ordinal_position: nextOrdinal + offset,
          logical_attribute_is_audit_column: true, logical_attribute_is_active: true,
          logical_attribute_is_locked: existing ? existing.logical_attribute_is_locked : false, sources: existing ? existing.sources : [],
        };
        if (existing?.logical_attribute_is_locked && !same(existing, desired)) throw new Error("A locked Logical audit column cannot be projected.");
        if (!same(existing, desired)) projected.push(desired);
        attributes.set(key, desired);
      });
    }
    return changedAttributes("logical", keys, baseline.attributes, candidate.attributes, projected)
      .sort((left, right) => compareKeys(keys.attribute(left), keys.attribute(right)));
  }

  function goldColumn(template, entityName) {
    const column = {
      semantic_name: template.semantic_name_template.split("{entity_name}").join(entityName),
      data_type: template.data_type, nullable: false,
      definition: template.definition_template.split("{entity_name}").join(entityName),
    };
    if (!validColumn(column)) {
      throw new Error("The Gold surrogate-key template produced an invalid column. Shorten the Entity name so the configured key name fits 255 characters and its definition fits 2000 characters. Preserve the frozen policy.");
    }
    return column;
  }

  function projectDimensional(candidate, baseline, rawTechnical, rawAudit, scdType) {
    const technical = rawTechnical;
    const auditColumns = auditPolicy(rawAudit, "Gold");
    const type2 = technical?.type_2;
    if (!technical?.dimension_surrogate_key || !type2 || ![type2.is_current, type2.effective_from, type2.effective_to].every(validColumn)) {
      throw new Error("The Gold technical-column template is invalid.");
    }
    const keys = layerKeys("dimensional");
    const entities = mergedRecords(baseline.entities, candidate.entities, keys.entity, keys.text);
    const attributes = mergedRecords(baseline.attributes, candidate.attributes, keys.attribute, keys.text);
    const appliedEntities = new Set(baseline.entities.map((record) => keys.text(keys.entity(record))));
    const projected = [];
    const ordered = [...entities.values()].sort((left, right) => compareKeys(keys.entity(left), keys.entity(right)));
    for (const entity of ordered) {
      if (entity.dimensional_entity_is_active !== true) continue;
      const entityKey = keys.entity(entity);
      const ownedBy = () => [...attributes.values()].filter((record) => compareKeys(keys.attribute(record).slice(0, 2), entityKey) === 0);
      let entityAttributes = ownedBy();
      const isNew = !appliedEntities.has(keys.text(entityKey));
      if (isNew || entityAttributes.some((row) => row.dimensional_attribute_is_surrogate_key && row.dimensional_attribute_ordinal_position === 1)) {
        // Reserve ordinal 1 for the own key; retain business relative order.
        entityAttributes.filter((row) => !row.dimensional_attribute_is_surrogate_key)
          .sort((left, right) => left.dimensional_attribute_ordinal_position - right.dimensional_attribute_ordinal_position ||
            compareKeys(keys.attribute(left), keys.attribute(right)))
          .forEach((row, index) => {
            const desired = {...row, dimensional_attribute_ordinal_position: index + 2};
            attributes.set(keys.text(keys.attribute(desired)), desired);
            projected.push(desired);
          });
        entityAttributes = ownedBy();
      }
      let base = Math.max(0, ...entityAttributes.filter((record) => !record.dimensional_attribute_is_audit_column &&
        !record.dimensional_attribute_is_surrogate_key).map((record) => record.dimensional_attribute_ordinal_position));
      const specifications = [];
      const history = [];
      if (entity.dimensional_entity_type === "dimension" || isNew) {
        specifications.push([goldColumn(technical.dimension_surrogate_key, entity.dimensional_entity_name), "technical", "surrogate"]);
        if (entity.dimensional_entity_type === "dimension" && scdType === "type_2") history.push(type2.is_current, type2.effective_from, type2.effective_to);
      }
      // History belongs to the audit group, immediately after SourceSystemID.
      const columns = [...auditColumns];
      const anchor = columns.findIndex((column) => norm(column.semantic_name) === "sourcesystemid");
      columns.splice(anchor + 1, 0, ...history);
      specifications.push(...columns.map((column) => [column, "audit", "none"]));
      const names = specifications.map(([column]) => norm(column.semantic_name));
      if (new Set(names).size !== names.length) throw new Error("Gold policy columns collide after normalization.");
      const surrogateFirst = specifications[0]?.[2] === "surrogate";
      specifications.forEach(([column, role, keyRole], index) => {
        const offset = index + 1;
        const key = keys.text([...entityKey, norm(column.semantic_name)]);
        const existing = attributes.get(key);
        const ordinal = keyRole === "surrogate"
          ? (isNew ? 1 : existing ? existing.dimensional_attribute_ordinal_position : base + 1)
          : base + offset - (surrogateFirst ? 1 : 0);
        if (existing && (existing.dimensional_attribute_is_audit_column !== (role === "audit") || existing.dimensional_attribute_is_natural_key ||
            norm(existing.dimensional_attribute_data_type) !== norm(column.data_type) || existing.dimensional_attribute_is_nullable !== column.nullable ||
            existing.dimensional_attribute_is_surrogate_key !== (keyRole === "surrogate") ||
            (existing.sources?.length && norm(column.semantic_name) !== "sourcesystemid"))) {
          throw new Error("A configured Gold policy column conflicts with an existing Attribute.");
        }
        const desired = {
          dimensional_entity_schema_name: entity.dimensional_entity_schema_name, dimensional_entity_name: entity.dimensional_entity_name,
          dimensional_attribute_name: column.semantic_name, dimensional_attribute_definition: column.definition || column.semantic_name,
          dimensional_attribute_data_type: column.data_type, dimensional_attribute_is_nullable: column.nullable,
          dimensional_attribute_ordinal_position: ordinal, dimensional_attribute_is_natural_key: false,
          dimensional_attribute_is_surrogate_key: keyRole === "surrogate", dimensional_attribute_is_audit_column: role === "audit",
          dimensional_attribute_is_active: true,
          dimensional_attribute_is_locked: existing ? existing.dimensional_attribute_is_locked : false, sources: existing ? existing.sources : [],
        };
        if (existing?.dimensional_attribute_is_locked && !same(existing, desired)) throw new Error("A locked Gold policy column cannot be projected.");
        if (!same(existing, desired)) projected.push(desired);
        attributes.set(key, desired);
        if (keyRole === "surrogate") base = Math.max(base, desired.dimensional_attribute_ordinal_position);
      });
    }
    return changedAttributes("dimensional", keys, baseline.attributes, candidate.attributes, projected)
      .sort((left, right) => core.compareCodePoints(norm(left.dimensional_entity_name), norm(right.dimensional_entity_name)) ||
        left.dimensional_attribute_ordinal_position - right.dimensional_attribute_ordinal_position ||
        core.compareCodePoints(norm(left.dimensional_attribute_name), norm(right.dimensional_attribute_name)));
  }

  return {DEFAULT_AUDIT, DEFAULT_TECHNICAL, effectiveAuditTemplate, effectiveGoldTemplates, projectLogical, projectDimensional};
});
