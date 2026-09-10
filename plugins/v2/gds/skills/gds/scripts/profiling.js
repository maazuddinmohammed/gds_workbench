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
  const masked = new Set([...(metadata.source_attribute ?? []), ...(metadata.bronze_attribute ?? [])]
    .filter((row) => row.is_masking_required === true).map((row) => attributeKey(row)));
  for (const mapping of metadata.ingestion_attribute_mapping ?? []) {
    if (active(mapping) && masked.has(attributeKey(mapping, "source_"))) masked.add(attributeKey(mapping, "target_"));
  }
  return masked;
}

function batchValue(value) {
  if (value !== null && (typeof value !== "string" || !value.trim() || value.length > 4000 || value.includes("\0"))) {
    throw Error("Batch IDs must be nonblank strings or null for all rows.");
  }
  return value;
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
  const predicate = batch ? `\n WHERE ${quote(batch.name)} = CAST(CAST(X'${Buffer.from(batch.value, "utf8").toString("hex")}' AS STRING) AS ${batch.type})` : "";
  return "WITH scoped AS (\nSELECT\n" + attributes.map((a) => "       " + quote(a.name)).join(",\n") +
    "\n  FROM " + relation + predicate + "\n),\nsummary AS (\nSELECT\n" + aggregates.join(",\n") +
    "\n  FROM scoped\n)\n" + projections.join("\nUNION ALL\n");
}

function planProfiling(metadata, scope, plan) {
  if (!plan || Array.isArray(plan) || typeof plan !== "object" ||
      !Object.hasOwn(plan, "default_batch_id") ||
      Object.keys(plan).some((field) => !["default_batch_id", "tenants", "systems", "objects", "selected_objects"].includes(field))) {
    throw Error("Profiling plan requires default_batch_id and only documented fields.");
  }
  batchValue(plan.default_batch_id);
  const assignments = {};
  for (const level of ["tenants", "systems", "objects"]) {
    const rows = plan[level] ?? [];
    if (!Array.isArray(rows) || rows.length > 2000) throw Error("Invalid batch assignments.");
    const names = level === "objects" ? fields : level === "systems" ? ["source_tenant_code", "system_code"] : ["source_tenant_code"];
    assignments[level] = new Map();
    for (const row of rows) {
      if (!row || Object.keys(row).some((name) => ![...names, "batch_id"].includes(name)) ||
          names.some((name) => typeof row[name] !== "string" || !row[name].trim())) throw Error("Invalid batch assignment key.");
      const identity = JSON.stringify(names.map((name) => norm(row[name])));
      if (assignments[level].has(identity)) throw Error("Duplicate/conflicting batch assignment.");
      assignments[level].set(identity, batchValue(row.batch_id));
    }
  }
  const objects = new Map([...(metadata.source_object ?? []), ...(metadata.bronze_object ?? [])].filter(active).map((row) => [key(row), row]));
  const knownTenants = new Set([...objects.values()].map((row) => JSON.stringify([norm(row.source_tenant_code)])));
  const knownSystems = new Set([...objects.values()].filter((row) => norm(row.zone_code) === "source")
    .map((row) => JSON.stringify([norm(row.source_tenant_code), norm(row.system_code)])));
  for (const [level, known] of [["tenants", knownTenants], ["systems", knownSystems], ["objects", objects]]) {
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
  const scoped = scope.filter(active).filter((row) => !selectedKeys || selectedKeys.has(key(row)));
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
    const relation = [source ? connection.foreign_catalog : tenant.tenant_catalog,
      source ? object.fc_object_schema : object.object_schema,
      source ? object.fc_object_name : object.object_name].map(quote).join(".");
    const allMembers = attributes.filter((row) => key(row) === key(object)).sort((a, b) =>
      a.attribute_ordinal_position - b.attribute_ordinal_position || String(a.attribute_name).localeCompare(String(b.attribute_name)));
    if (!allMembers.length || allMembers.length > 2000) throw Error("Object requires 1–2000 active Attributes.");
    const members = allMembers.filter((row) => !masked.has(attributeKey(row)));
    coverage.push({object: ownKey(object), active_attribute_count: allMembers.length,
      planned_attribute_count: members.length, excluded: allMembers.filter((row) => masked.has(attributeKey(row)))
        .map((row) => ({...ownKey(object), attribute_name: row.attribute_name, reason: "masking_required"}))});
    if (!members.length) continue;
    const origins = source ? [object] : (metadata.ingestion_object_mapping ?? []).filter((row) => active(row) && key(row, "target_") === key(object))
      .map((row) => objects.get(key(row, "source_"))).filter((row) => row && norm(row.source_tenant_code) === norm(object.source_tenant_code));
    const originSystems = [...new Set(origins.map((row) => norm(row.system_code)))];
    let batch = plan.default_batch_id;
    const tenantKey = JSON.stringify([norm(object.source_tenant_code)]);
    if (assignments.tenants.has(tenantKey)) batch = assignments.tenants.get(tenantKey);
    const systemChoices = originSystems.map((system) => JSON.stringify([norm(object.source_tenant_code), system]));
    const matched = systemChoices.filter((identity) => assignments.systems.has(identity));
    if (object.batch_attribute_name && !assignments.objects.has(key(object)) && matched.length && (originSystems.length !== 1 || matched.length !== 1)) throw Error("Ambiguous originating System batch; resolve Object assignment explicitly.");
    if (matched.length) batch = assignments.systems.get(matched[0]);
    if (object.batch_attribute_name && !origins.length && assignments.systems.size && !assignments.objects.has(key(object))) throw Error("Resolve Bronze originating System through ingestion Mapping.");
    if (assignments.objects.has(key(object))) batch = assignments.objects.get(key(object));
    const batchAttribute = object.batch_attribute_name ? allMembers.find((row) => norm(row.attribute_name) === norm(object.batch_attribute_name)) : null;
    let filter = null;
    if (batch !== null && object.batch_attribute_name) {
      if (!batchAttribute) throw Error("Registered batch column is not an active Attribute.");
      if (masked.has(attributeKey(batchAttribute))) throw Error("Masked batch Attribute cannot be used for Profiling.");
      const type = normalizedType(batchAttribute.attribute_data_type);
      if (!stringType.test(type) && !scalarType.test(type)) throw Error("Unsupported batch data type.");
      filter = {name: source ? batchAttribute.fc_attribute_name : batchAttribute.attribute_name, type, value: batch};
    }
    const projected = members.map((row, index) => ({index: index + 1,
      name: source ? row.fc_attribute_name : row.attribute_name, data_type: row.attribute_data_type,
      key: {...ownKey(object), attribute_name: row.attribute_name}}));
    if (new Set(projected.map((row) => norm(row.name))).size !== projected.length) throw Error("Attribute SQL coordinates are ambiguous.");
    for (let offset = 0; offset < projected.length;) {
      let count = Math.min(50, projected.length - offset);
      let chunk, sql;
      do { chunk = projected.slice(offset, offset + count); sql = buildQuery(relation, chunk, filter); }
      while (sql.length > 100000 && --count > 0);
      if (!count) throw Error("Profiling query exceeds SQL limit.");
      queries.push({object: ownKey(object), source_tenant_code: object.source_tenant_code,
        source_system_codes: originSystems, batch_id: filter ? batch : null,
        attributes: chunk.map((row) => ({attribute_index: row.index, ...row.key})), sql});
      offset += count;
    }
  }
  return {queries, coverage};
}

module.exports = {buildQuery, planProfiling, fields, norm, key, ownKey, attributeKey, maskingKeys, quote,
  normalizedType, stringType, scalarType};
