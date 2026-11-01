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
  // Model relationships point child -> parent, so only these two remain.
  const CARDINALITY = {
    many_to_one: ">",
    one_to_one: "-",
  };
  const OBJECT_FIELDS = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"];
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
    return core.normalize("project", "name", oneLine(value));
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

  function projectLines(project, suffix, description) {
    return [
      `Project ${token(`${project.project_name}_${suffix}`, "project")} {`,
      ...noteLines([
        ["Project", project.project_name],
        ["Project ID", project.project_id],
        ["Project revision", project.project_revision],
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

  function document(path, layer, view, subjectAreaName, lines, tableCount, relationshipCount) {
    return {
      path,
      layer,
      view,
      subject_area_name: subjectAreaName,
      content: `${lines.join("\n").trimEnd()}\n`,
      table_count: tableCount,
      relationship_count: relationshipCount,
    };
  }

  function entityKey(record, layer, prefix = "") {
    return JSON.stringify([normalize(record?.[`${prefix}${layer}_entity_schema_name`]), normalize(record?.[`${prefix}${layer}_entity_name`])]);
  }

  function objectKey(record) {
    return JSON.stringify(OBJECT_FIELDS.map((field) => normalize(record?.[field])));
  }

  // Subject Areas are focus windows over Input Scope Objects. A Logical Entity belongs to the
  // areas of its active Object sources; a Dimensional Entity to the areas of its Logical sources.
  function subjectAreaIndex(loaded) {
    const areas = rows(loaded, "subject_area")
      .filter((record) => record.subject_area_is_active === true)
      .map((record) => ({ key: normalize(record.subject_area_name), name: record.subject_area_name, definition: record.subject_area_definition }))
      .sort((left, right) => core.compareCodePoints(left.key, right.key));
    uniqueBy(areas, "name", "Subject Area");
    const names = new Map(areas.map((area) => [area.key, area.name]));
    const byObject = new Map();
    for (const member of rows(loaded, "subject_area_table")) {
      const area = normalize(member.subject_area_name);
      if (member.subject_area_table_is_active !== true || !names.has(area)) continue;
      const object = objectKey(member);
      if (!byObject.has(object)) byObject.set(object, new Set());
      byObject.get(object).add(area);
    }
    const objectAreas = (record) => new Set((Array.isArray(record.sources) ? record.sources : [])
      .filter((source) => source?.support_source_type === "object" && source.is_active === true)
      .flatMap((source) => [...(byObject.get(objectKey(source.source_object)) || [])]));
    const logical = new Map(rows(loaded, "logical_entity")
      .filter((record) => record.logical_entity_is_active === true)
      .map((record) => [entityKey(record, "logical"), objectAreas(record)]));
    const logicalAreas = (record) => new Set((Array.isArray(record.sources) ? record.sources : [])
      .filter((source) => source?.support_source_type === "logical_entity" && source.is_active === true)
      .flatMap((source) => [...(logical.get(entityKey(source.source_logical_entity, "logical")) || [])]));
    return { areas, names, entityAreas: (layer, record) => layer === "logical" ? objectAreas(record) : logicalAreas(record) };
  }

  // Worked out for display only; Dimensional Relationships store no kind or optionality.
  function dimensionalKind(fromType, toType) {
    if (toType !== "dimension") return "reference";
    if (fromType === "fact") return "fact_dimension";
    if (fromType === "bridge") return "bridge_dimension";
    return fromType === "dimension" ? "dimension_outrigger" : "reference";
  }

  function prepareLayer(loaded, layer, areaIndex) {
    const history = rows(loaded, "project_details")
      .some((record) => record[`${layer}_entity_scd_type`] === "type_2");
    const notes = layer === "logical"
      ? [["Type", "logical_entity_type"], ["Grain", "logical_entity_grain"], ["Dependency order", "logical_entity_dependency_order"], ["Definition", "logical_entity_definition"]]
      : [["Type", "dimensional_entity_type"], ["Fact type", "dimensional_fact_type"], ["Grain", "dimensional_entity_grain_definition"], ["Dependency order", "dimensional_entity_dependency_order"], ["Definition", "dimensional_entity_definition"]];
    const entities = rows(loaded, `${layer}_entity`)
      .filter((record) => record[`${layer}_entity_is_active`] === true)
      .map((record) => {
        const areas = areaIndex.entityAreas(layer, record);
        const areaNames = [...areas].sort(core.compareCodePoints).map((area) => areaIndex.names.get(area));
        return {
          schema: record[`${layer}_entity_schema_name`],
          key: entityKey(record, layer),
          name: record[`${layer}_entity_name`],
          type: record.dimensional_entity_type ?? null,
          order: record[`${layer}_entity_dependency_order`],
          historized: history && (layer === "logical" || record.dimensional_entity_type === "dimension"),
          colorGroup: String(record[layer === "logical" ? "logical_entity_dependency_order" : "dimensional_entity_type"] ?? "unspecified"),
          notes: [...notes.map(([label, field]) => [label, record[field]]), ["Subject Areas", areaNames.length ? areaNames : null]],
          areas,
        };
      })
      .sort((left, right) => (left.order ?? 0) - (right.order ?? 0) || normalize(left.name).localeCompare(normalize(right.name)));
    const entityByKey = new Map();
    for (const entity of entities) {
      if (!oneLine(entity.schema)) throw new Error(`An effective ${layer} Entity needs its schema name.`);
      if (entityByKey.has(entity.key)) throw new Error(`Effective ${layer} Entity identities are not unique.`);
      entityByKey.set(entity.key, entity);
    }
    const attributesByEntity = new Map();
    const attributeKeys = new Set();
    for (const record of rows(loaded, `${layer}_attribute`).filter((item) => item[`${layer}_attribute_is_active`] === true)) {
      const parent = entityKey(record, layer);
      if (!entityByKey.has(parent)) throw new Error(`An effective ${layer} Attribute has an inactive or missing Entity.`);
      const key = `${parent}\0${normalize(record[`${layer}_attribute_name`])}`;
      if (attributeKeys.has(key)) throw new Error(`Effective ${layer} Attribute names are not unique.`);
      attributeKeys.add(key);
      const notes = [record[`${layer}_attribute_definition`]];
      if (record[`${layer}_attribute_is_surrogate_key`]) notes.push("Surrogate key.");
      else if (record[`${layer}_attribute_is_natural_key`]) notes.push("Natural key.");
      if (record[`${layer}_attribute_is_audit_column`]) notes.push("Audit Attribute.");
      const attribute = {
        name: record[`${layer}_attribute_name`], type: record[`${layer}_attribute_data_type`],
        ordinal: record[`${layer}_attribute_ordinal_position`], nullable: record[`${layer}_attribute_is_nullable`],
        natural: record[`${layer}_attribute_is_natural_key`],
        surrogate: record[`${layer}_attribute_is_surrogate_key`],
        historized: entityByKey.get(parent).historized,
        notes: notes.filter((value) => value !== null && value !== undefined && oneLine(value)),
      };
      if (!attributesByEntity.has(parent)) attributesByEntity.set(parent, []);
      attributesByEntity.get(parent).push(attribute);
    }
    for (const attributes of attributesByEntity.values()) attributes.sort((left, right) => (left.ordinal ?? 0) - (right.ordinal ?? 0) || normalize(left.name).localeCompare(normalize(right.name)));
    // Child -> parent: from is the child's foreign key, to is the parent's key.
    const relationships = rows(loaded, `${layer}_relationship`)
      .filter((record) => record[`${layer}_relationship_is_active`] === true)
      .map((record) => ({
        fromEntity: entityKey(record, layer, "from_"), fromAttribute: normalize(record[`from_${layer}_attribute_name`]),
        toEntity: entityKey(record, layer, "to_"), toAttribute: normalize(record[`to_${layer}_attribute_name`]),
        cardinality: layer === "logical" ? record.logical_relationship_cardinality : "many_to_one",
        role: record.dimensional_relationship_role_name ?? null,
        basis: record[`${layer}_relationship_basis`] ?? null,
      }))
      .sort((left, right) => core.compareCodePoints(`${left.fromEntity}\0${left.fromAttribute}\0${left.toEntity}\0${left.toAttribute}`,
        `${right.fromEntity}\0${right.fromAttribute}\0${right.toEntity}\0${right.toAttribute}`));
    for (const relationship of relationships) {
      if (
        !entityByKey.has(relationship.fromEntity) ||
        !entityByKey.has(relationship.toEntity) ||
        !attributeKeys.has(`${relationship.fromEntity}\0${relationship.fromAttribute}`) ||
        !attributeKeys.has(`${relationship.toEntity}\0${relationship.toAttribute}`)
      ) throw new Error(`An effective ${layer} Relationship has an inactive or missing endpoint.`);
      if (!CARDINALITY[relationship.cardinality]) throw new Error(`An effective ${layer} Relationship has invalid cardinality.`);
      const foreignKey = attributesByEntity.get(relationship.fromEntity).find((item) => normalize(item.name) === relationship.fromAttribute);
      relationship.notes = layer === "logical"
        ? [["Basis", relationship.basis]]
        : [["Kind", dimensionalKind(entityByKey.get(relationship.fromEntity).type, entityByKey.get(relationship.toEntity).type)],
          ["Role", relationship.role], ["Optional", foreignKey.nullable ? "yes" : "no"], ["Basis", relationship.basis]];
    }
    return { layer, entities, entityByKey, attributesByEntity, relationships };
  }

  function keySettings(attributes) {
    const inline = new Map();
    const indexes = [];
    // Business identity repeats across historical versions; its role alone is
    // insufficient to declare a unique physical tuple for a historized Entity.
    const natural = attributes.some((item) => item.historized) ? [] : attributes.filter((item) => item.natural);
    const surrogate = attributes.filter((item) => item.surrogate);
    const add = (name, setting) => inline.set(normalize(name), [...(inline.get(normalize(name)) || []), setting]);
    if (natural.length === 1) add(natural[0].name, "unique");
    else if (natural.length) indexes.push([natural.map((item) => item.name), "unique"]);
    surrogate.forEach((item) => add(item.name, "unique"));
    return { inline, indexes };
  }

  function renderModeled(project, data, included, path, view, subjectAreaName, description) {
    const include = included || new Set(data.entities.map((entity) => entity.key));
    const colors = colorMap(new Map(data.entities.map((entity) => [entity.key, entity.colorGroup])));
    const lines = projectLines(project, token(description), description);
    let tableCount = 0;
    for (const entity of data.entities) {
      const entityKey = entity.key;
      if (!include.has(entityKey)) continue;
      tableCount += 1;
      lines.push(`Table ${identifier(entity.schema)}.${identifier(entity.name)} [headercolor: ${colors.get(entityKey)}] {`);
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
        comment([["Relationship", `${from.name}.${fromAttribute.name} -> ${to.name}.${toAttribute.name}`], ...relationship.notes]),
        `Ref ${data.layer}_relationship_${relationshipCount}: ${identifier(from.schema)}.${identifier(from.name)}.${identifier(fromAttribute.name)} ${CARDINALITY[relationship.cardinality]} ${identifier(to.schema)}.${identifier(to.name)}.${identifier(toAttribute.name)}`,
        "",
      );
    }
    return document(path, data.layer, view, subjectAreaName, lines, tableCount, relationshipCount);
  }

  // One file for the whole layer plus one per active Subject Area that has modeled Entities.
  function modeledDocuments(loaded, project, layer, includeSubjectAreas, areaIndex) {
    const data = prepareLayer(loaded, layer, areaIndex);
    const title = `${layer[0].toUpperCase()}${layer.slice(1)}`;
    const documents = [renderModeled(project, data, null, `${layer}_complete.dbml`, "complete", null, `Complete ${layer} model`)];
    if (!includeSubjectAreas) return documents;
    const usedNames = new Set([`${layer}_complete.dbml`]);
    for (const area of areaIndex.areas) {
      const members = new Set(data.entities.filter((entity) => entity.areas.has(area.key)).map((entity) => entity.key));
      if (!members.size) continue;
      const base = `${layer}_${token(area.name, "subject_area", 220).toLowerCase()}`;
      let path = `${base}.dbml`;
      let suffix = 2;
      while (usedNames.has(path.toLowerCase())) path = `${base}_${suffix++}.dbml`;
      usedNames.add(path.toLowerCase());
      documents.push(renderModeled(project, data, members, path, "subject_area", area.name, `${title} Subject Area: ${area.name}. ${area.definition || ""}`));
    }
    return documents;
  }

  function render(loaded, project, options = {}) {
    if (!(loaded instanceof Map)) throw new Error("Effective Project datasets are required for DBML generation.");
    if (!project || !Number.isSafeInteger(project.project_id) || typeof project.project_name !== "string" || !Number.isSafeInteger(project.project_revision)) {
      throw new Error("Project identity is required for DBML generation.");
    }
    const modelType = options.modelType || "full";
    const includeSubjectAreas = options.includeSubjectAreas !== false;
    if (!new Set(["full", "logical", "dimensional"]).has(modelType)) throw new Error("DBML model type is invalid.");
    const areaIndex = subjectAreaIndex(loaded);
    const documents = [];
    if (modelType === "full" || modelType === "logical") documents.push(...modeledDocuments(loaded, project, "logical", includeSubjectAreas, areaIndex));
    if (modelType === "full" || modelType === "dimensional") documents.push(...modeledDocuments(loaded, project, "dimensional", includeSubjectAreas, areaIndex));
    documents.sort((left, right) => left.path.localeCompare(right.path));
    const paths = documents.map((item) => item.path.toLowerCase());
    const sizes = documents.map((item) => encoder.encode(item.content).length);
    if (!documents.length || documents.length > 1002 || paths.length !== new Set(paths).size) throw new Error("DBML file inventory is invalid.");
    if (documents.some((item) => !/^[A-Za-z0-9_][A-Za-z0-9_.-]*\.dbml$/.test(item.path)) || sizes.some((size) => size < 1 || size > MAX_FILE_BYTES) || sizes.reduce((sum, size) => sum + size, 0) > MAX_TOTAL_BYTES) throw new Error("DBML output exceeds its safe file bounds.");
    return documents;
  }

  return { render };
});
