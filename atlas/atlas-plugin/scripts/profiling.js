"use strict";

// SQL shape mirrors the server's aggregate planner; parity is tested in Python.
const { normalize } = require("../workbench/core.js");
const fields = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"];
const norm = (value) => normalize("metadata", "object_name", value);
const key = (row, prefix = "") => JSON.stringify(fields.map((field) => norm(row[prefix + field])));
const ownKey = (row) => Object.fromEntries(fields.map((field) => [field, row[field]]));
const attributeKey = (row, prefix = "") => JSON.stringify([...fields, "attribute_name"].map((field) => norm(row[prefix + field])));
const active = (row) => row.is_active !== false;
const quote = (value) => {
  if (typeof value !== "string" || !value.trim() || value.includes("\0")) throw Error("Missing SQL coordinate.");
  return "`" + value.replaceAll("`", "``") + "`";
};
const normalizedType = (value) => value.toUpperCase().replace(/\s+/g, "");
const stringType = /^(?:STRING|VARCHAR(?:\(\d+\))?|CHAR(?:\(\d+\))?)$/;
const scalarType = /^(?:BOOLEAN|BYTE|TINYINT|SHORT|SMALLINT|INT|INTEGER|LONG|BIGINT|FLOAT|REAL|DOUBLE|DATE|TIMESTAMP(?:_NTZ|_LTZ)?|DECIMAL\(\d+,\d+\)|NUMERIC\(\d+,\d+\))$/;

function maskingKeys(metadata) {
  // A mapped Source mask remains binding even when the Source Attribute is inactive.
  const sourceAttributes = metadata.source_attribute ?? [];
  const masked = new Map([...sourceAttributes, ...(metadata.bronze_attribute ?? [])]
    .filter((row) => row.is_masking_required === true).map((row) => [attributeKey(row), "masking_required"]));
  for (const mapping of metadata.ingestion_attribute_mapping ?? []) {
    if (active(mapping) && masked.has(attributeKey(mapping, "source_"))) masked.set(attributeKey(mapping, "target_"), "masking_required");
  }
  // Attribute Mappings are advisory: expressions and absent mappings can carry any
  // protected Source value. Do not claim unprotected Bronze lineage from names.
  const protectedObjects = new Set(sourceAttributes.filter((row) => row.is_masking_required === true).map((row) => key(row)));
  for (const object of metadata.bronze_object ?? []) {
    const origins = (metadata.ingestion_object_mapping ?? []).filter((row) => key(row, "target_") === key(object));
    const uncertain = origins.some((row) => protectedObjects.has(key(row, "source_"))) || (!origins.length &&
      (metadata.source_object ?? []).some((row) => norm(row.source_tenant_code) === norm(object.source_tenant_code) && protectedObjects.has(key(row))));
    if (uncertain) for (const attribute of metadata.bronze_attribute ?? []) {
      if (key(attribute) === key(object) && !masked.has(attributeKey(attribute))) masked.set(attributeKey(attribute), "unproven_masking_lineage");
    }
  }
  return masked;
}

function validateBatchType(values, type) {
  const bounds = {BYTE: [-128n, 127n], TINYINT: [-128n, 127n], SHORT: [-32768n, 32767n], SMALLINT: [-32768n, 32767n],
    INT: [-2147483648n, 2147483647n], INTEGER: [-2147483648n, 2147483647n], LONG: [-9223372036854775808n, 9223372036854775807n], BIGINT: [-9223372036854775808n, 9223372036854775807n]};
  const decimal = /^(?:DECIMAL|NUMERIC)\((\d+),(\d+)\)$/.exec(type);
  const width = /^(?:CHAR|VARCHAR)\((\d+)\)$/.exec(type);
  const dateValid = (value) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return false;
    const [year, month, day] = match.slice(1).map(Number);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  };
  for (const value of batchValue(values)) {
    let valid = false;
    if (stringType.test(type)) valid = !width || (Number(width[1]) > 0 && [...value].length <= Number(width[1]));
    else if (bounds[type]) valid = /^[+-]?\d+$/.test(value) && BigInt(value) >= bounds[type][0] && BigInt(value) <= bounds[type][1];
    else if (decimal) {
      const precision = Number(decimal[1]), scale = Number(decimal[2]);
      const match = /^[+-]?(\d+)(?:\.(\d+))?$/.exec(value);
      valid = precision >= 1 && precision <= 38 && scale <= precision && !!match &&
        match[1].replace(/^0+/, "").length <= precision - scale && (match[2] ?? "").replace(/0+$/, "").length <= scale;
    } else if (type === "BOOLEAN") valid = /^(?:true|false)$/i.test(value);
    else if (type === "DATE") valid = dateValid(value);
    else if (/^TIMESTAMP(?:_NTZ|_LTZ)?$/.test(type)) {
      const match = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})?$/.exec(value);
      const offset = match?.[6];
      valid = !!match && dateValid(match[1]) && Number(match[2]) < 24 && Number(match[3]) < 60 && Number(match[4]) < 60 &&
        (type === "TIMESTAMP_NTZ" ? !offset : !!offset) && (!offset || offset === "Z" || (Number(offset.slice(1, 3)) <= 18 && Number(offset.slice(4)) < 60 && (Number(offset.slice(1, 3)) < 18 || Number(offset.slice(4)) === 0)));
    }
    // Float batch identities are intentionally unsupported; rounded casts can
    // silently choose a different population. Profiling float attributes is fine.
    if (!valid) throw Error("Batch ID cannot be converted exactly to its registered physical type.");
  }
}

function batchValue(value) {
  if (!Array.isArray(value) || !value.length || value.length > 2000 || value.some((item) =>
    typeof item !== "string" || !item.trim() || item.length > 4000 || item.includes("\0"))) {
    throw Error("Batch IDs must be a nonempty list of nonblank strings.");
  }
  return [...new Set(value)].sort();
}

function batchPredicate(batch) {
  if (!batch) return "";
  validateBatchType(batch.values, batch.type);
  return ` WHERE ${quote(batch.name)} IN (${batch.values.map((value) =>
    `CAST(CAST(X'${Buffer.from(value, "utf8").toString("hex")}' AS STRING) AS ${batch.type})`).join(", ")})`;
}

function buildQuery(relation, attributes, batch) {
  const aggregates = ["       COUNT(*) AS row_count"];
  const percentage = (numerator, denominator) => "CAST(CASE WHEN " + denominator +
    " = 0 THEN 0.0 ELSE ROUND(CAST(100 AS DOUBLE) * (" + numerator + ") / " + denominator + ", 4) END AS DOUBLE)";
  const projections = attributes.map((attribute, index) => {
    const identifier = quote(attribute.name);
    const type = normalizedType(attribute.data_type);
    const string = stringType.test(type), distinct = string || scalarType.test(type);
    const prefix = `p${index}`, nonNull = `${prefix}_non_null_count`, nullCount = `(row_count - ${nonNull})`;
    const distinctValue = `${prefix}_distinct_count`, blankValue = `${prefix}_blank_count`;
    aggregates.push(`       COUNT(${identifier}) AS ${nonNull}`);
    if (distinct) aggregates.push(`       COUNT(DISTINCT ${identifier}) AS ${distinctValue}`);
    if (string) aggregates.push(
      `       CAST(COALESCE(SUM(CASE WHEN ${identifier} IS NOT NULL AND TRIM(${identifier}) = '' THEN 1 ELSE 0 END), 0) AS BIGINT) AS ${blankValue}`,
      `       MIN(LENGTH(${identifier})) AS ${prefix}_min_data_length`,
      `       MAX(LENGTH(${identifier})) AS ${prefix}_max_data_length`,
      `       AVG(CAST(LENGTH(${identifier}) AS DOUBLE)) AS ${prefix}_avg_data_length`);
    const values = [
      `CAST(${attribute.index} AS BIGINT) AS attribute_index`,
      "CAST(row_count AS BIGINT) AS row_count",
      `CAST(${nonNull} AS BIGINT) AS non_null_count`,
      `CAST(${nullCount} AS BIGINT) AS null_count`,
      `CAST(${string ? blankValue : "NULL"} AS BIGINT) AS blank_count`,
      `CAST(${distinct ? distinctValue : "NULL"} AS BIGINT) AS distinct_count`,
      `CAST(${string ? prefix + "_min_data_length" : "NULL"} AS INT) AS min_data_length`,
      `CAST(${string ? prefix + "_max_data_length" : "NULL"} AS INT) AS max_data_length`,
      `CAST(${string ? "ROUND(" + prefix + "_avg_data_length, 6)" : "NULL"} AS DOUBLE) AS avg_data_length`,
      `${percentage(nonNull, "row_count")} AS percent_populated`,
      `${distinct ? percentage(`(${nonNull} - ${distinctValue})`, nonNull) : "CAST(NULL AS DOUBLE)"} AS percent_duplicates`,
      `${percentage(nullCount, "row_count")} AS percent_null`,
      `${string ? percentage(blankValue, nonNull) : "CAST(NULL AS DOUBLE)"} AS percent_blank`,
      `${distinct ? percentage(distinctValue, nonNull) : "CAST(NULL AS DOUBLE)"} AS percent_distinct`,
    ];
    return "SELECT\n" + values.map((value) => "       " + value).join(",\n") + "\n  FROM summary";
  });
  // Hex encoding keeps all user batch text out of SQL syntax, including quotes/backslashes.
  const predicate = batch ? "\n" + batchPredicate(batch).trimStart() : "";
  return "WITH scoped AS (\nSELECT\n" + attributes.map((a) => "       " + quote(a.name)).join(",\n") +
    "\n  FROM " + relation + predicate + "\n),\nsummary AS (\nSELECT\n" + aggregates.join(",\n") +
    "\n  FROM scoped\n)\n" + projections.join("\nUNION ALL\n");
}

function planProfiling(metadata, scope, plan) {
  if (!plan || Array.isArray(plan) || typeof plan !== "object" ||
      Object.keys(plan).some((field) => !["systems", "objects", "selected_objects", "max_attributes_per_query"].includes(field))) {
    throw Error("Profiling plan accepts systems, objects, selected_objects and max_attributes_per_query only.");
  }
  const maxAttributes = Object.hasOwn(plan, "max_attributes_per_query") ? plan.max_attributes_per_query : 50;
  if (!Number.isInteger(maxAttributes) || maxAttributes < 1 || maxAttributes > 50) throw Error("max_attributes_per_query must be an integer from 1 to 50.");
  const assignments = {};
  for (const level of ["systems", "objects"]) {
    const rows = plan[level] ?? [];
    if (!Array.isArray(rows) || rows.length > 2000) throw Error("Invalid batch assignments.");
    const names = level === "objects" ? fields : level === "systems" ? ["source_tenant_code", "system_code"] : ["source_tenant_code"];
    assignments[level] = new Map();
    for (const row of rows) {
      if (!row || Object.keys(row).some((name) => ![...names, "batch_ids"].includes(name)) ||
          names.some((name) => typeof row[name] !== "string" || !row[name].trim())) throw Error("Invalid batch assignment key.");
      const identity = JSON.stringify(names.map((name) => norm(row[name])));
      if (assignments[level].has(identity)) throw Error("Duplicate/conflicting batch assignment.");
      assignments[level].set(identity, batchValue(row.batch_ids));
    }
  }
  const objects = new Map([...(metadata.source_object ?? []), ...(metadata.bronze_object ?? [])].filter(active).map((row) => [key(row), row]));
  const knownSystems = new Set([...objects.values()].filter((row) => norm(row.zone_code) === "source")
    .map((row) => JSON.stringify([norm(row.source_tenant_code), norm(row.system_code)])));
  for (const [level, known] of [["systems", knownSystems], ["objects", objects]]) {
    for (const identity of assignments[level].keys()) if (!known.has(identity)) throw Error("Unknown batch assignment; use registered Source Tenant, System, and Object keys.");
  }
  const attributes = [...(metadata.source_attribute ?? []), ...(metadata.bronze_attribute ?? [])].filter(active);
  const selected = plan.selected_objects;
  if (selected !== undefined && (!Array.isArray(selected) || !selected.length)) throw Error("selected_objects must be a nonempty list.");
  const selectedKeys = selected ? new Set(selected.map((row) => {
    if (!row || Object.keys(row).length !== fields.length || fields.some((name) => typeof row[name] !== "string" || !row[name].trim())) throw Error("Invalid selected Object key.");
    return key(row);
  })) : null;
  if (selectedKeys && selectedKeys.size !== selected.length) throw Error("Duplicate selected Object.");
  const scoped = scope.filter(active).filter((row) => !selectedKeys || selectedKeys.has(key(row))).sort((a, b) => key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0);
  if (!scoped.length || scoped.length > 2000 || (selectedKeys && selectedKeys.size !== scoped.length)) throw Error("Selection must match active Model Input Scope.");
  const queries = [], coverage = [], masked = maskingKeys(metadata);
  for (const scopedObject of scoped) {
    const object = objects.get(key(scopedObject));
    if (!object) throw Error("Scoped Object is absent from authorized Source/Bronze Metadata.");
    const source = norm(object.zone_code) === "source";
    const connection = (metadata.connection ?? []).find((row) => active(row) &&
      ["tenant_code", "system_code", "connection_code"].every((field) => norm(row[field]) === norm(object[field])));
    const tenant = (metadata.tenant ?? []).find((row) => active(row) && norm(row.tenant_code) === norm(object.tenant_code));
    if (!connection || !tenant) throw Error("Object placement is not active in Metadata.");
    const catalogOwners = (metadata.tenant ?? []).filter((row) => active(row) && norm(row.tenant_code) === norm(object.source_tenant_code));
    if (!source && catalogOwners.length !== 1) throw Error("Object catalog owner is not uniquely active in Metadata.");
    const relation = [source ? connection.foreign_catalog : catalogOwners[0].tenant_catalog,
      source ? object.fc_object_schema : object.object_schema,
      source ? object.fc_object_name : object.object_name].map(quote).join(".");
    const allMembers = attributes.filter((row) => key(row) === key(object)).sort((a, b) =>
      a.attribute_ordinal_position - b.attribute_ordinal_position || (norm(a.attribute_name) < norm(b.attribute_name) ? -1 : norm(a.attribute_name) > norm(b.attribute_name) ? 1 : 0));
    if (!allMembers.length || allMembers.length > 2000) throw Error("Object requires 1–2000 active Attributes.");
    const members = allMembers.filter((row) => !masked.has(attributeKey(row)));
    coverage.push({object: ownKey(object), active_attribute_count: allMembers.length,
      planned_attribute_count: members.length, excluded: allMembers.filter((row) => masked.has(attributeKey(row)))
        .map((row) => ({...ownKey(object), attribute_name: row.attribute_name, reason: masked.get(attributeKey(row))}))});
    if (!members.length) continue;
    const origins = source ? [object] : (metadata.ingestion_object_mapping ?? []).filter((row) => active(row) && key(row, "target_") === key(object))
      .map((row) => objects.get(key(row, "source_"))).filter((row) => row && norm(row.source_tenant_code) === norm(object.source_tenant_code));
    const originSystems = [...new Set(origins.map((row) => norm(row.system_code)))];
    let batch = null;
    const systemChoices = originSystems.map((system) => JSON.stringify([norm(object.source_tenant_code), system]));
    const matched = systemChoices.filter((identity) => assignments.systems.has(identity));
    if (object.batch_attribute_name && !assignments.objects.has(key(object)) && matched.length && (originSystems.length !== 1 || matched.length !== 1)) throw Error("Ambiguous originating System batch; resolve Object assignment explicitly.");
    if (matched.length) batch = assignments.systems.get(matched[0]);
    if (object.batch_attribute_name && !origins.length && assignments.systems.size && !assignments.objects.has(key(object))) throw Error("Resolve Bronze originating System through ingestion Mapping.");
    if (assignments.objects.has(key(object))) batch = assignments.objects.get(key(object));
    const batchAttribute = object.batch_attribute_name ? allMembers.find((row) => norm(row.attribute_name) === norm(object.batch_attribute_name)) : null;
    let filter = null;
    if (object.batch_attribute_name) {
      if (batch === null) throw Error("Batch IDs are required for every batched Object.");
      if (!batchAttribute) throw Error("Registered batch column is not an active Attribute.");
      if (masked.has(attributeKey(batchAttribute))) throw Error("Masked batch Attribute cannot be used for Profiling.");
      const type = normalizedType(batchAttribute.attribute_data_type);
      if (!stringType.test(type) && !scalarType.test(type)) throw Error("Unsupported batch data type.");
      filter = {name: source ? batchAttribute.fc_attribute_name : batchAttribute.attribute_name, type, values: batch};
    }
    const projected = members.map((row, index) => ({index: index + 1,
      name: source ? row.fc_attribute_name : row.attribute_name, data_type: row.attribute_data_type,
      key: {...ownKey(object), attribute_name: row.attribute_name}}));
    if (new Set(projected.map((row) => norm(row.name))).size !== projected.length) throw Error("Attribute SQL coordinates are ambiguous.");
    for (let offset = 0; offset < projected.length;) {
      let count = Math.min(maxAttributes, projected.length - offset);
      let chunk, sql;
      do { chunk = projected.slice(offset, offset + count); sql = buildQuery(relation, chunk, filter); }
      while (sql.length > 100000 && --count > 0);
      if (!count) throw Error("Profiling query exceeds SQL limit.");
      queries.push({object: ownKey(object), source_tenant_code: object.source_tenant_code,
        source_system_codes: originSystems, batch_ids: filter ? batch : null, batch: filter, relation,
        attributes: chunk.map((row) => ({attribute_index: row.index, ...row.key})), sql});
      offset += count;
    }
  }
  return {queries, coverage};
}

module.exports = {batchValue, validateBatchType, batchPredicate, buildQuery, planProfiling, fields, norm, key, ownKey, attributeKey, maskingKeys, quote,
  normalizedType, stringType, scalarType};
