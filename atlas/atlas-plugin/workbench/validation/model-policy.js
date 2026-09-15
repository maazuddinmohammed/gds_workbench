(function (root, factory) {
  "use strict";
  const node = typeof module === "object" && module.exports;
  const api = factory(node ? require("../core.js") : root.GDSCore);
  if (node) module.exports = api;
  root.AtlasModelPolicy = api;
})(globalThis, function (core) {
  "use strict";
  const AUDIT = ["SourceSystemID", "IsDataValid", "HashKey", "IsActive", "GDSBatchID", "PipelineRunID", "CreatedDate", "UpdatedDate", "CreatedBy", "UpdatedBy"];
  const PHYSICAL = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"];
  const norm = value => core.normalize("model", "value", value);
  const tuple = values => core.stableStringify(values.map(norm));
  const active = record => core.active(record) === true;
  const same = (a, b) => core.stableStringify(a) === core.stableStringify(b);
  const physical = record => tuple(PHYSICAL.map(field => record?.[field]));
  const rows = (loaded, dataset) => loaded.get(dataset)?.effective || [];

  function validate(loaded, metadata, context = {}) {
    const issues = [], changed = new Map(), added = new Map();
    const add = (code, dataset, field, message, severity = "error") => issues.push({ code, dataset, field, message, severity });
    for (const [dataset, value] of loaded) {
      const originals = new Map((value.baseline || []).map(record => [core.stableStringify(core.key("model", value.definition, record)), record]));
      changed.set(dataset, (value.pending || []).filter(record => !same(originals.get(core.stableStringify(core.key("model", value.definition, record))), record)));
      added.set(dataset, (value.pending || []).filter(record => !originals.has(core.stableStringify(core.key("model", value.definition, record)))));
    }
    const details = rows(loaded, "model_details")[0] || context.model || {};
    for (const dataset of ["conceptual_object", "conceptual_relationship", "logical_submodel", "logical_entity", "logical_attribute", "logical_relationship", "dimensional_submodel", "dimensional_entity", "dimensional_attribute", "dimensional_relationship"]) {
      const override = dataset.startsWith("dimensional") ? details.gold_model_naming_instructions : details.silver_model_naming_instructions;
      for (const record of added.get(dataset) || []) {
        const field = `${dataset}_name`, name = record[field];
        if (!override && (typeof name !== "string" || !/^[A-Z][A-Za-z0-9]*$/.test(name) || /Id$/.test(name))) add("model.naming-policy", dataset, field, "New modeled names use PascalCase and uppercase ID for an identifier suffix. An approved Model naming override may specify another convention.");
      }
      if (override && (added.get(dataset) || []).length) add("model.naming-review", dataset, `${dataset}_name`, "Review new names against the Model's explicit naming instructions.", "warning");
    }

    for (const layer of ["logical", "dimensional"]) {
      const entityDataset = `${layer}_entity`, attributeDataset = `${layer}_attribute`, submodelDataset = `${layer}_submodel`;
      const entityField = `${layer}_entity_name`, attributeField = `${layer}_attribute_name`;
      const entities = rows(loaded, entityDataset).filter(active), attributes = rows(loaded, attributeDataset).filter(active);
      const byEntity = new Map(entities.map(entity => [norm(entity[entityField]), entity]));
      const submodels = new Map(rows(loaded, submodelDataset).map(record => [norm(record[`${layer}_submodel_name`]), record]));
      const newEntities = new Set((added.get(entityDataset) || []).filter(active).map(record => norm(record[entityField])));
      const touchedEntities = new Set([...(changed.get(entityDataset) || []).map(record => norm(record[entityField])), ...(changed.get(attributeDataset) || []).map(record => norm(record[entityField]))]);
      for (const entity of changed.get(entityDataset) || []) {
        for (const membership of entity.submodels || []) if (membership.membership_status === "active" && (!active(entity) || !active(submodels.get(norm(membership.submodel_name)) || {}))) add("model.membership-state", entityDataset, "submodels", "Active membership needs an active Entity and Submodel.");
      }
      for (const attribute of changed.get(attributeDataset) || []) {
        const parent = byEntity.get(norm(attribute[entityField]));
        if (!parent) continue;
        const parentSources = new Set((parent.sources || []).filter(source => source.support_source_status === "active" || source.source_status === "active" || source.is_active === true).map(source => physical(source.source_object)));
        // Source status field is layer-neutral in normalized records.
        for (const source of parent.sources || []) if (core.active(source) !== false && source.source_object) parentSources.add(physical(source.source_object));
        for (const source of attribute.sources || []) if (core.active(source) !== false && source.support_source_type === "attribute" && !parentSources.has(physical(source.source_attribute))) add("model.parent-source", attributeDataset, "sources", "An Attribute's physical source requires the matching Object source on its parent Entity.");
      }
      for (const [name, entity] of byEntity) {
        if (!touchedEntities.has(name)) continue;
        const columns = attributes.filter(attribute => norm(attribute[entityField]) === name).sort((a, b) => a[`${layer}_attribute_ordinal_position`] - b[`${layer}_attribute_ordinal_position`]);
        const ordinals = columns.map(attribute => attribute[`${layer}_attribute_ordinal_position`]);
        if (new Set(ordinals).size !== ordinals.length) add("model.attribute-order", attributeDataset, `${layer}_attribute_ordinal_position`, "Active Attributes within an Entity need distinct ordinal positions.");
        if (!newEntities.has(name)) continue; // Preserve approved historical layouts.
        const surrogates = columns.filter(attribute => layer === "logical" ? attribute.logical_attribute_is_surrogate_key : attribute.dimensional_attribute_key_role === "surrogate");
        const surrogate = surrogates[0];
        if (surrogates.length !== 1 || surrogate?.[`${layer}_attribute_ordinal_position`] !== 1 || surrogate?.[`${layer}_attribute_is_nullable`] !== false || norm(surrogate?.[`${layer}_attribute_data_type`]) !== "bigint" || surrogate?.sources?.length || (layer === "logical" && (!surrogate.logical_attribute_is_primary_key || surrogate.logical_attribute_is_natural_key || surrogate.logical_attribute_is_audit_column))) add("model.own-surrogate", attributeDataset, attributeField, "Every new Entity, including facts and bridges, needs one generated non-null BIGINT own surrogate at ordinal 1 without physical sources.");
        const naming = layer === "logical" ? details.silver_model_naming_instructions : details.gold_model_naming_instructions;
        if (surrogate && !naming && !surrogate[attributeField]?.endsWith(layer === "logical" ? "ID" : "Key")) add("model.key-suffix", attributeDataset, attributeField, `The own surrogate uses the ${layer === "logical" ? "ID" : "Key"} suffix under the default policy.`);
        const template = layer === "logical" ? details.silver_model_audit_columns_template : details.gold_model_audit_columns_template;
        const configured = Array.isArray(template?.columns) ? template.columns : AUDIT.map(semantic_name => ({ semantic_name }));
        const expected = configured.map(column => column.semantic_name);
        const byName = new Map(columns.map(column => [norm(column[attributeField]), column]));
        const actualAudit = columns.filter(column => expected.some(item => norm(item) === norm(column[attributeField])));
        if (actualAudit.length !== expected.length || !same(actualAudit.map(column => norm(column[attributeField])), expected.map(norm))) add("model.audit-order", attributeDataset, attributeField, "New Entity audit columns must contain the complete configured audit block in order.");
        for (const specification of configured) {
          const column = byName.get(norm(specification.semantic_name));
          if (!column) continue;
          if (!column[`${layer}_attribute_is_audit_column`]) add("model.audit-role", attributeDataset, attributeField, "Configured audit columns must be marked as audit columns.");
          if (specification.data_type && norm(column[`${layer}_attribute_data_type`]) !== norm(specification.data_type) || specification.nullable !== undefined && column[`${layer}_attribute_is_nullable`] !== specification.nullable) add("model.audit-template", attributeDataset, attributeField, "Audit types and nullability must match the configured Model template.");
          if (norm(specification.semantic_name) !== "sourcesystemid" && column.sources?.length) add("model.framework-source", attributeDataset, "sources", "Framework-populated audit columns have no fabricated physical source lineage.");
        }
        if (!template) add("model.audit-template-review", attributeDataset, attributeField, "The audit names are checked; exact types and nullability need the approved Model template.", "warning");
      }
      const byAttribute = new Map(attributes.map(attribute => [tuple([attribute[entityField], attribute[attributeField]]), attribute]));
      for (const relation of changed.get(`${layer}_relationship`) || []) {
        if (!active(relation)) continue;
        const endpoints = ["from", "to"].map(prefix => byAttribute.get(tuple([relation[`${prefix}_${entityField}`], relation[`${prefix}_${attributeField}`]])));
        if (endpoints.every(Boolean) && norm(endpoints[0][`${layer}_attribute_data_type`]) !== norm(endpoints[1][`${layer}_attribute_data_type`])) add("model.relationship-type", `${layer}_relationship`, `${layer}_relationship_name`, "Relationship endpoint types differ; resolve an explicit compatible representation before defining the FK.");
      }
    }

    for (const dataset of ["model_object_binding", "model_attribute_binding"]) {
      const value = loaded.get(dataset);
      if (!value) continue;
      const originals = new Map(value.baseline.map(record => [core.stableStringify(core.key("model", value.definition, record)), record]));
      const fields = [...PHYSICAL, ...(dataset === "model_attribute_binding" ? ["attribute_name"] : [])];
      for (const record of changed.get(dataset) || []) {
        const original = originals.get(core.stableStringify(core.key("model", value.definition, record)));
        if (original && fields.some(field => norm(original[field]) !== norm(record[field]))) add("binding.reassignment-unsupported", dataset, "object_name", "Retargeting an existing Binding is unsupported. Preserve it and resolve the governed change separately.");
      }
    }
    validateMappings(loaded, metadata, changed, add);
    return issues;
  }

  function validateMappings(loaded, metadata, changed, add) {
    const physicalObjects = new Set(), physicalAttributes = new Set();
    if (metadata) for (const [name, value] of metadata) for (const record of value.baseline || value.effective || []) {
      if (name.endsWith("_object")) physicalObjects.add(physical(record));
      if (name.endsWith("_attribute")) physicalAttributes.add(tuple([...PHYSICAL, "attribute_name"].map(field => record[field])));
    }
    const branch = record => tuple([record.modeled_entity_type, record.modeled_entity_name, record.source_system_code]);
    const mappingObjects = new Map(rows(loaded, "mapping_object").filter(active).map(record => [branch(record), record]));
    for (const record of changed.get("mapping_object") || []) {
      if (!active(record) || record.output_template_code && record.output_template_code !== "mapping_object_default") continue;
      const document = record.mapping_transformation_document;
      if (!document || !Array.isArray(document.steps) || !document.steps.length || document.steps.some(step => typeof step !== "string" || !step.trim())) { add("mapping.object-steps", "mapping_object", "mapping_transformation_document", "An active Mapping branch needs concise ordered transformation steps."); continue; }
      const inputs = document.source_objects || [], aliases = new Set();
      if (!Array.isArray(inputs)) { add("mapping.source-objects", "mapping_object", "mapping_transformation_document", "Mapping source_objects must be an array or null."); continue; }
      for (const source of inputs) {
        if (!source || PHYSICAL.some(field => typeof source[field] !== "string" || !source[field].trim()) || typeof source.alias !== "string" || !source.alias.trim() || aliases.has(norm(source.alias))) add("mapping.source-alias", "mapping_object", "mapping_transformation_document", "Query inputs need complete physical identities and unique nonempty aliases.");
        aliases.add(norm(source?.alias));
        if (metadata && !physicalObjects.has(physical(source))) add("mapping.source-exists", "mapping_object", "mapping_transformation_document", "A Mapping input does not exist in the supplied applied Metadata context.");
      }
    }
    for (const record of changed.get("mapping_attribute") || []) {
      if (!active(record) || record.output_template_code && record.output_template_code !== "mapping_attribute_default") continue;
      const document = record.attribute_mapping_transformation_document;
      if (!document || typeof document.transformation !== "string" || !document.transformation.trim()) { add("mapping.attribute-rule", "mapping_attribute", "attribute_mapping_transformation_document", "Every active mapped Attribute needs an explicit transformation or generated/framework population rule."); continue; }
      const object = mappingObjects.get(branch(record));
      const inputs = object?.mapping_transformation_document?.source_objects;
      const sources = document.source_attributes || [];
      if (!Array.isArray(sources)) { add("mapping.source-attributes", "mapping_attribute", "attribute_mapping_transformation_document", "Mapping source_attributes must be an array or null."); continue; }
      for (const source of sources) {
        if (metadata && !physicalAttributes.has(tuple([...PHYSICAL, "attribute_name"].map(field => source?.[field])))) add("mapping.attribute-exists", "mapping_attribute", "attribute_mapping_transformation_document", "A Mapping source Attribute does not exist in applied Metadata context.");
        if (Array.isArray(inputs) && !inputs.some(input => physical(input) === physical(source))) add("mapping.parent-input", "mapping_attribute", "attribute_mapping_transformation_document", "An Attribute source must belong to an Object-level query input in the same System branch.");
      }
    }
  }
  return { validate, AUDIT };
});
