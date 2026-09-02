(function (root, factory) {
  "use strict";
  let core = root.GDSCore;
  if (typeof module === "object" && module.exports) core = require("./core.js");
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSDbml = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  const COLORS = [
    "#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#B07AA1",
    "#76B7B2", "#EDC948", "#FF9DA7", "#9C755F", "#BAB0AC",
  ];
  const CARDINALITY = {
    one_to_one: "-",
    one_to_many: "<",
    many_to_one: ">",
    many_to_many: "<>",
  };
  const SAFE_TYPE = /^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\((?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?)(?: *, *(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?))*\))?$/;
  const MAX_FILE_BYTES = 12 * 1024 * 1024;
  const MAX_TOTAL_BYTES = 16 * 1024 * 1024;
  const encoder = new TextEncoder();

  function oneLine(value) {
    const rendered = Array.isArray(value) ? value.map(oneLine).join(", ") : String(value ?? "");
    return rendered
      .normalize("NFC")
      .replace(/[\p{Cc}\p{Cf}\p{Cs}]/gu, " ")
      .trim()
      .replace(/\s+/g, " ");
  }

  function normalize(value) {
    return core.normalize("model", "name", oneLine(value));
  }

  function token(value, fallback = "item", limit = 128) {
    let result = oneLine(value).replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
    if (!result) result = fallback;
    if (/^\d/.test(result)) result = `_${result}`;
    return result.slice(0, limit);
  }

  function identifier(value) {
    return `"${oneLine(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
  }

  function quoted(value) {
    return `'${oneLine(value).replaceAll("\\", "\\\\").replaceAll("'", "\\'")}'`;
  }

  function dbmlType(value) {
    const type = oneLine(value) || "unknown";
    return SAFE_TYPE.test(type) ? type : identifier(type);
  }

  function noteLines(values) {
    const content = values
      .filter(([, value]) => value !== null && value !== undefined && oneLine(value))
      .map(([label, value]) => `${label}: ${oneLine(value)}`);
    if (!content.length) return [];
    return ["  Note: '''", ...content.map((line) => `  ${line.replaceAll("\\", "\\\\").replaceAll("'", "\\'")}`), "  '''"];
  }

  function comment(values) {
    return `// ${values
      .filter(([, value]) => value !== null && value !== undefined && oneLine(value))
      .map(([label, value]) => `${label}: ${oneLine(value)}`)
      .join(" | ")}`;
  }

  function projectLines(model, suffix, description) {
    return [
      `Project ${token(`${model.model_name}_${suffix}`, "model")} {`,
      ...noteLines([
        ["Model", model.model_name],
        ["Model ID", model.model_id],
        ["Model revision", model.model_revision],
        ["View", description],
      ]),
      "}",
      "",
    ];
  }

  function rows(loaded, name) {
    const value = loaded.get(name);
    return Array.isArray(value?.effective)
      ? value.effective
      : Array.isArray(value?.records)
        ? value.records
        : [];
  }

  function uniqueBy(records, field, label) {
    const result = new Map();
    for (const record of records) {
      const key = normalize(record[field]);
      if (result.has(key)) throw new Error(`Effective ${label} names are not unique.`);
      result.set(key, record);
    }
    return result;
  }

  function colorMap(groups) {
    const groupNames = [...new Set([...groups.values()].map(normalize))].sort();
    const colors = new Map(groupNames.map((name, index) => [name, COLORS[index % COLORS.length]]));
    return new Map([...groups].map(([key, group]) => [key, colors.get(normalize(group))]));
  }

  function document(path, layer, view, submodelName, lines, tableCount, relationshipCount) {
    return {
      path,
      layer,
      view,
      submodel_name: submodelName,
      content: `${lines.join("\n").trimEnd()}\n`,
      table_count: tableCount,
      relationship_count: relationshipCount,
    };
  }

  function renderConceptual(loaded, model) {
    const objects = rows(loaded, "conceptual_object")
      .filter((record) => record.conceptual_object_status === "active")
      .sort((left, right) => normalize(left.conceptual_object_name).localeCompare(normalize(right.conceptual_object_name)));
    const byKey = uniqueBy(objects, "conceptual_object_name", "Conceptual Object");
    const colors = colorMap(new Map(objects.map((record) => [normalize(record.conceptual_object_name), record.conceptual_object_type])));
    const relationships = rows(loaded, "conceptual_relationship")
      .filter((record) => record.conceptual_relationship_status === "active")
      .sort((left, right) => [left.from_conceptual_object_name, left.to_conceptual_object_name, left.conceptual_relationship_name].map(normalize).join("\0").localeCompare([right.from_conceptual_object_name, right.to_conceptual_object_name, right.conceptual_relationship_name].map(normalize).join("\0")));
    const lines = projectLines(model, "conceptual", "Complete conceptual model");
    for (const record of objects) {
      lines.push(
        `Table ${identifier(record.conceptual_object_name)} [headercolor: ${colors.get(normalize(record.conceptual_object_name))}] {`,
        "  \"__conceptual_key\" conceptual_key [pk, not null, note: 'Visualization-only endpoint; not a modeled Attribute.']",
        ...noteLines([
          ["Type", record.conceptual_object_type],
          ["Grain", record.conceptual_object_grain],
          ["Definition", record.conceptual_object_definition],
          ["Aliases", record.conceptual_object_aliases],
          ["Confidence", record.conceptual_object_confidence],
        ]),
        "}",
        "",
      );
    }
    relationships.forEach((record, index) => {
      const from = byKey.get(normalize(record.from_conceptual_object_name));
      const to = byKey.get(normalize(record.to_conceptual_object_name));
      if (!from || !to) throw new Error("An effective Conceptual Relationship has an inactive or missing endpoint.");
      const operator = CARDINALITY[record.conceptual_relationship_cardinality] || "-";
      lines.push(
        comment([
          ["Relationship", record.conceptual_relationship_name],
          ["Type", record.conceptual_relationship_type],
          ["Definition", record.conceptual_relationship_definition],
          ["Basis", record.conceptual_relationship_basis],
        ]),
        ...(record.conceptual_relationship_cardinality === "unknown" ? ["// Cardinality is unknown; rendered as one-to-one fallback."] : []),
        `Ref conceptual_relationship_${index + 1}: ${identifier(from.conceptual_object_name)}."__conceptual_key" ${operator} ${identifier(to.conceptual_object_name)}."__conceptual_key"`,
        "",
      );
    });
    return document("conceptual.dbml", "conceptual", "complete", null, lines, objects.length, relationships.length);
  }

  function layerSpecification(layer) {
    if (layer === "logical") {
      return {
        submodelDataset: "logical_submodel", submodelName: "logical_submodel_name", submodelDefinition: "logical_submodel_definition", submodelStatus: "logical_submodel_status",
        entityDataset: "logical_entity", entityName: "logical_entity_name", entityStatus: "logical_entity_status", entityOrder: "logical_entity_dependency_order", entityColor: "logical_entity_dependency_order",
        entityNotes: [["Type", "logical_entity_type"], ["Type detail", "logical_entity_type_detail"], ["Grain", "logical_entity_grain"], ["Dependency order", "logical_entity_dependency_order"], ["Definition", "logical_entity_definition"], ["Confidence", "logical_entity_confidence"]],
        attributeDataset: "logical_attribute", attributeEntity: "logical_entity_name", attributeName: "logical_attribute_name", attributeStatus: "logical_attribute_status", attributeType: "logical_attribute_data_type", attributeOrdinal: "logical_attribute_ordinal_position", attributeNullable: "logical_attribute_is_nullable",
        relationshipDataset: "logical_relationship", relationshipStatus: "logical_relationship_status", relationshipName: "logical_relationship_name", relationshipDefinition: "logical_relationship_definition", fromEntity: "from_logical_entity_name", fromAttribute: "from_logical_attribute_name", toEntity: "to_logical_entity_name", toAttribute: "to_logical_attribute_name", relationshipCardinality: "logical_relationship_cardinality",
      };
    }
    return {
      submodelDataset: "dimensional_submodel", submodelName: "dimensional_submodel_name", submodelDefinition: "dimensional_submodel_definition", submodelStatus: "dimensional_submodel_status",
      entityDataset: "dimensional_entity", entityName: "dimensional_entity_name", entityStatus: "dimensional_entity_status", entityOrder: "dimensional_entity_dependency_order", entityColor: "dimensional_entity_type",
      entityNotes: [["Type", "dimensional_entity_type"], ["Fact type", "dimensional_fact_type"], ["Grain", "dimensional_entity_grain_definition"], ["Dependency order", "dimensional_entity_dependency_order"], ["Definition", "dimensional_entity_definition"], ["Confidence", "dimensional_entity_confidence"]],
      attributeDataset: "dimensional_attribute", attributeEntity: "dimensional_entity_name", attributeName: "dimensional_attribute_name", attributeStatus: "dimensional_attribute_status", attributeType: "dimensional_attribute_data_type", attributeOrdinal: "dimensional_attribute_ordinal_position", attributeNullable: "dimensional_attribute_is_nullable",
      relationshipDataset: "dimensional_relationship", relationshipStatus: "dimensional_relationship_status", relationshipName: "dimensional_relationship_name", relationshipDefinition: "dimensional_relationship_definition", fromEntity: "from_dimensional_entity_name", fromAttribute: "from_dimensional_attribute_name", toEntity: "to_dimensional_entity_name", toAttribute: "to_dimensional_attribute_name", relationshipCardinality: "dimensional_relationship_cardinality",
    };
  }

  function prepareLayer(loaded, layer) {
    const spec = layerSpecification(layer);
    const submodels = rows(loaded, spec.submodelDataset)
      .filter((record) => record[spec.submodelStatus] === "active")
      .map((record) => ({ name: record[spec.submodelName], definition: record[spec.submodelDefinition] }))
      .sort((left, right) => normalize(left.name).localeCompare(normalize(right.name)));
    uniqueBy(submodels, "name", `${layer} Submodel`);
    const activeSubmodels = new Set(submodels.map((item) => normalize(item.name)));
    const entities = rows(loaded, spec.entityDataset)
      .filter((record) => record[spec.entityStatus] === "active")
      .map((record) => {
        const memberships = new Set();
        for (const membership of Array.isArray(record.submodels) ? record.submodels : []) {
          if (membership?.membership_status !== "active") continue;
          const key = normalize(membership.submodel_name);
          if (!activeSubmodels.has(key)) throw new Error(`An effective ${layer} Entity membership has an inactive or missing Submodel.`);
          memberships.add(key);
        }
        return {
          name: record[spec.entityName],
          order: record[spec.entityOrder],
          colorGroup: String(record[spec.entityColor] ?? "unspecified"),
          notes: spec.entityNotes.map(([label, field]) => [label, record[field]]),
          submodels: memberships,
        };
      })
      .sort((left, right) => (left.order ?? 0) - (right.order ?? 0) || normalize(left.name).localeCompare(normalize(right.name)));
    const entityByKey = uniqueBy(entities, "name", `${layer} Entity`);
    const attributesByEntity = new Map();
    const attributeKeys = new Set();
    for (const record of rows(loaded, spec.attributeDataset).filter((item) => item[spec.attributeStatus] === "active")) {
      const entityKey = normalize(record[spec.attributeEntity]);
      if (!entityByKey.has(entityKey)) throw new Error(`An effective ${layer} Attribute has an inactive or missing Entity.`);
      const key = `${entityKey}\0${normalize(record[spec.attributeName])}`;
      if (attributeKeys.has(key)) throw new Error(`Effective ${layer} Attribute names are not unique.`);
      attributeKeys.add(key);
      const logical = layer === "logical";
      const keyRole = record.dimensional_attribute_key_role;
      const notes = [record[`${layer}_attribute_definition`]];
      if (logical && record.logical_attribute_is_surrogate_key) notes.push("Surrogate key.");
      else if (logical && record.logical_attribute_is_natural_key) notes.push("Natural key.");
      if (!logical) {
        notes.push(`Role: ${record.dimensional_attribute_role}.`);
        if (keyRole && keyRole !== "none") notes.push(`Key role: ${keyRole}.`);
        if (record.dimensional_attribute_is_grain_component) notes.push("Grain component.");
      }
      if (record[`${layer}_attribute_is_audit_column`]) notes.push("Audit Attribute.");
      const attribute = {
        name: record[spec.attributeName], type: record[spec.attributeType], ordinal: record[spec.attributeOrdinal], nullable: record[spec.attributeNullable],
        primary: logical ? record.logical_attribute_is_primary_key : keyRole === "surrogate",
        natural: logical ? record.logical_attribute_is_natural_key : keyRole === "business",
        surrogate: logical ? record.logical_attribute_is_surrogate_key : false,
        notes: notes.filter((value) => value !== null && value !== undefined && oneLine(value)),
      };
      if (!attributesByEntity.has(entityKey)) attributesByEntity.set(entityKey, []);
      attributesByEntity.get(entityKey).push(attribute);
    }
    for (const attributes of attributesByEntity.values()) attributes.sort((left, right) => (left.ordinal ?? 0) - (right.ordinal ?? 0) || normalize(left.name).localeCompare(normalize(right.name)));
    const relationships = rows(loaded, spec.relationshipDataset)
      .filter((record) => record[spec.relationshipStatus] === "active")
      .map((record) => ({
        name: record[spec.relationshipName], definition: record[spec.relationshipDefinition],
        fromEntity: normalize(record[spec.fromEntity]), fromAttribute: normalize(record[spec.fromAttribute]),
        toEntity: normalize(record[spec.toEntity]), toAttribute: normalize(record[spec.toAttribute]),
        cardinality: record[spec.relationshipCardinality],
        notes: layer === "logical"
          ? [["Basis", record.logical_relationship_basis], ["Confidence", record.logical_relationship_confidence]]
          : [["Kind", record.dimensional_relationship_kind], ["Role", record.dimensional_relationship_role_name], ["Optional", record.dimensional_relationship_is_optional ? "yes" : "no"], ["Basis", record.dimensional_relationship_basis], ["Confidence", record.dimensional_relationship_confidence]],
      }))
      .sort((left, right) => `${left.fromEntity}\0${left.toEntity}\0${normalize(left.name)}`.localeCompare(`${right.fromEntity}\0${right.toEntity}\0${normalize(right.name)}`));
    for (const relationship of relationships) {
      if (
        !entityByKey.has(relationship.fromEntity) ||
        !entityByKey.has(relationship.toEntity) ||
        !attributeKeys.has(`${relationship.fromEntity}\0${relationship.fromAttribute}`) ||
        !attributeKeys.has(`${relationship.toEntity}\0${relationship.toAttribute}`)
      ) throw new Error(`An effective ${layer} Relationship has an inactive or missing endpoint.`);
      if (!CARDINALITY[relationship.cardinality]) throw new Error(`An effective ${layer} Relationship has invalid cardinality.`);
    }
    return { layer, submodels, entities, entityByKey, attributesByEntity, relationships };
  }

  function keySettings(attributes) {
    const inline = new Map();
    const indexes = [];
    const primary = attributes.filter((item) => item.primary);
    const natural = attributes.filter((item) => item.natural && !item.primary);
    const surrogate = attributes.filter((item) => item.surrogate && !item.primary);
    const add = (name, setting) => inline.set(normalize(name), [...(inline.get(normalize(name)) || []), setting]);
    if (primary.length === 1) add(primary[0].name, "pk");
    else if (primary.length) indexes.push([primary.map((item) => item.name), "pk"]);
    if (natural.length === 1) add(natural[0].name, "unique");
    else if (natural.length) indexes.push([natural.map((item) => item.name), "unique"]);
    surrogate.forEach((item) => add(item.name, "unique"));
    return { inline, indexes };
  }

  function renderModeled(model, data, included, path, view, submodelName, description) {
    const include = included || new Set(data.entities.map((entity) => normalize(entity.name)));
    const colors = colorMap(new Map(data.entities.map((entity) => [normalize(entity.name), entity.colorGroup])));
    const lines = projectLines(model, token(description), description);
    let tableCount = 0;
    for (const entity of data.entities) {
      const entityKey = normalize(entity.name);
      if (!include.has(entityKey)) continue;
      tableCount += 1;
      lines.push(`Table ${identifier(entity.name)} [headercolor: ${colors.get(entityKey)}] {`);
      const attributes = data.attributesByEntity.get(entityKey) || [];
      const settings = keySettings(attributes);
      for (const attribute of attributes) {
        const values = [...(settings.inline.get(normalize(attribute.name)) || [])];
        values.push(attribute.nullable ? "null" : "not null");
        if (attribute.notes.length) values.push(`note: ${quoted(attribute.notes.join(" "))}`);
        lines.push(`  ${identifier(attribute.name)} ${dbmlType(attribute.type)} [${values.join(", ")}]`);
      }
      if (settings.indexes.length) {
        lines.push("  indexes {");
        settings.indexes.forEach(([names, setting]) => lines.push(`    (${names.map(identifier).join(", ")}) [${setting}]`));
        lines.push("  }");
      }
      lines.push(...noteLines(entity.notes), "}", "");
    }
    let relationshipCount = 0;
    for (const relationship of data.relationships) {
      if (!include.has(relationship.fromEntity) || !include.has(relationship.toEntity)) continue;
      relationshipCount += 1;
      const from = data.entityByKey.get(relationship.fromEntity);
      const to = data.entityByKey.get(relationship.toEntity);
      const fromAttribute = data.attributesByEntity.get(relationship.fromEntity).find((item) => normalize(item.name) === relationship.fromAttribute);
      const toAttribute = data.attributesByEntity.get(relationship.toEntity).find((item) => normalize(item.name) === relationship.toAttribute);
      lines.push(
        comment([["Relationship", relationship.name], ["Definition", relationship.definition], ...relationship.notes]),
        `Ref ${data.layer}_relationship_${relationshipCount}: ${identifier(from.name)}.${identifier(fromAttribute.name)} ${CARDINALITY[relationship.cardinality]} ${identifier(to.name)}.${identifier(toAttribute.name)}`,
        "",
      );
    }
    return document(path, data.layer, view, submodelName, lines, tableCount, relationshipCount);
  }

  function modeledDocuments(loaded, model, layer, includeSubmodels) {
    const data = prepareLayer(loaded, layer);
    const documents = [renderModeled(model, data, null, `${layer}_complete.dbml`, "complete", null, `Complete ${layer} model`)];
    if (!includeSubmodels) return documents;
    const usedNames = new Set([`${layer}_complete.dbml`, `${layer}_default.dbml`]);
    const assigned = new Set();
    for (const submodel of data.submodels) {
      const key = normalize(submodel.name);
      const members = new Set(data.entities.filter((entity) => entity.submodels.has(key)).map((entity) => normalize(entity.name)));
      members.forEach((member) => assigned.add(member));
      const base = `${layer}_${token(submodel.name, "submodel", 220).toLowerCase()}`;
      let path = `${base}.dbml`;
      let suffix = 2;
      while (usedNames.has(path.toLowerCase())) path = `${base}_${suffix++}.dbml`;
      usedNames.add(path.toLowerCase());
      documents.push(renderModeled(model, data, members, path, "submodel", submodel.name, `${layer[0].toUpperCase()}${layer.slice(1)} Submodel: ${submodel.name}. ${submodel.definition || ""}`));
    }
    const unassigned = new Set(data.entities.map((entity) => normalize(entity.name)).filter((key) => !assigned.has(key)));
    if (unassigned.size) documents.push(renderModeled(model, data, unassigned, `${layer}_default.dbml`, "default", null, `${layer[0].toUpperCase()}${layer.slice(1)} Entities without an active Submodel membership`));
    return documents;
  }

  function render(loaded, model, options = {}) {
    if (!(loaded instanceof Map)) throw new Error("Effective Model datasets are required for DBML generation.");
    if (!model || !Number.isSafeInteger(model.model_id) || typeof model.model_name !== "string" || !Number.isSafeInteger(model.model_revision)) {
      throw new Error("Model identity is required for DBML generation.");
    }
    const modelType = options.modelType || "full";
    const includeSubmodels = options.includeSubmodels !== false;
    if (!new Set(["full", "conceptual", "logical", "dimensional"]).has(modelType)) throw new Error("DBML model type is invalid.");
    const documents = [];
    if (modelType === "full" || modelType === "conceptual") documents.push(renderConceptual(loaded, model));
    if (modelType === "full" || modelType === "logical") documents.push(...modeledDocuments(loaded, model, "logical", includeSubmodels));
    if (modelType === "full" || modelType === "dimensional") documents.push(...modeledDocuments(loaded, model, "dimensional", includeSubmodels));
    documents.sort((left, right) => left.path.localeCompare(right.path));
    const paths = documents.map((item) => item.path.toLowerCase());
    const sizes = documents.map((item) => encoder.encode(item.content).length);
    if (!documents.length || documents.length > 1002 || paths.length !== new Set(paths).size) throw new Error("DBML file inventory is invalid.");
    if (documents.some((item) => !/^[A-Za-z0-9_][A-Za-z0-9_.-]*\.dbml$/.test(item.path)) || sizes.some((size) => size < 1 || size > MAX_FILE_BYTES) || sizes.reduce((sum, size) => sum + size, 0) > MAX_TOTAL_BYTES) throw new Error("DBML output exceeds its safe file bounds.");
    return documents;
  }

  return { render };
});
