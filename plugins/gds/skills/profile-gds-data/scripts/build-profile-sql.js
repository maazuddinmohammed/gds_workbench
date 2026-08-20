#!/usr/bin/env node
"use strict";

const fs = require("node:fs");

const MAX_ATTRIBUTES_PER_QUERY = 50;
const MAX_SQL_CHARACTERS = 100_000;
const MAX_ATTRIBUTES = 2_000;
const MAX_BATCH_IDS = 1_000;
const MIN_BIGINT = -(1n << 63n);
const MAX_BIGINT = (1n << 63n) - 1n;

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

function quoteText(value) {
  return `'${value.replaceAll("'", "''")}'`;
}

function normalizedType(value) {
  return value.trim().replaceAll(/\s+/gu, " ").toUpperCase();
}

function metricSupport(dataType) {
  const type = normalizedType(dataType);
  const string = /^(STRING|VARCHAR(?:\s*\(\s*\d+\s*\))?|CHAR(?:\s*\(\s*\d+\s*\))?)$/u.test(
    type,
  );
  const distinct =
    string ||
    /^(BOOLEAN|BYTE|TINYINT|SHORT|SMALLINT|INT|INTEGER|LONG|BIGINT|FLOAT|REAL|DOUBLE|DATE|TIMESTAMP(?:_NTZ|_LTZ)?|DECIMAL\s*\(\s*\d+\s*,\s*\d+\s*\)|NUMERIC\s*\(\s*\d+\s*,\s*\d+\s*\))$/u.test(
      type,
    );
  return { string, distinct };
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

function percentage(numerator, denominator) {
  return (
    `CAST(CASE WHEN ${denominator} = 0 THEN 0.0 ` +
    `ELSE ROUND(CAST(100 AS DOUBLE) * (${numerator}) / ${denominator}, 4) ` +
    "END AS DOUBLE)"
  );
}

function buildQuery(spec, columns, batch) {
  const relation = [spec.relation.catalog, spec.relation.schema, spec.relation.table]
    .map(quoteIdentifier)
    .join(".");
  const selected = columns.map((column) => `       ${quoteIdentifier(column.name)}`).join(",\n");
  let predicate = "";
  if (batch !== null) {
    if (batch.ids.length === 0) {
      predicate = "\n WHERE FALSE";
    } else if (batch.mode === "initial") {
      predicate = `\n WHERE ${quoteIdentifier(batch.column)} = ${batch.ids[0]}`;
    } else {
      predicate =
        `\n WHERE ${quoteIdentifier(batch.column)} IN (` +
        `${batch.ids.map(String).join(", ")})`;
    }
  }

  const aggregates = ["       COUNT(*) AS row_count"];
  for (const [index, column] of columns.entries()) {
    const identifier = quoteIdentifier(column.name);
    const prefix = `p${index}`;
    const support = metricSupport(column.data_type);
    aggregates.push(`       COUNT(${identifier}) AS ${prefix}_non_null_count`);
    if (support.distinct) {
      aggregates.push(`       COUNT(DISTINCT ${identifier}) AS ${prefix}_distinct_count`);
    }
    if (support.string) {
      aggregates.push(
        `       CAST(COALESCE(SUM(CASE WHEN ${identifier} IS NOT NULL ` +
          `AND TRIM(${identifier}) = '' THEN 1 ELSE 0 END), 0) AS BIGINT) ` +
          `AS ${prefix}_blank_count`,
      );
      aggregates.push(
        `       MIN(CASE WHEN ${identifier} IS NOT NULL THEN LENGTH(${identifier}) END) ` +
          `AS ${prefix}_min_data_length`,
      );
      aggregates.push(
        `       MAX(CASE WHEN ${identifier} IS NOT NULL THEN LENGTH(${identifier}) END) ` +
          `AS ${prefix}_max_data_length`,
      );
      aggregates.push(
        `       AVG(CASE WHEN ${identifier} IS NOT NULL ` +
          `THEN CAST(LENGTH(${identifier}) AS DOUBLE) END) AS ${prefix}_avg_data_length`,
      );
    }
  }

  const key = spec.physical_key;
  const projections = columns.map((column, index) => {
    const prefix = `p${index}`;
    const support = metricSupport(column.data_type);
    const nonNull = `${prefix}_non_null_count`;
    const nullCount = `(row_count - ${nonNull})`;
    const distinct = support.distinct ? `${prefix}_distinct_count` : null;
    const blank = support.string ? `${prefix}_blank_count` : null;
    const lines = [
      `       ${quoteText(key.tenant_code)} AS tenant_code`,
      `       ${quoteText(key.system_code)} AS system_code`,
      `       ${quoteText(key.connection_code)} AS connection_code`,
      `       ${quoteText(key.object_schema)} AS object_schema`,
      `       ${quoteText(key.object_name)} AS object_name`,
      `       ${quoteText(column.name)} AS attribute_name`,
      "       CAST(row_count AS BIGINT) AS row_count",
      `       CAST(${nonNull} AS BIGINT) AS non_null_count`,
      `       CAST(${nullCount} AS BIGINT) AS null_count`,
      blank === null
        ? "       CAST(NULL AS BIGINT) AS blank_count"
        : `       CAST(${blank} AS BIGINT) AS blank_count`,
      distinct === null
        ? "       CAST(NULL AS BIGINT) AS distinct_count"
        : `       CAST(${distinct} AS BIGINT) AS distinct_count`,
      support.string
        ? `       CAST(${prefix}_min_data_length AS INT) AS min_data_length`
        : "       CAST(NULL AS INT) AS min_data_length",
      support.string
        ? `       CAST(${prefix}_max_data_length AS INT) AS max_data_length`
        : "       CAST(NULL AS INT) AS max_data_length",
      support.string
        ? `       CAST(ROUND(${prefix}_avg_data_length, 6) AS DOUBLE) AS avg_data_length`
        : "       CAST(NULL AS DOUBLE) AS avg_data_length",
      `       ${percentage(nonNull, "row_count")} AS percent_populated`,
      distinct === null
        ? "       CAST(NULL AS DOUBLE) AS percent_duplicates"
        : `       ${percentage(`(${nonNull} - ${distinct})`, nonNull)} AS percent_duplicates`,
      `       ${percentage(nullCount, "row_count")} AS percent_null`,
      blank === null
        ? "       CAST(NULL AS DOUBLE) AS percent_blank"
        : `       ${percentage(blank, nonNull)} AS percent_blank`,
      distinct === null
        ? "       CAST(NULL AS DOUBLE) AS percent_distinct"
        : `       ${percentage(distinct, nonNull)} AS percent_distinct`,
    ];
    return `SELECT\n${lines.join(",\n")}\n  FROM summary`;
  });

  return (
    "WITH scoped AS (\n" +
    "SELECT\n" +
    `${selected}\n` +
    `  FROM ${relation}${predicate}\n` +
    "),\nsummary AS (\n" +
    "SELECT\n" +
    `${aggregates.join(",\n")}\n` +
    "  FROM scoped\n" +
    ")\n" +
    projections.join("\nUNION ALL\n")
  );
}

function validateSpec(spec) {
  requireExactKeys(
    spec,
    ["connection_id", "environment_code", "physical_key", "relation", "columns", "batch"],
    "spec",
  );
  if (!Number.isSafeInteger(spec.connection_id) || spec.connection_id < 1) {
    fail("connection_id must be a positive integer");
  }
  requireText(spec.environment_code, "environment_code", 100);
  if (spec.environment_code !== spec.environment_code.trim()) {
    fail("environment_code must not have surrounding whitespace");
  }

  requireExactKeys(
    spec.physical_key,
    ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"],
    "physical_key",
  );
  for (const field of ["tenant_code", "system_code", "connection_code"]) {
    requireText(spec.physical_key[field], `physical_key.${field}`, 100);
  }
  for (const field of ["object_schema", "object_name"]) {
    requireText(spec.physical_key[field], `physical_key.${field}`, 400);
  }

  requireExactKeys(spec.relation, ["catalog", "schema", "table"], "relation");
  requireText(spec.relation.catalog, "relation.catalog", 255);
  requireText(spec.relation.schema, "relation.schema", 400);
  requireText(spec.relation.table, "relation.table", 400);

  if (!Array.isArray(spec.columns) || spec.columns.length < 1 || spec.columns.length > MAX_ATTRIBUTES) {
    fail(`columns must contain 1-${MAX_ATTRIBUTES} Attributes`);
  }
  const seenColumns = new Set();
  for (const [index, column] of spec.columns.entries()) {
    requireExactKeys(column, ["name", "data_type"], `columns[${index}]`);
    requireText(column.name, `columns[${index}].name`, 400);
    requireText(column.data_type, `columns[${index}].data_type`, 100);
    const canonical = column.name.toLowerCase();
    if (seenColumns.has(canonical)) {
      fail("columns must have unique case-insensitive names");
    }
    seenColumns.add(canonical);
  }

  if (spec.batch === null) {
    return null;
  }
  requireExactKeys(spec.batch, ["column", "data_type", "mode", "ids"], "batch");
  requireText(spec.batch.column, "batch.column", 400);
  requireText(spec.batch.data_type, "batch.data_type", 100);
  if (spec.batch.mode !== "initial" && spec.batch.mode !== "incremental") {
    fail("batch.mode must be initial or incremental");
  }
  if (!Array.isArray(spec.batch.ids) || spec.batch.ids.length > MAX_BATCH_IDS) {
    fail(`batch.ids must contain at most ${MAX_BATCH_IDS} values`);
  }
  if (spec.batch.mode === "initial" && spec.batch.ids.length !== 1) {
    fail("initial batch mode requires exactly one ID");
  }
  if (seenColumns.has(spec.batch.column.toLowerCase())) {
    fail("the batch Attribute must not be included in columns");
  }

  const [minimum, maximum] = batchBounds(spec.batch.data_type);
  const seenIds = new Set();
  const ids = spec.batch.ids.map((value, index) => {
    const parsed = parseBatchId(value, `batch.ids[${index}]`, minimum, maximum);
    const canonical = parsed.toString();
    if (seenIds.has(canonical)) {
      fail("batch.ids must be unique");
    }
    seenIds.add(canonical);
    return parsed;
  });
  ids.sort((left, right) => (left < right ? -1 : left > right ? 1 : 0));
  return {
    column: spec.batch.column,
    data_type: spec.batch.data_type,
    mode: spec.batch.mode,
    ids,
  };
}

function buildPlan(spec) {
  const batch = validateSpec(spec);
  const chunks = [];
  let offset = 0;
  while (offset < spec.columns.length) {
    let size = Math.min(MAX_ATTRIBUTES_PER_QUERY, spec.columns.length - offset);
    let columns;
    let sql;
    while (size > 0) {
      columns = spec.columns.slice(offset, offset + size);
      sql = buildQuery(spec, columns, batch);
      if (sql.length <= MAX_SQL_CHARACTERS) {
        break;
      }
      size -= 1;
    }
    if (size < 1 || columns === undefined || sql === undefined) {
      fail("one Attribute produces SQL above the tool character limit");
    }
    chunks.push({
      attribute_names: columns.map((column) => column.name),
      sql,
    });
    offset += size;
  }

  return {
    schema_version: "1.0",
    connection_id: spec.connection_id,
    environment_code: spec.environment_code,
    batch_mode: batch === null ? null : batch.mode,
    batch_value_count: batch === null ? 0 : batch.ids.length,
    profile_record_count: spec.columns.length,
    chunk_count: chunks.length,
    chunks,
  };
}

function main() {
  const argumentsList = process.argv.slice(2);
  if (argumentsList.length !== 2 || argumentsList[0] !== "--spec") {
    fail("usage: build-profile-sql.js --spec <json-file>");
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
