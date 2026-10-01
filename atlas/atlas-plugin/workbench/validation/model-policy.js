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
    const modelDetails = loaded.get("model_details");
    for (const field of ["logical_entity_scd_type", "dimensional_entity_scd_type"]) {
      if (modelDetails?.baseline?.length && modelDetails.pending?.length &&
          (modelDetails.baseline[0][field] ?? null) !== (modelDetails.pending[0][field] ?? null)) {
        add("model_policy_read_only", "model_details", field, "SCD type must be changed through Model settings.");
      }
    }
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
      const entityField = `${layer}_entity_name`, schemaField = `${layer}_entity_schema_name`, attributeField = `${layer}_attribute_name`;
      const entityKey = record => tuple([record[schemaField], record[entityField]]);
      const configuredSchemas = details[`${layer}_schemas`] ?? (loaded.has("model_details") ? [] : undefined);
      if (Array.isArray(configuredSchemas)) {
        const allowed = new Set(configuredSchemas.map(item => norm(item.schema_name)));
        for (const entity of rows(loaded, entityDataset)) if (!allowed.has(norm(entity[schemaField]))) add("model.entity-schema", entityDataset, schemaField, "Entity schema must be configured on its Model layer.");
      }
      const entities = rows(loaded, entityDataset).filter(active), attributes = rows(loaded, attributeDataset).filter(active);
      const byEntity = new Map(entities.map(entity => [entityKey(entity), entity]));
      const submodels = new Map(rows(loaded, submodelDataset).map(record => [norm(record[`${layer}_submodel_name`]), record]));
      const newEntities = new Set((added.get(entityDataset) || []).filter(active).map(record => entityKey(record)));
      const touchedEntities = new Set([...(changed.get(entityDataset) || []).map(record => entityKey(record)), ...(changed.get(attributeDataset) || []).map(record => entityKey(record))]);
      for (const entity of changed.get(entityDataset) || []) {
        for (const membership of entity.submodels || []) if (membership.membership_status === "active" && (!active(entity) || !active(submodels.get(norm(membership.submodel_name)) || {}))) add("model.membership-state", entityDataset, "submodels", "Active membership needs an active Entity and Submodel.");
      }
      for (const attribute of rows(loaded, attributeDataset).filter(active)) {
        const parent = byEntity.get(entityKey(attribute));
        if (!parent) continue;
        if (layer === "logical") {
          const parentSources = new Set((parent.sources || []).filter(source => core.active(source) !== false && source.source_object).map(source => physical(source.source_object)));
          for (const source of attribute.sources || []) if (core.active(source) !== false && source.support_source_type === "attribute" && !parentSources.has(physical(source.source_attribute))) add("model.parent-source", attributeDataset, "sources", "An Attribute's physical source requires the matching Object source on its parent Entity.");
        } else {
          const logicalKey = source => tuple([source?.logical_entity_schema_name, source?.logical_entity_name]);
          const parentSources = new Set((parent.sources || []).filter(source => core.active(source) !== false && source.source_logical_entity).map(source => logicalKey(source.source_logical_entity)));
          for (const source of attribute.sources || []) if (core.active(source) !== false && source.support_source_type === "logical_attribute" && !parentSources.has(logicalKey(source.source_logical_attribute))) add("model.parent-source", attributeDataset, "sources", "A Dimensional Attribute's Logical source requires matching Logical Entity support on its parent.");
        }
      }
      for (const [name, entity] of byEntity) {
        if (!touchedEntities.has(name)) continue;
        const columns = attributes.filter(attribute => entityKey(attribute) === name).sort((a, b) => a[`${layer}_attribute_ordinal_position`] - b[`${layer}_attribute_ordinal_position`]);
        const ordinals = columns.map(attribute => attribute[`${layer}_attribute_ordinal_position`]);
        if (new Set(ordinals).size !== ordinals.length) add("model.attribute-order", attributeDataset, `${layer}_attribute_ordinal_position`, "Active Attributes within an Entity need distinct ordinal positions.");
        if (!newEntities.has(name)) continue; // Preserve approved historical layouts.
        const surrogates = columns.filter(attribute => layer === "logical" ? attribute.logical_attribute_is_surrogate_key : attribute.dimensional_attribute_key_role === "surrogate");
        const surrogate = surrogates[0];
        if (surrogates.length !== 1 || surrogate?.[`${layer}_attribute_ordinal_position`] !== 1 || surrogate?.[`${layer}_attribute_is_nullable`] !== false || norm(surrogate?.[`${layer}_attribute_data_type`]) !== "bigint" || surrogate?.sources?.length || (layer === "logical" && (surrogate.logical_attribute_is_natural_key || surrogate.logical_attribute_is_audit_column))) add("model.own-surrogate", attributeDataset, attributeField, "Every new Entity, including facts and bridges, needs one generated non-null BIGINT own surrogate at ordinal 1 without physical sources.");
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
      const byAttribute = new Map(attributes.map(attribute => [tuple([attribute[schemaField], attribute[entityField], attribute[attributeField]]), attribute]));
      for (const relation of changed.get(`${layer}_relationship`) || []) {
        if (!active(relation)) continue;
        const endpoints = ["from", "to"].map(prefix => byAttribute.get(tuple([relation[`${prefix}_${schemaField}`], relation[`${prefix}_${entityField}`], relation[`${prefix}_${attributeField}`]])));
        if (endpoints.every(Boolean) && norm(endpoints[0][`${layer}_attribute_data_type`]) !== norm(endpoints[1][`${layer}_attribute_data_type`])) add("model.relationship-type", `${layer}_relationship`, `${layer}_relationship_name`, "Relationship endpoint types differ; resolve an explicit compatible representation before defining the FK.");
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
    const sourceKey = (record, layer, attribute = false) => tuple([`${layer}_entity_schema_name`, `${layer}_entity_name`, ...(attribute ? [`${layer}_attribute_name`] : [])].map(field => record?.[field]));
    const sourceEntities = {}, sourceAttributes = {};
    for (const layer of ["logical", "dimensional"]) {
      sourceEntities[layer] = new Set(rows(loaded, `${layer}_entity`).filter(active).map(record => sourceKey(record, layer)));
      sourceAttributes[layer] = new Set(rows(loaded, `${layer}_attribute`).filter(active).map(record => sourceKey(record, layer, true)));
    }
    const branch = record => tuple([record.modeled_entity_type, record.modeled_entity_schema_name, record.modeled_entity_name, record.source_system_code]);
    const mappingObjects = new Map(rows(loaded, "mapping_object").filter(active).map(record => [branch(record), record]));
    for (const record of changed.get("mapping_object") || []) {
      if (!active(record) || record.output_template_code && record.output_template_code !== "mapping_object_default") continue;
      const document = record.mapping_transformation_document;
      if (document === null) continue;
      if (!document || !Array.isArray(document.steps) || !document.steps.length || document.steps.some(step => typeof step !== "string" || !step.trim())) { add("mapping.object-steps", "mapping_object", "mapping_transformation_document", "An active Mapping branch needs concise ordered transformation steps."); continue; }
      const dimensional = record.modeled_entity_type === "dimensional_entity";
      if (dimensional && document.source_objects != null) add("mapping.source-kind", "mapping_object", "mapping_transformation_document", "Dimensional Mapping uses modeled source identities; physical source fields must be null or absent.");
      if (!dimensional && document.source_dimensional_entities != null) add("mapping.source-kind", "mapping_object", "mapping_transformation_document", "Logical Mapping cannot use Dimensional source identities.");
      const aliases = new Set();
      for (const inputField of dimensional ? ["source_logical_entities", "source_dimensional_entities"] : ["source_objects", "source_logical_entities"]) {
        const layer = inputField === "source_objects" ? null : inputField === "source_logical_entities" ? "logical" : "dimensional";
        const fields = layer ? [`${layer}_entity_schema_name`, `${layer}_entity_name`] : PHYSICAL;
        const inputs = document[inputField] ?? [];
        if (!Array.isArray(inputs)) { add("mapping.source-objects", "mapping_object", "mapping_transformation_document", "Mapping Entity inputs must be an array or null."); continue; }
        for (const source of inputs) {
          if (!source || fields.some(field => typeof source[field] !== "string" || !source[field].trim()) || typeof source.alias !== "string" || !source.alias.trim() || aliases.has(norm(source.alias))) add("mapping.source-alias", "mapping_object", "mapping_transformation_document", "Query inputs need complete source identities and unique nonempty aliases.");
          aliases.add(norm(source?.alias));
          if (layer ? !sourceEntities[layer].has(sourceKey(source, layer)) : metadata && !physicalObjects.has(physical(source))) add("mapping.source-exists", "mapping_object", "mapping_transformation_document", "A Mapping input does not exist in the supplied applied source context.");
        }
      }
    }
    for (const record of changed.get("mapping_attribute") || []) {
      if (!active(record) || record.output_template_code && record.output_template_code !== "mapping_attribute_default") continue;
      const document = record.attribute_mapping_transformation_document;
      if (document === null) continue;
      if (!document || typeof document.transformation !== "string" || !document.transformation.trim()) { add("mapping.attribute-rule", "mapping_attribute", "attribute_mapping_transformation_document", "Every active mapped Attribute needs an explicit transformation or generated/framework population rule."); continue; }
      const object = mappingObjects.get(branch(record));
      const dimensional = record.modeled_entity_type === "dimensional_entity";
      if (dimensional && document.source_attributes != null) add("mapping.source-kind", "mapping_attribute", "attribute_mapping_transformation_document", "Dimensional Mapping uses modeled source identities; physical source fields must be null or absent.");
      if (!dimensional && document.source_dimensional_attributes != null) add("mapping.source-kind", "mapping_attribute", "attribute_mapping_transformation_document", "Logical Mapping cannot use Dimensional source identities.");
      for (const sourceField of dimensional ? ["source_logical_attributes", "source_dimensional_attributes"] : ["source_attributes", "source_logical_attributes"]) {
        const layer = sourceField === "source_attributes" ? null : sourceField === "source_logical_attributes" ? "logical" : "dimensional";
        const inputs = object?.mapping_transformation_document?.[layer ? `source_${layer}_entities` : "source_objects"];
        const sources = document[sourceField] ?? [];
        if (!Array.isArray(sources)) { add("mapping.source-attributes", "mapping_attribute", "attribute_mapping_transformation_document", "Mapping Attribute inputs must be an array or null."); continue; }
        for (const source of sources) {
          if (layer ? !sourceAttributes[layer].has(sourceKey(source, layer, true)) : metadata && !physicalAttributes.has(tuple([...PHYSICAL, "attribute_name"].map(field => source?.[field])))) add("mapping.attribute-exists", "mapping_attribute", "attribute_mapping_transformation_document", "A Mapping source Attribute does not exist in applied source context.");
          if (object?.mapping_transformation_document != null && (!Array.isArray(inputs) || !inputs.some(input => layer ? sourceKey(input, layer) === sourceKey(source, layer) : physical(input) === physical(source)))) add("mapping.parent-input", "mapping_attribute", "attribute_mapping_transformation_document", "An Attribute source must belong to an Object-level query input in the same System branch.");
        }
      }
    }
  }
  return { validate, AUDIT };
});
