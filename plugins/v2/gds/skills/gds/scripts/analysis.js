"use strict";

// Planning only: no connection, execution, sample rows, or inferred identity.
const {fields, norm, key, ownKey, attributeKey, maskingKeys, quote, normalizedType, stringType, scalarType} = require("./profiling.js");
const active = (row) => row.is_active !== false;

function exactFields(value, names, label) {
  if (!value || Array.isArray(value) || typeof value !== "object" ||
      Object.keys(value).length !== names.length || names.some((name) => !Object.hasOwn(value, name))) {
    throw Error(`${label} requires only its documented fields.`);
  }
}

function resolveEndpoint(metadata, scope, endpoint, masked) {
  exactFields(endpoint, ["object", "columns"], "Analysis endpoint");
  exactFields(endpoint.object, fields, "Object key");
  if (fields.some((field) => typeof endpoint.object[field] !== "string" || !endpoint.object[field].trim())) {
    throw Error("Object key requires registered nonblank names.");
  }
  const names = endpoint.columns;
  if (!Array.isArray(names) || names.length < 1 || names.length > 8 ||
      names.some((name) => typeof name !== "string" || !name.trim()) ||
      new Set(names.map(norm)).size !== names.length) throw Error("Select 1–8 distinct registered Attributes.");
  const identity = key(endpoint.object);
  if (!scope.some((row) => active(row) && key(row) === identity)) throw Error("Object is outside active Model Input Scope.");
  const objects = [...(metadata.source_object ?? []), ...(metadata.bronze_object ?? [])].filter(active);
  const matches = objects.filter((row) => key(row) === identity);
  if (matches.length !== 1) throw Error("Object is missing or ambiguous in Source/Bronze Metadata.");
  const object = matches[0], source = norm(object.zone_code) === "source";
  if (!source && norm(object.zone_code) !== "bronze") throw Error("Analysis requires Source or Bronze Objects.");
  const connections = (metadata.connection ?? []).filter((row) => active(row) &&
    fields.slice(0, 3).every((field) => norm(row[field]) === norm(object[field])));
  const tenants = (metadata.tenant ?? []).filter((row) => active(row) && norm(row.tenant_code) === norm(object.tenant_code));
  if (connections.length !== 1 || tenants.length !== 1) throw Error("Object placement is not uniquely active in Metadata.");
  if (source && connections[0].has_foreign_catalog === false) throw Error("Source Object requires a registered foreign catalog.");
  const relation = [source ? connections[0].foreign_catalog : tenants[0].tenant_catalog,
    source ? object.fc_object_schema : object.object_schema,
    source ? object.fc_object_name : object.object_name].map(quote).join(".");
  const allAttributes = [...(metadata.source_attribute ?? []), ...(metadata.bronze_attribute ?? [])];
  const attributes = names.map((name) => {
    const candidates = allAttributes.filter((row) => active(row) && key(row) === identity && norm(row.attribute_name) === norm(name));
    if (candidates.length !== 1) throw Error("Attribute is missing or ambiguous in active Metadata.");
    const attribute = candidates[0];
    if (masked.has(attributeKey(attribute))) {
      throw Error("Masked Attributes cannot be used in Analysis probes.");
    }
    const type = normalizedType(String(attribute.attribute_data_type ?? ""));
    if (!stringType.test(type) && !scalarType.test(type)) throw Error("Analysis probes require scalar registered Attribute types.");
    return {name: attribute.attribute_name, sql: quote(source ? attribute.fc_attribute_name : attribute.attribute_name), type};
  });
  if (new Set(attributes.map((attribute) => norm(attribute.sql))).size !== attributes.length) {
    throw Error("Attribute SQL coordinates are ambiguous.");
  }
  const origins = source ? [object] : (metadata.ingestion_object_mapping ?? []).filter((row) => active(row) && key(row, "target_") === identity)
    .flatMap((mapping) => objects.filter((row) => key(row) === key(mapping, "source_") && norm(row.source_tenant_code) === norm(object.source_tenant_code)));
  return {object: ownKey(object), source_tenant_code: object.source_tenant_code,
    source_system_codes: [...new Set(origins.map((row) => norm(row.system_code)))],
    columns: attributes.map((row) => row.name), attributes, relation};
}

function buildSql(kind, endpoints, determinantCount) {
  const ctes = [], metrics = [];
  const metric = (name, sql) => { metrics.push({name, sql: `CAST((${sql}) AS BIGINT) AS ${name}`}); };
  const scoped = (name, endpoint) => {
    const columns = endpoint.attributes.map((row, index) => `c${index}`);
    ctes.push(`${name} AS (\nSELECT ${endpoint.attributes.map((row, index) => `${row.sql} AS ${columns[index]}`).join(", ")}\n  FROM ${endpoint.relation}\n)`);
    return columns;
  };
  const complete = (columns) => columns.map((name) => `${name} IS NOT NULL`).join(" AND ");
  const nulls = (columns) => columns.map((name) => `${name} IS NULL`).join(" OR ");
  const counts = (name, source, columns) => ctes.push(`${name} AS (\nSELECT ${columns.join(", ")}, COUNT(*) AS key_rows\n  FROM ${source}\n WHERE ${complete(columns)}\n GROUP BY ${columns.join(", ")}\n)`);
  if (kind === "key") {
    const columns = scoped("scoped", endpoints[0]);
    counts("key_counts", "scoped", columns);
    metric("row_count", "SELECT COUNT(*) FROM scoped");
    metric("null_key_row_count", `SELECT COUNT(*) FROM scoped WHERE ${nulls(columns)}`);
    metric("distinct_complete_key_count", "SELECT COUNT(*) FROM key_counts");
    metric("duplicate_complete_key_row_count", "SELECT COALESCE(SUM(key_rows - 1), 0) FROM key_counts");
  } else if (kind === "dependency") {
    const columns = scoped("scoped", endpoints[0]), determinants = columns.slice(0, determinantCount);
    ctes.push(`dependent_tuples AS (\nSELECT ${columns.join(", ")}\n  FROM scoped\n WHERE ${complete(determinants)}\n GROUP BY ${columns.join(", ")}\n)`);
    ctes.push(`determinant_variants AS (\nSELECT ${determinants.join(", ")}, COUNT(*) AS dependent_tuple_count\n  FROM dependent_tuples\n GROUP BY ${determinants.join(", ")}\n)`);
    metric("row_count", "SELECT COUNT(*) FROM scoped");
    metric("null_determinant_row_count", `SELECT COUNT(*) FROM scoped WHERE ${nulls(determinants)}`);
    metric("complete_determinant_group_count", "SELECT COUNT(*) FROM determinant_variants");
    metric("conflicting_determinant_group_count", "SELECT COUNT(*) FROM determinant_variants WHERE dependent_tuple_count > 1");
  } else {
    const columns = scoped("source_rows", endpoints[0]);
    scoped("target_rows", endpoints[1]);
    counts("source_counts", "source_rows", columns);
    counts("target_counts", "target_rows", columns);
    const equality = columns.map((name) => `s.${name} = t.${name}`).join(" AND ");
    metric("validation_source_non_null_count", "SELECT COALESCE(SUM(key_rows), 0) FROM source_counts");
    metric("validation_source_distinct_count", "SELECT COUNT(*) FROM source_counts");
    metric("validation_target_non_null_count", "SELECT COALESCE(SUM(key_rows), 0) FROM target_counts");
    metric("validation_target_distinct_count", "SELECT COUNT(*) FROM target_counts");
    metric("validation_source_missing_target_count", `SELECT COUNT(*) FROM source_counts s WHERE NOT EXISTS (SELECT 1 FROM target_counts t WHERE ${equality})`);
    metric("validation_unused_target_count", `SELECT COUNT(*) FROM target_counts t WHERE NOT EXISTS (SELECT 1 FROM source_counts s WHERE ${equality})`);
    metric("validation_duplicate_target_key_count", "SELECT COALESCE(SUM(key_rows - 1), 0) FROM target_counts");
    metric("source_null_key_row_count", `SELECT COUNT(*) FROM source_rows WHERE ${nulls(columns)}`);
    metric("target_null_key_row_count", `SELECT COUNT(*) FROM target_rows WHERE ${nulls(columns)}`);
  }
  const names = metrics.map((metric) => metric.name);
  let sql = `WITH ${ctes.join(",\n")}\n`;
  const summary = `SELECT\n       ${metrics.map((metric) => metric.sql).join(",\n       ")}`;
  if (kind === "join") {
    sql += `, summary AS (\n${summary}\n)\nSELECT ${names.join(", ")},\n       CASE WHEN validation_source_non_null_count = 0 OR validation_target_non_null_count = 0 THEN 'inconclusive'\n            WHEN validation_source_missing_target_count = 0 AND validation_duplicate_target_key_count = 0 THEN 'supported'\n            ELSE 'unsupported' END AS validation_result\n  FROM summary`;
    names.push("validation_result");
  } else sql += summary;
  if (sql.length > 100000) throw Error("Analysis query exceeds SQL limit.");
  return {sql, result_columns: names};
}

function planAnalysis(metadata, scope, plan) {
  exactFields(plan, ["scope", "probes"], "Analysis plan");
  if (plan.scope !== "all_rows") throw Error("Analysis scope must explicitly be all_rows.");
  if (!Array.isArray(plan.probes) || plan.probes.length < 1 || plan.probes.length > 50) throw Error("Select 1–50 Analysis probes.");
  const ids = new Set(), masked = maskingKeys(metadata);
  return plan.probes.map((probe) => {
    const kind = probe?.kind;
    const names = kind === "key" ? ["id", "kind", "object", "columns"]
      : kind === "dependency" ? ["id", "kind", "object", "determinants", "dependents"]
      : kind === "join" ? ["id", "kind", "from", "to"] : null;
    if (!names) throw Error("Probe kind must be key, dependency, or join.");
    exactFields(probe, names, "Analysis probe");
    if (typeof probe.id !== "string" || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(probe.id) || ids.has(probe.id)) throw Error("Probe IDs must be unique bounded identifiers.");
    ids.add(probe.id);
    let endpoints, determinantCount = 0;
    if (kind === "dependency") {
      // Resolve each side independently so an empty list and determinant overlap fail.
      const determinants = resolveEndpoint(metadata, scope, {object: probe.object, columns: probe.determinants}, masked);
      const dependents = resolveEndpoint(metadata, scope, {object: probe.object, columns: probe.dependents}, masked);
      determinantCount = determinants.columns.length;
      const columns = [...determinants.columns, ...dependents.columns];
      if (new Set(columns.map(norm)).size !== columns.length) throw Error("Determinants and dependents must be different Attributes.");
      endpoints = [{...determinants, columns, attributes: [...determinants.attributes, ...dependents.attributes]}];
    } else if (kind === "join") {
      endpoints = [resolveEndpoint(metadata, scope, probe.from, masked), resolveEndpoint(metadata, scope, probe.to, masked)];
      if (endpoints[0].columns.length !== endpoints[1].columns.length || endpoints[0].attributes.some((row, index) => row.type !== endpoints[1].attributes[index].type)) {
        throw Error("Join requires equal-length Attribute lists with matching registered types; casts are not inferred.");
      }
      if (key(endpoints[0].object) === key(endpoints[1].object) && endpoints[0].columns.every((name, index) => norm(name) === norm(endpoints[1].columns[index]))) throw Error("Join endpoints must differ.");
    } else endpoints = [resolveEndpoint(metadata, scope, {object: probe.object, columns: probe.columns}, masked)];
    const interpretation = kind === "key"
      ? "A nonempty result with zero null-key rows and duplicate complete-key rows supports observed uniqueness only; confirm business identity and lifecycle."
      : kind === "dependency"
        ? "Conflicting determinant groups have multiple distinct dependent tuples. Null determinants are counted as rows and excluded; null dependents count as tuple values. Zero conflicts on empty evidence proves nothing."
        : "Supported means nonempty complete keys, no missing source keys, and unique target keys. Null-key rows are excluded and reported separately. Matching values do not prove shared business identity or future cardinality.";
    return {id: probe.id, kind, scope: "all_rows", execution_state: "not_run", scan_cost: "unknown", max_result_rows: 1,
      endpoints: endpoints.map(({attributes, relation, ...endpoint}) => endpoint),
      ...(kind === "dependency" ? {determinant_count: determinantCount} : {}),
      interpretation, ...buildSql(kind, endpoints, determinantCount)};
  });
}

module.exports = {planAnalysis};
