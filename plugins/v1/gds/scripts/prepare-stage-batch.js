#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const MAX_SOURCE_BYTES = 16 * 1024 * 1024;
const MAX_CHUNK_BYTES = 450 * 1024;
const MAX_CHUNKS = 64;
const MAX_RECORDS = { metadata: 50000, model: 20000 };
const DATASETS = {
  metadata: new Set([
    "source_object", "source_attribute", "bronze_object", "bronze_attribute",
    "silver_object", "silver_attribute", "gold_object", "gold_attribute",
    "ingestion_object_mapping", "ingestion_attribute_mapping", "copy_group",
    "member_group", "copy_group_control", "copy", "process_group", "process",
  ]),
  model: new Set([
    "model_details", "model_scope", "profiling_profile", "analysis_result",
    "modeling_assertion_document", "modeling_assertion_record", "conceptual_object",
    "conceptual_relationship", "logical_submodel", "logical_entity",
    "logical_attribute", "logical_relationship", "dimensional_submodel",
    "dimensional_entity", "dimensional_attribute", "dimensional_relationship",
    "mapping_dependency", "mapping_object", "mapping_attribute",
  ]),
};

function fail(message) {
  process.stderr.write(`ok=false\nerror=${message}\n`);
  process.exit(2);
}

function argumentsByName(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    const value = argv[index + 1];
    if (!name || !name.startsWith("--") || value === undefined || value.startsWith("--")) {
      fail("Expected --kind, --dataset-file, --dataset, and --output arguments.");
    }
    if (Object.hasOwn(parsed, name)) fail(`Duplicate argument: ${name}.`);
    parsed[name] = value;
  }
  return parsed;
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(stableValue(value));
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

const options = argumentsByName(process.argv.slice(2));
const kind = options["--kind"];
const dataset = options["--dataset"];
const datasetFile = options["--dataset-file"];
const outputDirectory = options["--output"];

if (!Object.hasOwn(DATASETS, kind)) fail("Kind must be metadata or model.");
if (!DATASETS[kind].has(dataset)) fail("Dataset is not eligible for this Change Set kind.");
if (!datasetFile || !outputDirectory) fail("Dataset file and output directory are required.");

let sourceStat;
try {
  sourceStat = fs.lstatSync(datasetFile);
} catch {
  fail("Dataset file was not found.");
}
if (!sourceStat.isFile() || sourceStat.isSymbolicLink()) fail("Dataset path must be a regular file.");
if (sourceStat.size < 2 || sourceStat.size > MAX_SOURCE_BYTES) {
  fail("Dataset file must be between 2 bytes and 16 MiB.");
}

let sourceBytes;
let records;
try {
  sourceBytes = fs.readFileSync(datasetFile);
  records = JSON.parse(sourceBytes.toString("utf8"));
} catch {
  fail("Dataset file must contain valid UTF-8 JSON.");
}
if (!Array.isArray(records) || records.length < 1 || records.length > MAX_RECORDS[kind]) {
  fail(`Dataset must contain 1-${MAX_RECORDS[kind]} records.`);
}
if (records.some((record) => record === null || Array.isArray(record) || typeof record !== "object")) {
  fail("Every dataset record must be a JSON object.");
}

const chunks = [];
let current = [];
for (const record of records) {
  const candidate = [...current, record];
  const candidateBytes = Buffer.byteLength(canonicalJson(candidate), "utf8");
  if (candidateBytes <= MAX_CHUNK_BYTES) {
    current = candidate;
    continue;
  }
  if (current.length === 0) fail("One record exceeds the 450 KiB chunk limit.");
  chunks.push(current);
  current = [record];
  if (Buffer.byteLength(canonicalJson(current), "utf8") > MAX_CHUNK_BYTES) {
    fail("One record exceeds the 450 KiB chunk limit.");
  }
}
if (current.length > 0) chunks.push(current);
if (chunks.length > MAX_CHUNKS) fail("Dataset requires more than 64 Stage chunks.");

const outputParent = path.dirname(path.resolve(outputDirectory));
if (!fs.existsSync(outputParent) || !fs.statSync(outputParent).isDirectory()) {
  fail("Output parent directory does not exist.");
}
if (fs.existsSync(outputDirectory)) fail("Output directory already exists.");
fs.mkdirSync(outputDirectory);

const chunkManifest = [];
for (let offset = 0; offset < chunks.length; offset += 1) {
  const index = offset + 1;
  const recordsInChunk = chunks[offset];
  const canonical = canonicalJson(recordsInChunk);
  const file = `chunk-${String(index).padStart(4, "0")}.json`;
  fs.writeFileSync(path.join(outputDirectory, file), `${JSON.stringify(recordsInChunk)}\n`, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600,
  });
  chunkManifest.push({
    chunk_index: index,
    file,
    record_count: recordsInChunk.length,
    bytes: Buffer.byteLength(canonical, "utf8"),
    chunk_sha256: sha256(canonical),
  });
}

const batchSha256 = sha256(chunkManifest.map((chunk) => chunk.chunk_sha256).join(""));
const manifest = {
  format_version: "1.0",
  kind,
  dataset,
  source_file: path.basename(datasetFile),
  source_sha256: sha256(sourceBytes),
  record_count: records.length,
  chunk_count: chunks.length,
  max_chunk_bytes: MAX_CHUNK_BYTES,
  batch_sha256: batchSha256,
  chunks: chunkManifest,
};
fs.writeFileSync(path.join(outputDirectory, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, {
  encoding: "utf8",
  flag: "wx",
  mode: 0o600,
});

process.stdout.write(
  [
    "ok=true",
    `kind=${kind}`,
    `dataset=${dataset}`,
    `record_count=${records.length}`,
    `chunk_count=${chunks.length}`,
    `batch_sha256=${batchSha256}`,
    `output=${path.resolve(outputDirectory)}`,
  ].join("\n") + "\n",
);
