#!/usr/bin/env node
"use strict";

const fs = require("node:fs");

const MAX_SQL_CHARACTERS = 100_000;
const MAX_BATCH_IDS = 1_000;
const MIN_BIGINT = -(1n << 63n);
const MAX_BIGINT = (1n << 63n) - 1n;
const RESULT_COLUMNS = [
  "validation_source_non_null_count",
  "validation_source_distinct_count",
  "validation_target_non_null_count",
  "validation_target_distinct_count",
  "validation_source_missing_target_count",
  "validation_unused_target_count",
  "validation_duplicate_target_key_count",
  "validation_result",
];

function fail(message) {
  process.stderr.write(`error: ${message}\n`);
  process.exit(2);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireExactKeys(value, expected, label) {
  if (!isObject(value)) {
    fail(`${label} must be an object`);
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    fail(`${label} has unexpected or missing fields`);
  }
}

function requireText(value, label, maximumLength) {
  if (
    typeof value !== "string" ||
    value.length < 1 ||
    value.length > maximumLength ||
    !/\S/u.test(value) ||
    value.includes("\0")
  ) {
    fail(`${label} must be a bounded nonblank string`);
  }
  return value;
}

function quoteIdentifier(value) {
  return `\`${value.replaceAll("`", "``")}\``;
}

function normalizedType(value) {
  return value.trim().replaceAll(/\s+/gu, " ").toUpperCase();
}

function comparableType(value, label) {
  const type = normalizedType(requireText(value, label, 100));
  if (
    /^(BOOLEAN|BYTE|TINYINT|SHORT|SMALLINT|INT|INTEGER|LONG|BIGINT|FLOAT|REAL|DOUBLE|DATE|TIMESTAMP(?:_NTZ|_LTZ)?|STRING)$/u.test(type) ||
    /^(?:VARCHAR|CHAR)\s*\(\s*[1-9]\d{0,5}\s*\)$/u.test(type)
  ) {
    return type;
  }
  const decimal = /^(?:DECIMAL|NUMERIC)\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)$/u.exec(type);
  if (decimal !== null) {
    const precision = Number(decimal[1]);
    const scale = Number(decimal[2]);
    if (precision >= 1 && precision <= 38 && scale >= 0 && scale <= precision) {
      return type;
    }
  }
  fail(`${label} must be a comparable scalar Databricks type`);
}

function batchBounds(dataType) {
  const type = normalizedType(dataType).replaceAll(" ", "");
  if (type === "BYTE" || type === "TINYINT") {
    return [-128n, 127n];
  }
  if (type === "SHORT" || type === "SMALLINT") {
    return [-32_768n, 32_767n];
  }
  if (type === "INT" || type === "INTEGER") {
    return [-2_147_483_648n, 2_147_483_647n];
  }
  if (type === "LONG" || type === "BIGINT") {
    return [MIN_BIGINT, MAX_BIGINT];
  }
  const decimal = /^DECIMAL\((\d+),0\)$/u.exec(type);
  if (decimal !== null) {
    const precision = Number(decimal[1]);
    if (!Number.isInteger(precision) || precision < 1 || precision > 38) {
      fail("batch.data_type has invalid decimal precision");
    }
    const magnitude = 10n ** BigInt(precision) - 1n;
    return [magnitude > MAX_BIGINT ? MIN_BIGINT : -magnitude, magnitude > MAX_BIGINT ? MAX_BIGINT : magnitude];
  }
  fail("batch.data_type must be an integral Databricks type or DECIMAL(p,0)");
}

function parseBatchId(value, label, minimum, maximum) {
  let text;
  if (typeof value === "number" && Number.isSafeInteger(value)) {
    text = String(value);
  } else if (typeof value === "string" && /^-?(0|[1-9]\d*)$/u.test(value)) {
    text = value;
  } else {
    fail(`${label} must be a decimal integer or decimal string`);
  }
  const parsed = BigInt(text);
  if (parsed < minimum || parsed > maximum) {
    fail(`${label} does not fit batch.data_type`);
  }
  return parsed;
}

function validateBatch(value, label) {
  if (value === null) {
    return null;
  }
  requireExactKeys(value, ["column", "data_type", "mode", "ids"], `${label}.batch`);
  requireText(value.column, `${label}.batch.column`, 400);
  requireText(value.data_type, `${label}.batch.data_type`, 100);
  if (value.mode !== "initial" && value.mode !== "incremental") {
    fail(`${label}.batch.mode must be initial or incremental`);
  }
  if (!Array.isArray(value.ids) || value.ids.length > MAX_BATCH_IDS) {
    fail(`${label}.batch.ids must contain at most ${MAX_BATCH_IDS} values`);
  }
  if (value.mode === "initial" && value.ids.length !== 1) {
    fail(`${label} initial batch mode requires exactly one ID`);
  }
  const [minimum, maximum] = batchBounds(value.data_type);
  const seen = new Set();
  const ids = value.ids.map((item, index) => {
    const parsed = parseBatchId(item, `${label}.batch.ids[${index}]`, minimum, maximum);
    const canonical = parsed.toString();
    if (seen.has(canonical)) {
      fail(`${label}.batch.ids must be unique`);
    }
    seen.add(canonical);
    return parsed;
  });
  ids.sort((left, right) => (left < right ? -1 : left > right ? 1 : 0));
  return { column: value.column, mode: value.mode, ids };
}

function validateEndpoint(value, label) {
  requireExactKeys(value, ["physical_key", "relation", "data_type", "batch"], label);
  requireExactKeys(
    value.physical_key,
    ["tenant_code", "system_code", "connection_code", "object_schema", "object_name", "attribute_name"],
    `${label}.physical_key`,
  );
  for (const field of ["tenant_code", "system_code", "connection_code"]) {
    requireText(value.physical_key[field], `${label}.physical_key.${field}`, 100);
  }
  for (const field of ["object_schema", "object_name", "attribute_name"]) {
    requireText(value.physical_key[field], `${label}.physical_key.${field}`, 400);
  }
  requireExactKeys(value.relation, ["catalog", "schema", "table"], `${label}.relation`);
  requireText(value.relation.catalog, `${label}.relation.catalog`, 255);
  requireText(value.relation.schema, `${label}.relation.schema`, 400);
  requireText(value.relation.table, `${label}.relation.table`, 400);
  if (
    value.relation.schema !== value.physical_key.object_schema ||
    value.relation.table !== value.physical_key.object_name
  ) {
    fail(`${label} relation schema/table must exactly match its registered physical Object key`);
  }
  return {
    physical_key: value.physical_key,
    relation: value.relation,
    data_type: comparableType(value.data_type, `${label}.data_type`),
    batch: validateBatch(value.batch, label),
  };
}

function canonicalKey(key) {
  return [
    key.tenant_code,
    key.system_code,
    key.connection_code,
    key.object_schema,
    key.object_name,
    key.attribute_name,
  ].map((part) => part.trim().toLowerCase()).join("\0");
}

function validateSpec(spec) {
  requireExactKeys(
    spec,
    ["connection_id", "environment_code", "relationship_kind", "comparison_type", "from", "to"],
    "spec",
  );
  if (!Number.isSafeInteger(spec.connection_id) || spec.connection_id < 1) {
    fail("connection_id must be a positive integer");
  }
  requireText(spec.environment_code, "environment_code", 100);
  if (spec.environment_code !== spec.environment_code.trim()) {
    fail("environment_code must not have surrounding whitespace");
  }
  requireText(spec.relationship_kind, "relationship_kind", 100);
  const from = validateEndpoint(spec.from, "from");
  const to = validateEndpoint(spec.to, "to");
  if (canonicalKey(from.physical_key) === canonicalKey(to.physical_key)) {
    fail("from and to Attributes must be different");
  }
  if (from.physical_key.tenant_code.trim().toLowerCase() !== to.physical_key.tenant_code.trim().toLowerCase()) {
    fail("from and to Attributes must belong to the same Model Tenant");
  }
  let comparisonType = null;
  if (spec.comparison_type === null) {
    if (from.data_type !== to.data_type) {
      fail("unlike endpoint data types require an explicit comparison_type");
    }
  } else {
    comparisonType = comparableType(spec.comparison_type, "comparison_type");
  }
  return { from, to, comparisonType };
}

function relationSql(relation) {
  return [relation.catalog, relation.schema, relation.table].map(quoteIdentifier).join(".");
}

function valueExpression(endpoint, comparisonType) {
  const identifier = quoteIdentifier(endpoint.physical_key.attribute_name);
  return comparisonType === null ? identifier : `CAST(${identifier} AS ${comparisonType})`;
}

function endpointSelect(endpoint, comparisonType) {
  const identifier = quoteIdentifier(endpoint.physical_key.attribute_name);
  const predicates = [`${identifier} IS NOT NULL`];
  if (endpoint.batch !== null) {
    const batchIdentifier = quoteIdentifier(endpoint.batch.column);
    if (endpoint.batch.mode === "initial") {
      predicates.push(`${batchIdentifier} = ${endpoint.batch.ids[0]}`);
    } else {
      predicates.push(`${batchIdentifier} IN (${endpoint.batch.ids.map(String).join(", ")})`);
    }
  }
  return (
    `SELECT ${valueExpression(endpoint, comparisonType)} AS comparison_value\n` +
    `  FROM ${relationSql(endpoint.relation)}\n` +
    ` WHERE ${predicates.join("\n   AND ")}`
  );
}

function buildSql(from, to, comparisonType) {
  return (
    "WITH source_values AS (\n" +
    `${endpointSelect(from, comparisonType)}\n` +
    "),\n" +
    "target_values AS (\n" +
    `${endpointSelect(to, comparisonType)}\n` +
    "),\n" +
    "source_value_counts AS (\n" +
    "SELECT comparison_value, COUNT(*) AS value_count\n" +
    "  FROM source_values\n" +
    " GROUP BY comparison_value\n" +
    "),\n" +
    "target_value_counts AS (\n" +
    "SELECT comparison_value, COUNT(*) AS value_count\n" +
    "  FROM target_values\n" +
    " GROUP BY comparison_value\n" +
    "),\n" +
    "source_stats AS (\n" +
    "SELECT CAST(COALESCE(SUM(value_count), 0) AS BIGINT) AS non_null_count,\n" +
    "       CAST(COUNT(*) AS BIGINT) AS distinct_count\n" +
    "  FROM source_value_counts\n" +
    "),\n" +
    "target_stats AS (\n" +
    "SELECT CAST(COALESCE(SUM(value_count), 0) AS BIGINT) AS non_null_count,\n" +
    "       CAST(COUNT(*) AS BIGINT) AS distinct_count,\n" +
    "       CAST(COALESCE(SUM(value_count - 1), 0) AS BIGINT) AS duplicate_count\n" +
    "  FROM target_value_counts\n" +
    "),\n" +
    "missing_source AS (\n" +
    "SELECT CAST(COUNT(*) AS BIGINT) AS value_count\n" +
    "  FROM source_value_counts AS source\n" +
    "  LEFT ANTI JOIN target_value_counts AS target\n" +
    "    ON source.comparison_value = target.comparison_value\n" +
    "),\n" +
    "unused_target AS (\n" +
    "SELECT CAST(COUNT(*) AS BIGINT) AS value_count\n" +
    "  FROM target_value_counts AS target\n" +
    "  LEFT ANTI JOIN source_value_counts AS source\n" +
    "    ON target.comparison_value = source.comparison_value\n" +
    ")\n" +
    "SELECT source_stats.non_null_count AS validation_source_non_null_count,\n" +
    "       source_stats.distinct_count AS validation_source_distinct_count,\n" +
    "       target_stats.non_null_count AS validation_target_non_null_count,\n" +
    "       target_stats.distinct_count AS validation_target_distinct_count,\n" +
    "       missing_source.value_count AS validation_source_missing_target_count,\n" +
    "       unused_target.value_count AS validation_unused_target_count,\n" +
    "       target_stats.duplicate_count AS validation_duplicate_target_key_count,\n" +
    "       CASE\n" +
    "         WHEN source_stats.non_null_count = 0 OR target_stats.non_null_count = 0\n" +
    "           THEN 'inconclusive'\n" +
    "         WHEN missing_source.value_count = 0 AND target_stats.duplicate_count = 0\n" +
    "           THEN 'supported'\n" +
    "         ELSE 'unsupported'\n" +
    "       END AS validation_result\n" +
    "  FROM source_stats\n" +
    " CROSS JOIN target_stats\n" +
    " CROSS JOIN missing_source\n" +
    " CROSS JOIN unused_target"
  );
}

function analysisIdentity(spec) {
  const identity = {};
  for (const prefix of ["from", "to"]) {
    for (const [field, value] of Object.entries(spec[prefix].physical_key)) {
      identity[`${prefix}_${field}`] = value;
    }
  }
  identity.relationship_kind = spec.relationship_kind;
  return identity;
}

function buildPlan(spec) {
  const validated = validateSpec(spec);
  const batches = {
    from: validated.from.batch === null ? null : validated.from.batch.mode,
    to: validated.to.batch === null ? null : validated.to.batch.mode,
  };
  const batchValueCounts = {
    from: validated.from.batch === null ? 0 : validated.from.batch.ids.length,
    to: validated.to.batch === null ? 0 : validated.to.batch.ids.length,
  };
  const noOp = [validated.from.batch, validated.to.batch].some(
    (batch) => batch !== null && batch.mode === "incremental" && batch.ids.length === 0,
  );
  const sql = noOp ? null : buildSql(validated.from, validated.to, validated.comparisonType);
  if (sql !== null && sql.length > MAX_SQL_CHARACTERS) {
    fail("generated SQL exceeds the tool character limit");
  }
  return {
    schema_version: "1.0",
    validation_policy_version: "1.0.0",
    connection_id: spec.connection_id,
    environment_code: spec.environment_code,
    analysis_identity: analysisIdentity(spec),
    comparison_type: validated.comparisonType,
    batch_modes: batches,
    batch_value_counts: batchValueCounts,
    no_op: noOp,
    result_columns: RESULT_COLUMNS,
    sql,
  };
}

function main() {
  const argumentsList = process.argv.slice(2);
  if (argumentsList.length !== 2 || argumentsList[0] !== "--spec") {
    fail("usage: build-relationship-sql.js --spec <json-file>");
  }
  let spec;
  try {
    spec = JSON.parse(fs.readFileSync(argumentsList[1], "utf8"));
  } catch (_error) {
    fail("could not read a valid JSON spec");
  }
  process.stdout.write(`${JSON.stringify(buildPlan(spec), null, 2)}\n`);
}

main();
