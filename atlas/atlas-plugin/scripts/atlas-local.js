#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const crypto = require("node:crypto");
const childProcess = require("node:child_process");
const unicode = require("../workbench/unicode.js");
const workbenchCore = require("../workbench/core.js");
const { normalize: normalizedValue, stableStringify } = workbenchCore;
const workbenchCommon = require("../workbench/validation/common.js");
const workbenchAreas = {
  metadata: require("../workbench/metadata.js"),
  model: require("../workbench/model.js"),
};
const workbenchDbml = require("../workbench/dbml.js");
const qualityFiles = require("./model-quality-files.js");

const stateFiles = require("./workspace-state.js");
const HELPER_CONTRACT_PATH = path.resolve(__dirname, "..", "contracts", "local-helper.json");
const COMPACT_SCHEMA_OMISSIONS = new Set(["x-gds-columns", "x-gds-governed-authoring-schema", "x-gds-stage-record-validation"]);

function fail(message) {
  throw new Error(message);
}

function parseArguments(argv) {
  const [command, ...tokens] = argv;
  if (!command) fail("A command is required.");
  const options = {};
  for (let index = 0; index < tokens.length; index += 2) {
    const flag = tokens[index];
    const value = tokens[index + 1];
    if (!flag?.startsWith("--") || value === undefined) {
      fail(`Invalid argument near ${flag ?? "end of command"}.`);
    }
    if (Object.hasOwn(options, flag.slice(2))) fail(`Duplicate option ${flag}.`);
    options[flag.slice(2)] = value;
  }
  return { command, options };
}

function commandContract(options) {
  const contract = readJsonFile(HELPER_CONTRACT_PATH, "Local helper command contract");
  if (!options.command) {
    return { schema_version: contract.schema_version, commands: Object.keys(contract.commands) };
  }
  const command = contract.commands?.[options.command];
  if (!command) fail(`Unknown helper command contract: ${options.command}.`);
  return { schema_version: contract.schema_version, command: options.command, ...command };
}

function writeJsonAtomic(filePath, value) {
  const temporary = path.join(
    path.dirname(filePath),
    `.${path.basename(filePath)}.${process.pid}.${Date.now()}.tmp`,
  );
  fs.writeFileSync(temporary, `${JSON.stringify(value)}\n`, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600,
  });
  fs.renameSync(temporary, filePath);
}

function writeTextAtomic(filePath, value) {
  const temporary = path.join(
    path.dirname(filePath),
    `.${path.basename(filePath)}.${process.pid}.${Date.now()}.tmp`,
  );
  fs.writeFileSync(temporary, value, { encoding: "utf8", flag: "wx", mode: 0o600 });
  try {
    if (fs.existsSync(filePath)) {
      const stat = fs.lstatSync(filePath);
      if (!stat.isFile() || stat.isSymbolicLink()) fail("Generated DBML member must be a regular file.");
    }
    fs.renameSync(temporary, filePath);
  } catch (error) {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
    throw error;
  }
}

function readJsonFile(filePath, label) {
  const stat = fs.lstatSync(filePath);
  if (!stat.isFile() || stat.isSymbolicLink()) fail(`${label} must be a regular file.`);
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    fail(`${label} is not valid JSON.`);
  }
}

function assertSafeSnapshotMemberPath(relativePath) {
  if (
    typeof relativePath !== "string" ||
    !relativePath ||
    path.isAbsolute(relativePath) ||
    /^[A-Za-z]:/.test(relativePath) ||
    relativePath.includes("\\") ||
    relativePath.includes("\0") ||
    relativePath.split("/").some((part) => !part || part === "." || part === "..")
  ) {
    fail("Snapshot manifest contains an unsafe member path.");
  }
}

function snapshotInventory(manifest) {
  if (!Array.isArray(manifest.members) || manifest.members.length === 0) {
    fail("Snapshot manifest members are invalid.");
  }
  const inventory = new Map();
  for (const member of manifest.members) {
    if (!member || Array.isArray(member) || typeof member !== "object") {
      fail("Snapshot manifest members are invalid.");
    }
    assertSafeSnapshotMemberPath(member.path);
    if (
      !Number.isSafeInteger(member.size_bytes) ||
      member.size_bytes < 0 ||
      typeof member.sha256 !== "string" ||
      !/^[0-9a-f]{64}$/.test(member.sha256)
    ) {
      fail("Snapshot manifest members are invalid.");
    }
    if (inventory.has(member.path)) {
      fail(`Snapshot manifest contains duplicate member path ${member.path}.`);
    }
    inventory.set(member.path, member);
  }
  return inventory;
}

function resolveSnapshotMember(root, relativePath, inventory) {
  assertSafeSnapshotMemberPath(relativePath);
  const member = inventory.get(relativePath);
  if (!member) fail(`Snapshot member ${relativePath} is missing from the manifest inventory.`);
  const resolved = stateFiles.safePath(root, relativePath);
  if (!resolved.startsWith(`${root}${path.sep}`)) {
    fail("Snapshot member escapes its Snapshot directory.");
  }
  const stat = fs.lstatSync(resolved);
  if (!stat.isFile() || stat.isSymbolicLink()) fail("Snapshot member must be a regular file.");
  if (stat.size !== member.size_bytes) {
    fail(`Snapshot member size mismatch: ${relativePath}.`);
  }
  const digest = crypto.createHash("sha256").update(fs.readFileSync(resolved)).digest("hex");
  if (digest !== member.sha256) {
    fail(`Snapshot member SHA-256 mismatch: ${relativePath}.`);
  }
  return resolved;
}

function loadSnapshotRoot(root, session, area, bindSession = true, selectedOwner) {
  const manifest = readJsonFile(path.join(root, "manifest.json"), "Snapshot manifest");
  const inventory = snapshotInventory(manifest);
  if (
    !manifest.catalog ||
    Array.isArray(manifest.catalog) ||
    typeof manifest.catalog !== "object" ||
    manifest.catalog.path !== "catalog.json" ||
    typeof manifest.catalog.sha256 !== "string" ||
    !/^[0-9a-f]{64}$/.test(manifest.catalog.sha256)
  ) {
    fail("Snapshot manifest catalog descriptor is invalid.");
  }
  const catalogMember = inventory.get(manifest.catalog.path);
  if (!catalogMember || catalogMember.sha256 !== manifest.catalog.sha256) {
    fail("Snapshot manifest catalog descriptor does not match its member inventory.");
  }
  const catalog = readJsonFile(
    resolveSnapshotMember(root, manifest.catalog.path, inventory),
    "Snapshot catalog",
  );
  if (catalog.snapshot_kind !== area || manifest.snapshot_kind !== area) {
    fail(`Snapshot kind must match ${area}.`);
  }
  if (!Array.isArray(catalog.sections)) fail("Snapshot catalog sections are invalid.");

  const datasets = [];
  const byName = new Map();
  for (const section of catalog.sections) {
    if (!Array.isArray(section.datasets)) fail("Snapshot catalog datasets are invalid.");
    for (const dataset of section.datasets) {
      if (
        !dataset ||
        typeof dataset.name !== "string" ||
        !Number.isSafeInteger(dataset.row_count) ||
        dataset.row_count < 0 ||
        typeof dataset.rows_file !== "string" ||
        byName.has(dataset.name)
      ) {
        fail("Snapshot catalog contains an invalid or duplicate dataset.");
      }
      datasets.push(dataset);
      byName.set(dataset.name, dataset);
    }
  }
  assertSessionSnapshotIdentity(session, area, manifest, catalog, bindSession, selectedOwner);
  return { root, catalog, manifest, inventory, datasets, byName };
}

function inspectSnapshot(options) {
  const snapshot = locateSnapshot(options);
  return {
    area: options.area,
    kind: snapshot.catalog.snapshot_kind,
    id: snapshot.manifest.snapshot_id ?? null,
    revision: snapshot.manifest.model_revision ?? null,
    datasets: snapshot.datasets.map((dataset) => [dataset.name, dataset.row_count]),
  };
}

function compactAuthoringSchema(value) {
  if (Array.isArray(value)) return value.map(compactAuthoringSchema);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !COMPACT_SCHEMA_OMISSIONS.has(key))
      .map(([key, child]) => [key, compactAuthoringSchema(child)]),
  );
}

function describeDataset(options) {
  if (!options.dataset) fail("--dataset is required.");
  const snapshot = locateSnapshot(options);
  const dataset = snapshot.byName.get(options.dataset);
  if (!dataset) fail(`Unknown Snapshot dataset: ${options.dataset}.`);
  if (typeof dataset.schema_file !== "string") fail(`${dataset.name} schema path is missing.`);
  const schema = readJsonFile(
    resolveSnapshotMember(snapshot.root, dataset.schema_file, snapshot.inventory),
    `${dataset.name} schema`,
  );
  const detail = options.detail ?? "compact";
  if (!new Set(["compact", "full"]).has(detail)) {
    fail("--detail must be compact or full.");
  }
  return {
    detail,
    dataset: dataset.name,
    count: dataset.row_count,
    canonical_key: dataset.canonical_key,
    authoring_schema: compactAuthoringSchema(schema),
    schema: detail === "full" ? schema : null,
  };
}

function parseWhere(value) {
  if (value === undefined) return {};
  let parsed;
  try {
    parsed = JSON.parse(value);
  } catch {
    fail("--where must be a JSON object.");
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    fail("--where must be a JSON object.");
  }
  return parsed;
}

function digestValue(value) {
  return crypto.createHash("sha256").update(stableStringify(value), "utf8").digest("hex");
}

function canonicalKey(area, dataset, record) {
  if (!Array.isArray(dataset.canonical_key)) fail(`${dataset.name} canonical key is invalid.`);
  return dataset.canonical_key.map((field) => {
    if (!Object.hasOwn(record, field)) fail(`${dataset.name}.${field} is required by its canonical key.`);
    return normalizedValue(area, field, record[field]);
  });
}

function compareKeys(left, right) {
  const leftKey = stableStringify(left);
  const rightKey = stableStringify(right);
  return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
}

function readPending(context) {
  const pending = {};
  for (const entry of fs.readdirSync(context.directory, { withFileTypes: true })) {
    if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(".json")) {
      fail("Local Change Set contains an unsupported entry.");
    }
    const datasetName = entry.name.slice(0, -5);
    const dataset = context.byName.get(datasetName);
    if (!dataset) fail(`Local Change Set contains unknown dataset ${datasetName}.`);
    editableDatasetSchema(context, dataset);
    const records = readJsonFile(path.join(context.directory, entry.name), `${datasetName} pending file`);
    if (!Array.isArray(records)) fail(`${datasetName} pending file must contain a JSON array.`);
    const seen = new Set();
    for (const record of records) {
      if (!record || Array.isArray(record) || typeof record !== "object") {
        fail(`${datasetName} pending file contains a non-object record.`);
      }
      const key = stableStringify(canonicalKey(optionsArea(context), dataset, record));
      if (seen.has(key)) fail(`${datasetName} pending file contains a duplicate canonical key.`);
      seen.add(key);
    }
    records.sort((left, right) =>
      compareKeys(
        canonicalKey(optionsArea(context), dataset, left),
        canonicalKey(optionsArea(context), dataset, right),
      ),
    );
    pending[datasetName] = records;
  }
  return pending;
}

function optionsArea(context) {
  return context.catalog.snapshot_kind;
}

function workspaceDigest(context) {
  const hash = crypto.createHash("sha256");
  const entries = fs.readdirSync(context.directory, { withFileTypes: true });
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(".json")) {
      fail("Local Change Set contains an unsupported entry.");
    }
    const bytes = fs.readFileSync(path.join(context.directory, entry.name));
    hash.update(`${entry.name}\0${bytes.length}\0`, "utf8");
    hash.update(bytes);
  }
  return hash.digest("hex");
}

function assertExpectedDigest(options, context) {
  if (options["expected-digest"] === undefined) {
    fail("--expected-digest is required for every local write.");
  }
  const actual = workspaceDigest(context);
  if (options["expected-digest"] === "empty") {
    if (fs.readdirSync(context.directory).length !== 0) {
      fail(`Local Change Set digest conflict: expected an empty directory, found ${actual}.`);
    }
    return actual;
  }
  if (!/^[0-9a-f]{64}$/.test(options["expected-digest"])) {
    fail("--expected-digest must be empty or a lowercase SHA-256 digest.");
  }
  if (options["expected-digest"] !== actual) {
    fail(`Local Change Set digest conflict: expected ${options["expected-digest"]}, found ${actual}.`);
  }
}

function datasetSchema(context, dataset) {
  if (typeof dataset.schema_file !== "string") fail(`${dataset.name} schema path is missing.`);
  return readJsonFile(
    resolveSnapshotMember(context.root, dataset.schema_file, context.inventory),
    `${dataset.name} schema`,
  );
}

function editableDatasetSchema(context, dataset) {
  const schema = datasetSchema(context, dataset);
  if (schema["x-gds-change-set-eligible"] !== true) {
    fail(`${dataset.name} is not Change Set eligible.`);
  }
  return schema;
}

function schemaIssues(value, schema) {
  return workbenchCommon.validateSchema(value, schema);
}

function parseObjectOption(value, label) {
  let parsed;
  try {
    parsed = JSON.parse(value ?? "");
  } catch {
    fail(`${label} must be a JSON object.`);
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    fail(`${label} must be a JSON object.`);
  }
  return parsed;
}

function assertEditableRecords(context, proposed) {
  const loaded = new Map();
  for (const dataset of context.datasets) {
    const schema = datasetSchema(context, dataset), baseline = readSnapshotRecords(context, dataset);
    const pending = proposed[dataset.name] ?? [];
    loaded.set(dataset.name, {definition: {...dataset, record_type: schema["x-gds-record-type"] ?? dataset.record_type ?? dataset.name},
      schema, baseline, pending, effective: workbenchCore.overlay(optionsArea(context), dataset, baseline, pending)});
  }
  const findings = workbenchAreas[optionsArea(context)].validate(loaded, null, {tenantCode: context.owner.code});
  const locked = findings.find((finding) => /lock/.test(finding.code));
  if (locked) fail(locked.message ?? "A locked record cannot be changed.");
}

function writePendingDataset(context, dataset, records) {
  records.sort((left, right) =>
    compareKeys(
      canonicalKey(optionsArea(context), dataset, left),
      canonicalKey(optionsArea(context), dataset, right),
    ),
  );
  writeJsonAtomic(path.join(context.directory, `${dataset.name}.json`), records);
}

function readSnapshotRecords(context, dataset) {
  const rowsPath = resolveSnapshotMember(context.root, dataset.rows_file, context.inventory);
  const records = [];
  const lines = fs.readFileSync(rowsPath, "utf8").split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    if (!lines[index].trim()) continue;
    try {
      records.push(JSON.parse(lines[index]));
    } catch {
      fail(`${dataset.name} contains invalid JSON on line ${index + 1}.`);
    }
  }
  return records;
}

async function copyRecords(options) {
  const context = changeSetContext(options);
  const pending = readPending(context);
  assertExpectedDigest(options, context);
  const selection = await selectRecords({ ...options, limit: options.limit ?? "200" });
  if (selection.truncated) fail("Selection exceeds 200 records; narrow --where.");
  const dataset = context.byName.get(options.dataset);
  const schema = editableDatasetSchema(context, dataset);
  const records = pending[dataset.name] ?? [];
  const byKey = new Map(
    records.map((record, index) => [stableStringify(canonicalKey(options.area, dataset, record)), index]),
  );
  for (const record of selection.records) {
    const issues = schemaIssues(record, schema);
    if (issues.length) fail(`${dataset.name} Snapshot record fails its schema: ${issues[0]}`);
    const key = stableStringify(canonicalKey(options.area, dataset, record));
    const index = byKey.get(key);
    if (index === undefined) {
      byKey.set(key, records.length);
      records.push(record);
    } // Preserve an existing proposal; copy is not a reset command.

  }
  pending[dataset.name] = records;
  assertEditableRecords(context, {[dataset.name]: records});
  assertExpectedDigest(options, context);
  writePendingDataset(context, dataset, records);
  return { dataset: dataset.name, count: records.length, digest: workspaceDigest(context) };
}

function upsertRecord(options) {
  const context = changeSetContext(options);
  const pending = readPending(context);
  assertExpectedDigest(options, context);
  const dataset = context.byName.get(options.dataset ?? "");
  if (!dataset) fail(`Unknown Snapshot dataset: ${options.dataset}.`);
  const record = parseObjectOption(options.record, "--record");
  const issues = schemaIssues(record, editableDatasetSchema(context, dataset));
  if (issues.length) fail(`${dataset.name} record is invalid: ${issues[0]}`);
  const key = stableStringify(canonicalKey(options.area, dataset, record));
  const records = pending[dataset.name] ?? [];
  const index = records.findIndex(
    (item) => stableStringify(canonicalKey(options.area, dataset, item)) === key,
  );
  if (index < 0) records.push(record);
  else records[index] = record;
  pending[dataset.name] = records;

  const baseline = readSnapshotRecords(context, dataset).find(
    (item) => stableStringify(canonicalKey(options.area, dataset, item)) === key,
  );
  const action = baseline
    ? stableStringify(baseline) === stableStringify(record)
      ? "unchanged"
      : "changed"
    : "added";
  assertEditableRecords(context, {[dataset.name]: records});
  assertExpectedDigest(options, context);
  writePendingDataset(context, dataset, records);
  return { dataset: dataset.name, action, count: records.length, digest: workspaceDigest(context) };
}

function upsertBatch(options) {
  const context = changeSetContext(options);
  const pending = readPending(context);
  assertExpectedDigest(options, context);
  const changes = parseObjectOption(options.changes, "--changes");
  const names = Object.keys(changes).sort();
  if (names.length === 0) fail("--changes must contain at least one dataset.");

  let total = 0;
  const prepared = [];
  for (const name of names) {
    const dataset = context.byName.get(name);
    if (!dataset) fail(`Unknown Snapshot dataset: ${name}.`);
    const schema = editableDatasetSchema(context, dataset);
    const incoming = changes[name];
    if (!Array.isArray(incoming) || incoming.length === 0) {
      fail(`${name} batch must be a non-empty JSON array.`);
    }
    total += incoming.length;
    if (total > 200) fail("--changes may contain at most 200 records.");

    const records = [...(pending[name] ?? [])];
    const byKey = new Map(
      records.map((record, index) => [stableStringify(canonicalKey(options.area, dataset, record)), index]),
    );
    const batchKeys = new Set();
    for (let index = 0; index < incoming.length; index += 1) {
      const record = incoming[index];
      if (!record || Array.isArray(record) || typeof record !== "object") {
        fail(`${name} batch record ${index + 1} must be a JSON object.`);
      }
      const issues = schemaIssues(record, schema);
      if (issues.length) fail(`${name} batch record ${index + 1} is invalid: ${issues[0]}`);
      const key = stableStringify(canonicalKey(options.area, dataset, record));
      if (batchKeys.has(key)) fail(`${name} batch contains a duplicate canonical key.`);
      batchKeys.add(key);
      const existing = byKey.get(key);
      if (existing === undefined) {
        byKey.set(key, records.length);
        records.push(record);
      } else {
        records[existing] = record;
      }
    }
    prepared.push({ dataset, inputCount: incoming.length, records });
  }

  assertEditableRecords(context, Object.fromEntries(prepared.map((item) => [item.dataset.name, item.records])));
  assertExpectedDigest(options, context);
  for (const item of prepared) writePendingDataset(context, item.dataset, item.records);
  return {
    datasets: prepared.map((item) => [item.dataset.name, item.inputCount, item.records.length]),
    records: total,
    digest: workspaceDigest(context),
  };
}

function discardRecord(options) {
  const context = changeSetContext(options);
  const pending = readPending(context);
  assertExpectedDigest(options, context);
  const dataset = context.byName.get(options.dataset ?? "");
  if (!dataset) fail(`Unknown Snapshot dataset: ${options.dataset}.`);
  editableDatasetSchema(context, dataset);
  const keyObject = parseObjectOption(options.key, "--key");
  const expectedFields = dataset.canonical_key;
  if (
    Object.keys(keyObject).length !== expectedFields.length ||
    expectedFields.some((field) => !Object.hasOwn(keyObject, field))
  ) {
    fail("--key must contain exactly the dataset canonical-key fields.");
  }
  const key = stableStringify(canonicalKey(options.area, dataset, keyObject));
  const records = (pending[dataset.name] ?? []).filter(
    (record) => stableStringify(canonicalKey(options.area, dataset, record)) !== key,
  );
  pending[dataset.name] = records;
  assertExpectedDigest(options, context);
  writePendingDataset(context, dataset, records);
  return { dataset: dataset.name, count: records.length, digest: workspaceDigest(context) };
}

function recordActive(record) {
  if (typeof record.is_active === "boolean") return record.is_active;
  if (typeof record.status === "string") return record.status === "active";
  return null;
}

function reviewChangeSet(options) {
  const context = changeSetContext(options);
  const pending = readPending(context);
  const counts = {
    added: 0,
    changed: 0,
    reactivated: 0,
    deactivated: 0,
    unchanged: 0,
    total: 0,
  };
  const actions = [];
  for (const datasetName of Object.keys(pending).sort()) {
    const dataset = context.byName.get(datasetName);
    const baseline = new Map(
      readSnapshotRecords(context, dataset).map((record) => [
        stableStringify(canonicalKey(options.area, dataset, record)),
        record,
      ]),
    );
    for (const record of pending[datasetName]) {
      const keyValues = canonicalKey(options.area, dataset, record);
      const original = baseline.get(stableStringify(keyValues));
      let action;
      if (!original) action = "added";
      else if (stableStringify(original) === stableStringify(record)) action = "unchanged";
      else if (recordActive(original) === true && recordActive(record) === false) action = "deactivated";
      else if (recordActive(original) === false && recordActive(record) === true) action = "reactivated";
      else action = "changed";
      counts[action] += 1;
      counts.total += 1;
      if (actions.length < 200) {
        actions.push([
          datasetName,
          Object.fromEntries(dataset.canonical_key.map((field, index) => [field, keyValues[index]])),
          action,
        ]);
      }
    }
  }
  return {
    counts,
    actions,
    truncated: counts.total > actions.length,
    digest: workspaceDigest(context),
  };
}

function generateLocalDbml(options) {
  if (options.area !== "model") fail("--area must be model for generate-dbml.");
  const modelType = options["model-type"] ?? "full";
  if (!["full", "conceptual", "logical", "dimensional"].includes(modelType)) fail("Invalid DBML Model type.");
  const includeSubmodels = options["include-submodels"] ?? "true";
  if (!["true", "false"].includes(includeSubmodels)) fail("--include-submodels must be true or false.");
  const context = changeSetContext(options);
  const sessionDigest = stateFiles.session(context.session).digest;
  const validation = validateChangeSet({...options, _includeQuality: false});
  if (!validation.valid) fail(`Correct local Model findings before generating DBML; inspect ${validation.report}.`);
  const inputDigest = validation.digest;
  const verifyInputs = () => {
    if (stateFiles.session(context.session).digest !== sessionDigest || workspaceDigest(context) !== inputDigest ||
        validation.inputs.some((input) => fileDigest(stateFiles.safePath(context.session, input.manifest_path)) !== input.manifest_sha256) ||
        validation.snapshot.manifest_digest !== fileDigest(path.join(context.root, "manifest.json"))) {
      fail("DBML inputs changed during generation; reload and generate again.");
    }
  };
  verifyInputs();
  const pending = readPending(context), loaded = new Map();
  for (const dataset of context.datasets) {
    const baseline = readSnapshotRecords(context, dataset), draft = pending[dataset.name] ?? [];
    loaded.set(dataset.name, {definition: dataset, schema: datasetSchema(context, dataset), baseline, pending: draft,
      effective: workbenchCore.overlay("model", dataset, baseline, draft)});
  }
  const documents = workbenchDbml.render(loaded, context.catalog.model, {modelType, includeSubmodels: includeSubmodels === "true"});
  if (!documents.length || documents.length > 1002 || documents.reduce((sum, item) => sum + Buffer.byteLength(item.content), 0) > 16 * 1024 * 1024) fail("DBML output exceeds the supported file/byte limits.");
  const temporary = path.dirname(stateFiles.safePath(context.session, `.atlas/temp/dbml-${crypto.randomUUID()}/.check`, true));
  const candidate = path.join(temporary, "candidate"); fs.mkdirSync(candidate, {mode: 0o700});
  const files = documents.map(document => {
    if (!/^[A-Za-z0-9_][A-Za-z0-9_.-]*\.dbml$/.test(document.path) || Buffer.byteLength(document.content) > 12 * 1024 * 1024) fail("Invalid DBML output member.");
    fs.writeFileSync(path.join(candidate, document.path), document.content, {flag: "wx", mode: 0o600});
    return {path: document.path, layer: document.layer, view: document.view, submodel_name: document.submodel_name,
      table_count: document.table_count, relationship_count: document.relationship_count,
      size_bytes: Buffer.byteLength(document.content), sha256: sha256Bytes(Buffer.from(document.content, "utf8"))};
  });
  const manifest = {schema_version: "1.0", snapshot_kind: "dbml", source: "local_effective_model", generated_by: "agent",
    model: {id: context.catalog.model.model_id, name: context.catalog.model.model_name, revision: context.catalog.model.model_revision},
    draft_digest: inputDigest, inputs: validation.inputs, model_type: modelType, include_submodels: includeSubmodels === "true", files};
  writeJsonAtomic(path.join(candidate, "manifest.json"), manifest);
  verifyInputs();
  const destination = stateFiles.safePath(context.session, "model-dbml"), backup = path.join(temporary, "previous");
  const existed = fs.existsSync(destination);
  if (existed && !fs.lstatSync(destination).isDirectory()) fail("DBML destination must be a regular directory.");
  // Publish a complete generation; retain the previous directory for recovery.
  if (existed) fs.renameSync(destination, backup);
  try {
    fs.renameSync(candidate, destination);
    verifyInputs();
  } catch (error) {
    if (fs.existsSync(destination)) fs.renameSync(destination, candidate);
    if (existed) fs.renameSync(backup, destination);
    throw error;
  }
  return {directory: destination, manifest: path.join(destination, "manifest.json"), file_count: files.length,
    draft_digest: inputDigest, files: files.map(item => item.path)};
}

function sameAppliedRecord(local, server, schema, root = schema, recordType = "", collection = "") {
  // Retirement only: accepted bytes and Stage fingerprints must stay exact.
  if (stableStringify(local) === stableStringify(server)) return true;
  if (!schema || typeof schema !== "object") return false;
  if (typeof schema.$ref === "string") {
    if (!schema.$ref.startsWith("#/$defs/")) return false;
    return sameAppliedRecord(local, server, root.$defs?.[schema.$ref.slice(8)], root, recordType, collection);
  }
  const alternatives = schema.anyOf ?? schema.oneOf;
  if (Array.isArray(alternatives)) {
    // Pydantic Decimal schemas explicitly allow both numbers and patterned strings.
    if (alternatives.some((part) => part.type === "number") &&
        alternatives.some((part) => part.type === "string" && typeof part.pattern === "string")) {
      const values = [local, server].map((value) => {
        if (!["string", "number"].includes(typeof value) ||
            workbenchCommon.validateSchema(value, schema, root).length) return null;
        const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/.exec(String(value));
        if (!match) return null;
        const exponent = Number(match[4] ?? 0) - (match[3] ?? "").length;
        if (!Number.isSafeInteger(exponent)) return null;
        let digits = `${match[2]}${match[3] ?? ""}`.replace(/^0+/, "");
        if (!digits) return "0";
        const zeros = digits.length - digits.replace(/0+$/, "").length;
        digits = digits.slice(0, digits.length - zeros);
        return `${match[1] === "-" ? "-" : ""}${digits}e${exponent + zeros}`;
      });
      return values[0] !== null && values[0] === values[1];
    }
    return alternatives.some((part) =>
      workbenchCommon.validateSchema(local, part, root).length === 0 &&
      workbenchCommon.validateSchema(server, part, root).length === 0 &&
      sameAppliedRecord(local, server, part, root, recordType, collection));
  }
  if (Array.isArray(local) || Array.isArray(server)) {
    if (!Array.isArray(local) || !Array.isArray(server) || local.length !== server.length) return false;
    if (collection) {
      // SQL emits these owned collections by database ID/name. Explicit source_order stays compared.
      const identity = (item) => {
        if (!item || Array.isArray(item) || typeof item !== "object") return null;
        if (collection === "submodels") return typeof item.submodel_name === "string"
          ? stableStringify(["submodel", item.submodel_name]) : null;
        const field = {object: "source_object", attribute: "source_attribute", assertion: "assertion_record"}[item.support_source_type];
        return field && item[field] && typeof item[field] === "object" && !Array.isArray(item[field])
          ? stableStringify([item.support_source_type, item[field]]) : null;
      };
      const candidates = new Map();
      for (const item of server) {
        const key = identity(item);
        if (key === null || candidates.has(key)) return false;
        candidates.set(key, item);
      }
      for (const item of local) {
        const key = identity(item);
        if (key === null || !candidates.has(key) ||
            !sameAppliedRecord(item, candidates.get(key), schema.items, root, recordType)) return false;
        candidates.delete(key);
      }
      return candidates.size === 0;
    }
    return local.every((value, index) => sameAppliedRecord(value, server[index], schema.items, root, recordType));
  }
  if (!local || !server || typeof local !== "object" || typeof server !== "object") return false;
  for (const field of new Set([...Object.keys(local), ...Object.keys(server)])) {
    const child = schema.properties?.[field];
    const hasLocal = Object.hasOwn(local, field), hasServer = Object.hasOwn(server, field);
    if ((!hasLocal || !hasServer) && (!child || !Object.hasOwn(child, "default") ||
        schema.required?.includes(field))) return false;
    const ownedCollection = schema === root && (
      (field === "supports" && ["conceptual_object", "conceptual_relationship"].includes(recordType)) ||
      (field === "sources" && ["logical_entity", "logical_attribute", "dimensional_entity", "dimensional_attribute"].includes(recordType)) ||
      (field === "submodels" && ["logical_entity", "dimensional_entity"].includes(recordType))) ? field : "";
    if (!sameAppliedRecord(hasLocal ? local[field] : child.default,
      hasServer ? server[field] : child.default, child, root, recordType, ownedCollection)) return false;
  }
  return true;
}

function findExtractedSnapshotRoot(directory) {
  const candidates = [];
  const hasContract = (target) =>
    fs.existsSync(path.join(target, "catalog.json")) &&
    fs.existsSync(path.join(target, "manifest.json"));
  if (hasContract(directory)) candidates.push(directory);
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.isSymbolicLink()) {
      const target = path.join(directory, entry.name);
      if (hasContract(target)) candidates.push(target);
    }
  }
  if (candidates.length !== 1) fail("Snapshot ZIP must contain exactly one Snapshot root.");
  return candidates[0];
}

function sha256Bytes(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

async function selectRecords(options) {
  if (!options.dataset) fail("--dataset is required.");
  const limit = options.limit === undefined ? 50 : Number(options.limit);
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 200) {
    fail("--limit must be between 1 and 200.");
  }
  const where = parseWhere(options.where);
  const snapshot = locateSnapshot(options);
  const dataset = snapshot.byName.get(options.dataset);
  if (!dataset) fail(`Unknown Snapshot dataset: ${options.dataset}.`);
  if (options.view !== undefined && !["snapshot", "effective"].includes(options.view)) fail("--view must be snapshot or effective.");
  if (options.view === "effective") {
    const directory = stateFiles.safePath(snapshot.session, `${ownerPrefix(snapshot.owner)}${options.area}-change-set`);
    const pending = fs.existsSync(directory) ? readPending({...snapshot, directory})[dataset.name] ?? [] : [];
    const effective = workbenchCore.overlay(options.area, dataset, readSnapshotRecords(snapshot, dataset), pending);
    const matches = effective.filter((record) => Object.entries(where).every(([field, expected]) =>
      Object.hasOwn(record, field) && normalizedValue(options.area, field, record[field]) === normalizedValue(options.area, field, expected)));
    return {dataset: options.dataset, view: "effective", count: Math.min(matches.length, limit), truncated: matches.length > limit, records: matches.slice(0, limit)};
  }
  const rowsPath = resolveSnapshotMember(snapshot.root, dataset.rows_file, snapshot.inventory);
  const records = [];
  let truncated = false;
  let lineNumber = 0;
  const lines = readline.createInterface({
    input: fs.createReadStream(rowsPath, { encoding: "utf8" }),
    crlfDelay: Infinity,
  });
  for await (const line of lines) {
    lineNumber += 1;
    if (!line.trim()) continue;
    let record;
    try {
      record = JSON.parse(line);
    } catch {
      lines.close();
      fail(`${options.dataset} contains invalid JSON on line ${lineNumber}.`);
    }
    const matches = Object.entries(where).every(
      ([field, expected]) =>
        Object.hasOwn(record, field) &&
        normalizedValue(options.area, field, record[field]) ===
          normalizedValue(options.area, field, expected),
    );
    if (!matches) continue;
    if (records.length === limit) {
      truncated = true;
      lines.close();
      break;
    }
    records.push(record);
  }
  return { dataset: options.dataset, count: records.length, truncated, records };
}

function requireSessionPath(value) {
  if (!value) fail("--session must be the working directory containing .atlas.");
  const root = path.resolve(value);
  stateFiles.session(root);
  return root;
}

function readSessionState(root) { return stateFiles.session(root).value; }

function ownerPrefix(owner) { return owner.root === "." ? "" : `${owner.root}/`; }

function locateSnapshot(options) {
  const session = requireSessionPath(options.session);
  const state = readSessionState(session);
  const owner = stateFiles.owner(state, options.area, options.owner);
  const relative = `${ownerPrefix(owner)}${options.area}/${options.area}-snapshot`;
  const root = stateFiles.safePath(session, relative);
  if (!fs.existsSync(root)) fail(`${options.area} Snapshot directory is missing.`);
  const snapshot = loadSnapshotRoot(root, session, options.area, false, owner);
  return {...snapshot, session, state, owner};
}

function assertSessionSnapshotIdentity(session, area, manifest, catalog, _bind, selectedOwner) {
  const state = readSessionState(session);
  const owner = selectedOwner ?? stateFiles.owner(state, area);
  if (area === "metadata") {
    if (normalizedValue("metadata", "tenant_code", manifest.tenant_code) !== normalizedValue("metadata", "tenant_code", owner.code)) {
      fail("Metadata Snapshot does not match the selected owner.");
    }
    if (manifest.tenant_id !== undefined && manifest.tenant_id !== owner.id) fail("Metadata Snapshot Tenant ID mismatch.");
  } else {
    const model = catalog.model;
    if (!state.model || manifest.model_id !== state.model.id || !model || model.model_id !== manifest.model_id ||
        model.model_name !== manifest.model_name || model.model_revision !== manifest.model_revision ||
        !Number.isSafeInteger(manifest.model_revision) || manifest.model_revision < 0) fail("Model Snapshot identity/revision mismatch.");
    if (model.tenant_code && normalizedValue("metadata", "tenant_code", model.tenant_code) !== normalizedValue("metadata", "tenant_code", state.tenant.code)) {
      fail("Model Snapshot Tenant mismatch.");
    }
  }
}

function changeSetContext(options) {
  const snapshot = locateSnapshot(options);
  if (snapshot.state.refresh_required?.some((entry) => entry.area === options.area && entry.owner_tenant_id === snapshot.owner.id)) {
    fail("Snapshot requires refresh/reconciliation before authoring.");
  }
  const taskId = options.task ?? snapshot.state.active_task;
  stateFiles.task(snapshot.session, taskId);
  const relative = `${ownerPrefix(snapshot.owner)}${options.area}-change-set`;
  const directory = stateFiles.safePath(snapshot.session, `${relative}/.check`, true);
  return {...snapshot, taskId, directory: path.dirname(directory)};
}

function initializeSession(options) {
  if (!options.root || !path.isAbsolute(options.root)) fail("--root must be an absolute working directory.");
  const root = path.resolve(options.root);
  const tenant = {id: Number(options["tenant-id"]), code: options.tenant};
  stateFiles.identity(tenant, "Tenant");
  const model = options["model-id"] === undefined ? null : {id: Number(options["model-id"]), name: options["model-name"]};
  if (model && (!Number.isSafeInteger(model.id) || model.id < 1 || typeof model.name !== "string" || !model.name.trim())) fail("Model requires verified --model-id and --model-name.");
  fs.mkdirSync(root, {recursive: true, mode: 0o700});
  if (fs.existsSync(path.join(root, ".atlas", "session.json"))) {
    const existing = readSessionState(root);
    if (existing.tenant.id !== tenant.id || existing.tenant.code !== tenant.code || (model && existing.model?.id !== model.id)) fail("Existing workspace identity differs; use another directory.");
    return {workspace: root, reused: true, session: existing};
  }
  const value = {schema_version: "1.0", tenant, model, active_task: null, metadata_owners: {[String(tenant.id)]: {...tenant, root: "."}}};
  if (options.policy) value.sql = {policy: options.policy, ...(options.environment ? {environment: options.environment} : {})};
  if (value.sql && (!["never", "essential", "proactive"].includes(value.sql.policy) || (value.sql.environment && !["dev", "qa", "stg", "prod"].includes(value.sql.environment)))) fail("Invalid SQL choices.");
  stateFiles.write(root, ".atlas/session.json", value);
  stateFiles.safePath(root, ".atlas/tasks/.check", true);
  stateFiles.safePath(root, ".atlas/temp/.check", true);
  return {workspace: root, reused: false, session: value};
}

function selectModel(options) {
  const root = requireSessionPath(options.session), document = stateFiles.session(root);
  const model = {id: Number(options["model-id"]), name: options["model-name"]};
  if (!Number.isSafeInteger(model.id) || model.id < 1 || typeof model.name !== "string" || !model.name.trim()) fail("Model requires a verified ID and name.");
  if (document.value.model && document.value.model.id !== model.id) fail("One Model per directory; use a different directory for another Model.");
  document.value.model = model;
  stateFiles.write(root, ".atlas/session.json", document.value, document.digest);
  return {model};
}

function selectTask(options) {
  const root = requireSessionPath(options.session), document = stateFiles.session(root);
  stateFiles.task(root, options.task);
  document.value.active_task = options.task;
  stateFiles.write(root, ".atlas/session.json", document.value, document.digest);
  return {task: options.task};
}

function registerOwner(options) {
  const root = requireSessionPath(options.session), document = stateFiles.session(root);
  const state = document.value;
  const owner = {id: Number(options["tenant-id"]), code: options.tenant};
  stateFiles.identity(owner, "Metadata owner");
  if (owner.id !== state.tenant.id && !state.model) fail("Additional owners require Model-derived work.");
  owner.root = owner.id === state.tenant.id ? "." : `metadata-owners/tenant-${owner.id}`;
  const previous = state.metadata_owners?.[String(owner.id)];
  if (previous && (previous.code !== owner.code || previous.root !== owner.root)) fail("Owner identity cannot be rebound.");
  state.metadata_owners ??= {};
  state.metadata_owners[String(owner.id)] = owner;
  stateFiles.write(root, ".atlas/session.json", state, document.digest);
  return {owner};
}

function addTask(options) {
  const root = requireSessionPath(options.session), document = stateFiles.session(root);
  if (typeof options.outcome !== "string" || !options.outcome.trim()) fail("--outcome is required.");
  const id = crypto.randomUUID();
  const value = {schema_version: "1.0", outcome: options.outcome};
  if (options.workflow) value.inputs = {workflow: options.workflow};
  stateFiles.write(root, `.atlas/tasks/${id}.json`, value);
  stateFiles.safePath(root, `.atlas/tasks/${id}.evidence/.check`, true);
  document.value.active_task = id;
  stateFiles.write(root, ".atlas/session.json", document.value, document.digest);
  return {task: id, path: `.atlas/tasks/${id}.json`};
}

function updateTask(options) {
  const root = requireSessionPath(options.session);
  const id = options.task ?? readSessionState(root).active_task;
  const previous = stateFiles.task(root, id);
  if (options["expected-digest"] !== previous.digest) fail("Task changed; use its current --expected-digest.");
  const replacement = options.file ? readJsonFile(path.resolve(options.file), "Task") : {...previous.value, progress: options.progress};
  if (!replacement || replacement.schema_version !== "1.0" || typeof replacement.outcome !== "string" || !replacement.outcome.trim() || (replacement.progress !== undefined && typeof replacement.progress !== "string") || (replacement.inputs !== undefined && !stateFiles.object(replacement.inputs)) || ["work", "evidence"].some((key) => replacement[key] !== undefined && (!Array.isArray(replacement[key]) || replacement[key].some((item) => !stateFiles.object(item) || typeof item.path !== "string" || typeof item.purpose !== "string")))) fail("Task needs schema_version and outcome.");
  const digest = stateFiles.write(root, `.atlas/tasks/${id}.json`, replacement, previous.digest);
  return {task: id, digest};
}

function sessionStatus(options) {
  const root = requireSessionPath(options.session), document = stateFiles.session(root);
  const tasks = fs.readdirSync(stateFiles.safePath(root, ".atlas/tasks")).filter((name) => name.endsWith(".json"));
  return {workspace: root, session: document.value, session_digest: document.digest,
    tasks: tasks.map((file) => { const id = file.slice(0, -5), task = stateFiles.task(root, id); return {id, ...task.value, digest: task.digest}; })};
}

function setSqlPolicy(options) {
  const root = requireSessionPath(options.session), document = stateFiles.session(root);
  if (!["never", "essential", "proactive"].includes(options.policy)) fail("Invalid SQL policy.");
  const environment = options.environment ?? document.value.sql?.environment ?? "dev";
  if (!["dev", "qa", "stg", "prod"].includes(environment)) fail("Invalid SQL environment.");
  document.value.sql = {policy: options.policy, ...(options.policy === "never" ? {} : {environment})};
  stateFiles.write(root, ".atlas/session.json", document.value, document.digest);
  return {sql: document.value.sql};
}

function fileDigest(file) { return sha256Bytes(fs.readFileSync(file)); }

function snapshotBinding(context) {
  return {area: optionsArea(context), owner_tenant_id: context.owner.id,
    manifest_path: path.relative(context.session, path.join(context.root, "manifest.json")).split(path.sep).join("/"),
    snapshot_id: context.manifest.snapshot_id, manifest_sha256: fileDigest(path.join(context.root, "manifest.json")),
    ...(optionsArea(context) === "model" ? {model_revision: context.manifest.model_revision} : {})};
}

function reportRelative(context) {
  return `.atlas/tasks/${context.taskId}.evidence/${optionsArea(context)}-${context.owner.id}-validation.json`;
}

function loadAppliedMetadata(context) {
  const metadata = new Map(), inputs = [], missingMetadataOwners = [];
  const owners = new Map([[context.state.tenant.id, {...context.state.tenant, root: "."}], ...Object.values(context.state.metadata_owners ?? {}).map((owner) => [owner.id, owner])]);
  for (const owner of owners.values()) {
    if (context.state.refresh_required?.some((entry) => entry.area === "metadata" && entry.owner_tenant_id === owner.id)) fail("Model work needs refreshed Metadata inputs.");
    let snapshot;
    try { snapshot = locateSnapshot({session: context.session, area: "metadata", owner: owner.id}); }
    catch (error) { if (error.code === "ENOENT" || error.message === "metadata Snapshot directory is missing." || error.message === "Workspace parent directory is missing.") { missingMetadataOwners.push(owner.id); continue; } throw error; }
    inputs.push(snapshotBinding(snapshot));
    for (const dataset of snapshot.datasets) {
      const schema = datasetSchema(snapshot, dataset), rows = readSnapshotRecords(snapshot, dataset);
      const prior = metadata.get(dataset.name);
      if (prior && stableStringify(prior.definition.canonical_key) !== stableStringify(dataset.canonical_key)) fail("Owner Snapshots disagree on dataset key contracts.");
      const merged = new Map((prior?.baseline ?? []).map((row) => [stableStringify(canonicalKey("metadata", dataset, row)), row]));
      for (const row of rows) {
        const key = stableStringify(canonicalKey("metadata", dataset, row)), existing = merged.get(key);
        if (existing && stableStringify(existing) !== stableStringify(row)) fail("Owner Snapshots disagree on a shared record; refresh before proceeding.");
        merged.set(key, row);
      }
      metadata.set(dataset.name, {definition: {...dataset, record_type: schema["x-gds-record-type"] ?? dataset.record_type ?? dataset.name}, schema, baseline: [...merged.values()]});
    }
  }
  return {metadata, inputs, missingMetadataOwners};
}

function validateChangeSet(options) {
  const context = changeSetContext(options), pending = readPending(context), loaded = new Map();
  const inputDigest = workspaceDigest(context), binding = snapshotBinding(context);
  for (const dataset of context.datasets) {
    const schema = datasetSchema(context, dataset), baseline = readSnapshotRecords(context, dataset), draft = pending[dataset.name] ?? [];
    let effective = baseline, overlayError = null;
    try { effective = workbenchCore.overlay(options.area, dataset, baseline, draft); }
    catch (error) { overlayError = error.message; }
    loaded.set(dataset.name, {definition: {...dataset, record_type: schema["x-gds-record-type"] ?? dataset.record_type ?? dataset.name}, schema, baseline, pending: draft, effective, overlayError});
  }
  const applied = options.area === "model" ? loadAppliedMetadata(context) : {metadata: null, inputs: [], missingMetadataOwners: []};
  const {metadata, missingMetadataOwners} = applied;
  const inputs = [binding, ...applied.inputs];
  // A Metadata enrichment task may derive its selection from a Model Snapshot.
  const declared = stateFiles.task(context.session, context.taskId).value.inputs?.snapshots ?? [];
  if (!Array.isArray(declared)) fail("Task Snapshot bindings must be an array.");
  const declaredDigest = digestValue(declared);
  for (const input of declared) {
    if (!stateFiles.object(input) || !["metadata", "model"].includes(input.area)) fail("Invalid task Snapshot binding.");
    const actual = snapshotBinding(locateSnapshot({session: context.session, area: input.area, owner: input.owner_tenant_id}));
    if (Object.keys(actual).some((field) => actual[field] !== input[field])) fail("Task Snapshot input changed; review its selection before validation.");
    if (!inputs.some((existing) => existing.manifest_path === actual.manifest_path)) inputs.push(actual);
  }
  let decisions = null, noteFiles = {}, qualityBindings = [];
  if (options.area === "model" && options._includeQuality !== false && Object.keys(pending).some((name) => qualityFiles.modelingDatasets.has(name))) {
    const evidence = qualityFiles.readDecisions(context.session, context.taskId);
    decisions = evidence.decisions;
    noteFiles = evidence.noteFiles;
    qualityBindings = evidence.files;
  }
  const evaluated = require("../workbench/validation/run.js").run(options.area, loaded, metadata,
    {tenantCode: context.owner.code, model: context.catalog.model ?? null, decisions, noteFiles, missingMetadataOwners, includeQuality: options._includeQuality !== false});
  const {issues, quality} = evaluated;
  for (const evidence of qualityBindings) {
    const file = stateFiles.safePath(context.session, evidence.path);
    if (evidence.sha256 === null ? fs.existsSync(file) : !fs.existsSync(file) || fileDigest(file) !== evidence.sha256) fail("Modeling evidence changed during validation.");
  }
  if (digestValue(stateFiles.task(context.session, context.taskId).value.inputs?.snapshots ?? []) !== declaredDigest) fail("Task Snapshot inputs changed during validation.");
  if (workspaceDigest(context) !== inputDigest || inputs.some((input) => fileDigest(stateFiles.safePath(context.session, input.manifest_path)) !== input.manifest_sha256)) fail("Validation inputs changed; run validation again.");
  const result = {schema_version: "1.0", run_by: "agent", area: options.area, owner_tenant_id: context.owner.id,
    generated_at: new Date().toISOString(), digest: inputDigest, inputs,
    snapshot: {id: binding.snapshot_id, revision: context.manifest.model_revision ?? null, manifest_digest: binding.manifest_sha256},
    valid: evaluated.valid, checks: evaluated.checks,
    issue_count: evaluated.issueCount, truncated: evaluated.truncated,
    issues: issues.slice(0, 200), quality, evidence_files: qualityBindings};
  const relative = reportRelative(context), file = stateFiles.safePath(context.session, relative, true);
  stateFiles.write(context.session, relative, result, fs.existsSync(file) ? stateFiles.read(context.session, relative).digest : "absent");
  return {...result, report: relative};
}

function acceptChangeSet(options) {
  const context = changeSetContext(options);
  if (!stateFiles.digest.test(options.digest ?? "") || workspaceDigest(context) !== options.digest) fail("Acknowledged digest does not match local files.");
  if (!["production", "local", "azureLocalTest"].includes(options["backend-profile"]) || !stateFiles.digest.test(options["endpoint-sha256"] ?? "")) fail("Supply safe backend identity from Check Stage Runner.");
  const validation = validateChangeSet(options);
  if (!validation.valid) fail("Fix local validation findings before acknowledgement.");
  const stateDocument = stateFiles.session(context.session);
  let prior = null;
  try { prior = stateFiles.operation(context.session, stateDocument.value, options.area, context.owner); }
  catch (error) { if (error.message !== "A digest-bound acknowledgement is required first.") throw error; }
  if (prior?.value.stage_attempt?.status === "unknown") fail("Prior Stage result is uncertain; inspect it before accepting another operation.");
  if (prior?.value.stage && !prior.value.apply && !prior.value.draft?.validation_failed) fail("Previous Stage needs validation/Apply or explicit reconciliation before new acceptance.");
  const id = crypto.randomUUID(), relative = `.atlas/tasks/${context.taskId}.evidence/${id}.json`;
  const reportHash = fileDigest(stateFiles.safePath(context.session, validation.report));
  const operation = {schema_version: "1.0", id, task_id: context.taskId, area: options.area, owner: context.owner,
    backend: {profile: options["backend-profile"], endpoint_sha256: options["endpoint-sha256"]}, inputs: validation.inputs,
    local_digest: options.digest, validation: {outcome: "valid", report_path: validation.report, report_sha256: reportHash, checks: validation.checks},
    acknowledgement: {source: "conversation", at: new Date().toISOString(), digest: options.digest, report_sha256: reportHash},
    ...(prior?.value.draft?.validation_failed ? {draft: prior.value.draft} : {})};
  // Preserve an immutable copy for each operation; later validation reports can change.
  const savedReport = `.atlas/tasks/${context.taskId}.evidence/${id}.validation.json`;
  stateFiles.write(context.session, savedReport, stateFiles.read(context.session, validation.report).value);
  operation.validation.report_path = savedReport;
  operation.validation.report_sha256 = stateFiles.read(context.session, savedReport).digest;
  operation.acknowledgement.report_sha256 = operation.validation.report_sha256;
  stateFiles.write(context.session, relative, operation);
  stateDocument.value.operations ??= {};
  if (options.area === "model") stateDocument.value.operations.model = relative;
  else { stateDocument.value.operations.metadata ??= {}; stateDocument.value.operations.metadata[String(context.owner.id)] = relative; }
  stateFiles.write(context.session, ".atlas/session.json", stateDocument.value, stateDocument.digest);
  return {operation: id, path: relative, task: context.taskId, digest: options.digest};
}

function cacheServerDraft(options) {
  const root = requireSessionPath(options.session), state = readSessionState(root), owner = stateFiles.owner(state, options.area, options.owner);
  const document = stateFiles.operation(root, state, options.area, owner), operation = document.value;
  const revision = Number(options.revision);
  if (!stateFiles.uuid.test(options.id ?? "") || !Number.isSafeInteger(revision) || revision < 0 || !["active", "validated"].includes(options.status)) fail("Invalid server draft identity/revision/status.");
  if (operation.draft && operation.draft.id !== options.id) fail("Operation cannot be rebound to another server draft.");
  if (operation.draft && revision < operation.draft.revision) fail("Server revision cannot go backwards.");
  operation.draft = {id: options.id, revision, status: options.status, digest: operation.draft?.digest ?? operation.local_digest,
    ...(options["validation-failed"] === "true" ? {validation_failed: true} : {})};
  stateFiles.write(root, document.relative, operation, document.digest);
  return {operation: operation.id, draft: operation.draft};
}

function assertOperationInputs(root, operation) {
  for (const binding of operation.inputs) {
    if (fileDigest(stateFiles.safePath(root, binding.manifest_path)) !== binding.manifest_sha256) fail("Snapshot changed after acknowledgement.");
  }
  const report = stateFiles.read(root, operation.validation.report_path);
  if (report.digest !== operation.validation.report_sha256 || report.value.valid !== true) fail("Validation report changed after acknowledgement.");
  for (const evidence of report.value.evidence_files ?? []) {
    const file = stateFiles.safePath(root, evidence.path);
    if (evidence.sha256 === null ? fs.existsSync(file) : !fs.existsSync(file) || fileDigest(file) !== evidence.sha256) fail("Modeling evidence changed after acknowledgement.");
  }
}

function prepareStageRequest(options) {
  const context = changeSetContext(options), document = stateFiles.operation(context.session, context.state, options.area, context.owner), operation = document.value;
  if (workspaceDigest(context) !== operation.local_digest) fail("Local files changed after acknowledgement.");
  assertOperationInputs(context.session, operation);
  if (!operation.draft || operation.draft.status !== "active") fail("Cache the active server draft before preparing Stage.");
  if (operation.stage_attempt?.status === "unknown") fail("Stage result is uncertain; inspect before retrying.");
  const pending = readPending(context), names = Object.keys(pending).sort();
  if (!names.length) fail("No local datasets to Stage.");
  const relative = `.atlas/tasks/${operation.task_id}.evidence/${operation.id}.stage-request.json`;
  const binding = snapshotBinding(context);
  const manifest = {schema_version: "1.0", kind: "atlas-stage-request", area: options.area, task: operation.task_id,
    accepted_digest: operation.local_digest, failed_retry: operation.draft.validation_failed === true && operation.draft.digest !== operation.local_digest,
    operation: {id: operation.id, path: document.relative}, owner: context.owner, backend: operation.backend,
    snapshot: {snapshot_id: binding.snapshot_id, manifest_sha256: binding.manifest_sha256, manifest_path: binding.manifest_path},
    target: {...(options.area === "metadata" ? {tenant_code: context.owner.code} : {model_id: context.manifest.model_id, model_name: context.manifest.model_name, model_revision: context.manifest.model_revision}), change_set_id: operation.draft.id, starting_revision: operation.draft.revision},
    datasets: names.map((name) => ({dataset: name, canonical_key: context.byName.get(name).canonical_key, record_count: pending[name].length,
      payload_file: `${ownerPrefix(context.owner)}${options.area}-change-set/${name}.json`, sha256: fileDigest(path.join(context.directory, `${name}.json`))}))};
  const existing = fs.existsSync(stateFiles.safePath(context.session, relative));
  stateFiles.write(context.session, relative, manifest, existing ? stateFiles.read(context.session, relative).digest : "absent");
  operation.stage_request = {path: relative, sha256: fileDigest(stateFiles.safePath(context.session, relative))};
  stateFiles.write(context.session, document.relative, operation, document.digest);
  return {manifest: stateFiles.safePath(context.session, relative), accepted_digest: operation.local_digest, operation: operation.id, dataset_count: names.length};
}

function aggregatePlan(options, kind) {
  const context = changeSetContext({...options, area: "model"});
  const applied = loadAppliedMetadata(context);
  if (applied.missingMetadataOwners.length) fail("Install every registered owner Metadata Snapshot before planning SQL.");
  if (!options["plan-file"]) fail("--plan-file is required.");
  const supplied = readJsonFile(path.resolve(options["plan-file"]), "SQL planning input");
  const selections = supplied.selections;
  if (!stateFiles.object(selections) || !Array.isArray(supplied.execution_connections) || !supplied.execution_connections.length) fail("Plan requires selections and verified execution_connections.");
  const environment = context.state.sql?.environment ?? (context.state.sql?.policy === "never" ? "dev" : null);
  if (!environment) fail("Resolve SQL policy/environment before preparing evidence queries.");
  const definition = context.byName.get("model_input_scope");
  if (!definition) fail("Model Input Scope is missing.");
  const datasets = Object.fromEntries([...applied.metadata].map(([name, dataset]) => [name, dataset.baseline]));
  const planner = kind === "analysis" ? require("./analysis.js").planAnalysis : require("./profiling.js").planProfiling;
  const planned = planner(datasets, readSnapshotRecords(context, definition), selections);
  const queries = kind === "profiling" ? planned.queries : planned;
  const directoryRelative = `.atlas/temp/${context.taskId}/${kind}/${crypto.randomUUID()}`;
  const directory = path.dirname(stateFiles.safePath(context.session, `${directoryRelative}/.check`, true));
  const entries = queries.map(({sql, ...query}, index) => {
    const sourceTenants = [...new Set((query.endpoints ?? [query]).map((endpoint) => endpoint.source_tenant_code))];
    const choices = supplied.execution_connections.filter((connection) => sourceTenants.every((tenant) => connection.source_tenant_codes?.includes(tenant)));
    if (choices.length !== 1 || !Number.isSafeInteger(choices[0].connection_id) || choices[0].connection_id < 1 || choices[0].is_global_data_store !== false) fail("Each query needs one verified non-GDS execution Connection covering its source owners.");
    const file = `${String(index + 1).padStart(4, "0")}.sql`;
    fs.writeFileSync(path.join(directory, file), sql, {flag: "wx", mode: 0o600});
    return {...query, file, sha256: sha256Bytes(Buffer.from(sql, "utf8")), origin: "atlas-generator", generator_version: "1.0",
      environment, connection_id: choices[0].connection_id, expected_row_count: kind === "profiling" ? query.attributes.length : 1};
  });
  const manifest = {schema_version: "1.0", kind, task: context.taskId, inputs: [snapshotBinding(context), ...applied.inputs],
    environment, selections, queries: entries, ...(kind === "profiling" ? {coverage: planned.coverage} : {})};
  if (manifest.inputs.some((input) => fileDigest(stateFiles.safePath(context.session, input.manifest_path)) !== input.manifest_sha256)) fail("Snapshot changed during planning; discard this plan and retry.");
  writeJsonAtomic(path.join(directory, "plan.json"), manifest);
  return {directory, manifest: path.join(directory, "plan.json"), query_count: entries.length};
}

async function main() {
  const {command, options} = parseArguments(process.argv.slice(2));
  const commands = {
    "command-contract": commandContract, "session-init": initializeSession, "status": sessionStatus,
    "owner-add": registerOwner, "model-select": selectModel, "sql-policy": setSqlPolicy, "task-add": addTask, "task-update": updateTask, "task-select": selectTask,
    "inspect": inspectSnapshot, "describe": describeDataset, "select": selectRecords, "copy": copyRecords,
    "upsert": upsertRecord, "upsert-batch": upsertBatch, "discard": discardRecord,
    "review": reviewChangeSet, "validate": validateChangeSet, "accept": acceptChangeSet,
    "draft-cache": cacheServerDraft, "prepare-stage-request": prepareStageRequest,
    "generate-dbml": generateLocalDbml, "snapshot-install": installSnapshot, "operation-record": recordOperation,
    "profile-results": importProfileResults,
    "profile-plan": (value) => aggregatePlan(value, "profiling"),
    "analysis-plan": (value) => aggregatePlan(value, "analysis"),
  };
  if (!commands[command]) fail(`Unknown Atlas command: ${command}.`);
  const contract = readJsonFile(HELPER_CONTRACT_PATH, "Local helper command contract").commands[command];
  const allowed = new Set([...contract.usage.matchAll(/--([a-z0-9-]+)/g)].map((match) => match[1]));
  // Explicit task selection is valid for local authoring commands; it never changes operation ownership.
  if (["copy", "upsert", "upsert-batch", "discard", "review", "accept", "generate-dbml"].includes(command)) allowed.add("task");
  for (const option of Object.keys(options)) if (!allowed.has(option)) fail(`Unsupported option --${option} for ${command}. Read command-contract.`);
  process.stdout.write(`${JSON.stringify(await commands[command](options))}\n`);
}

if (require.main === module) main().catch((error) => {
  process.stderr.write(`atlas-local: ${error.message}\n`);
  process.exitCode = 1;
});
module.exports = {initializeSession, locateSnapshot, changeSetContext, readPending, workspaceDigest, validateChangeSet, snapshotBinding};

function installSnapshot(options) {
  const session = requireSessionPath(options.session), state = readSessionState(session), owner = stateFiles.owner(state, options.area, options.owner);
  if (!stateFiles.uuid.test(options["snapshot-id"] ?? "") || !stateFiles.digest.test(options.sha256 ?? "")) fail("Snapshot ID and SHA-256 are required.");
  const archive = path.resolve(options.archive ?? ""), stat = fs.lstatSync(archive);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size !== Number(options["size-bytes"]) || fileDigest(archive) !== options.sha256) fail("Snapshot archive identity/size/hash mismatch.");
  const pendingPath = stateFiles.safePath(session, `${ownerPrefix(owner)}${options.area}-change-set/.check`, true);
  const pendingDirectory = path.dirname(pendingPath);
  const pendingNames = fs.readdirSync(pendingDirectory);
  let applied = null;
  if (pendingNames.some((name) => {
    if (!name.endsWith(".json")) fail("Unexpected local draft entry.");
    const rows = readJsonFile(path.join(pendingDirectory, name), "Pending dataset");
    if (!Array.isArray(rows)) fail("Pending dataset must contain an array.");
    return rows.length > 0;
  })) {
    applied = stateFiles.operation(session, state, options.area, owner);
    if (applied.value.apply?.applied !== true) fail("Preserve local drafts; Apply or reconcile them before replacing the Snapshot.");
  }
  if (!applied && state.refresh_required?.some((entry) => entry.area === options.area && entry.owner_tenant_id === owner.id)) {
    const previous = stateFiles.operation(session, state, options.area, owner);
    if (previous.value.apply?.applied === true) applied = previous;
  }
  const tempRelative = `.atlas/temp/snapshot-${crypto.randomUUID()}`, temporary = path.dirname(stateFiles.safePath(session, `${tempRelative}/.check`, true));
  const extracted = path.join(temporary, "incoming"); fs.mkdirSync(extracted, {mode: 0o700});
  let result;
  for (const command of [["python3"], ["python"], ["py", "-3"]]) {
    result = childProcess.spawnSync(command[0], [...command.slice(1), path.join(__dirname, "unpack-snapshot.py"), archive, extracted], {encoding: "utf8", windowsHide: true, maxBuffer: 1024 * 1024});
    if (!result.error || result.error.code !== "ENOENT") break;
  }
  if (result.error || result.status !== 0) fail("Snapshot extraction failed; Python 3.12+ is required. Previous files are preserved.");
  const candidateRoot = findExtractedSnapshotRoot(extracted);
  const candidate = loadSnapshotRoot(candidateRoot, session, options.area, false, owner);
  if (candidate.manifest.snapshot_id !== options["snapshot-id"]) fail("Extracted Snapshot ID mismatch.");
  if (options.area === "model") {
    const previousManifest = path.join(session, "model/model-snapshot/manifest.json");
    const previousRevision = fs.existsSync(previousManifest) ? readJsonFile(previousManifest, "Previous Snapshot").model_revision : 0;
    const minimumRevision = Math.max(previousRevision ?? 0, applied?.value.apply?.model_revision ?? 0);
    if (!Number.isSafeInteger(candidate.manifest.model_revision) || candidate.manifest.model_revision < minimumRevision) fail("Refreshed Model Snapshot is older than the known Model revision.");
  }
  // Verify every declared file, including datasets not yet opened by a workflow.
  for (const member of candidate.inventory.keys()) resolveSnapshotMember(candidateRoot, member, candidate.inventory);
  const retire = [];
  if (applied) {
    for (const name of pendingNames) {
      if (!name.endsWith(".json")) fail("Unexpected local draft entry.");
      const definition = candidate.byName.get(name.slice(0, -5));
      if (!definition) fail("Applied dataset missing from refreshed Snapshot.");
      const pending = readJsonFile(path.join(pendingDirectory, name), "Pending dataset");
      const baseline = new Map(readSnapshotRecords(candidate, definition).map((row) => [stableStringify(canonicalKey(options.area, definition, row)), row]));
      const schema = datasetSchema(candidate, definition);
      const remaining = pending.filter((row) => {
        const server = baseline.get(stableStringify(canonicalKey(options.area, definition, row)));
        return !server || !sameAppliedRecord(row, server, schema);
      });
      retire.push({name, remaining, digest: fileDigest(path.join(pendingDirectory, name))});
    }
  }
  const relative = `${ownerPrefix(owner)}${options.area}/${options.area}-snapshot`;
  const destination = stateFiles.safePath(session, relative, true), backup = path.join(temporary, "previous");
  const existed = fs.existsSync(destination);
  if (existed) fs.renameSync(destination, backup);
  try { fs.renameSync(candidateRoot, destination); }
  catch (error) { if (existed) fs.renameSync(backup, destination); throw error; }
  // Backups stay in temp until explicitly cleaned. Retirement never removes unrelated drafts.
  for (const item of retire) {
    const file = path.join(pendingDirectory, item.name);
    if (fileDigest(file) !== item.digest) fail("Local draft changed during refresh; Snapshot installed, draft preserved for reconciliation.");
    writeJsonAtomic(file, item.remaining);
  }
  const document = stateFiles.session(session);
  document.value.refresh_required = (document.value.refresh_required ?? []).filter((entry) => entry.area !== options.area || entry.owner_tenant_id !== owner.id);
  stateFiles.write(session, ".atlas/session.json", document.value, document.digest);
  return {snapshot_id: candidate.manifest.snapshot_id, area: options.area, owner_tenant_id: owner.id,
    model_revision: candidate.manifest.model_revision ?? null, dataset_count: candidate.datasets.length, backup: existed ? path.relative(session, backup) : null};
}

function recordOperation(options) {
  const session = requireSessionPath(options.session), state = readSessionState(session), owner = stateFiles.owner(state, options.area, options.owner);
  const document = stateFiles.operation(session, state, options.area, owner), operation = document.value;
  if (!operation.draft) fail("Operation has no bound server draft.");
  const response = readJsonFile(path.resolve(options.file ?? ""), "Governed operation result");
  const changeId = response.metadata_change_set_id ?? response.model_change_set_id;
  if (changeId !== operation.draft.id || response.draft_revision !== operation.draft.revision ||
      (options.area === "metadata" ? response.tenant_id !== owner.id : response.model_id !== state.model?.id)) fail("Server result does not match the bound owner/draft/revision.");
  if (!operation.stage || operation.stage.status !== "staged" || operation.stage.fingerprintVerified !== true || operation.stage.acceptedDigest !== operation.local_digest || operation.stage.changeSetId !== operation.draft.id || operation.stage.resultingRevision !== operation.draft.revision || !stateFiles.digest.test(operation.stage.stageFingerprint ?? "") || operation.stage_attempt?.status === "unknown") fail("Resolve and verify Stage before recording server validation or Apply.");
  if (operation.apply && options.checkpoint !== "apply") fail("Applied operation evidence cannot return to an earlier checkpoint.");
  if (options.checkpoint === "apply-approval") {
    const context = changeSetContext({...options, task: operation.task_id});
    if (workspaceDigest(context) !== operation.local_digest) fail("Local work changed after review; reconcile it before Apply approval.");
    assertOperationInputs(session, operation);
  }
  if (options.checkpoint === "validation") {
    if (typeof response.valid !== "boolean" || (response.valid && (!stateFiles.digest.test(response.candidate_digest ?? "") || response.status !== "validated")) || !["active", "validated"].includes(response.status)) fail("Invalid server validation result.");
    const relative = `.atlas/tasks/${operation.task_id}.evidence/${operation.id}.server-validation.json`;
    const saved = {schema_version: response.schema_version, area: options.area, owner_tenant_id: owner.id,
      change_set_id: changeId, draft_revision: response.draft_revision, valid: response.valid, status: response.status,
      candidate_digest: response.candidate_digest, error_count: response.error_count,
      action_review: response.action_review, validated_at: response.validated_at, expires_at: response.expires_at};
    const existing = fs.existsSync(stateFiles.safePath(session, relative));
    stateFiles.write(session, relative, saved, existing ? stateFiles.read(session, relative).digest : "absent");
    operation.server_validation = {path: relative, sha256: stateFiles.read(session, relative).digest, valid: response.valid,
      candidate_digest: response.candidate_digest, revision: response.draft_revision};
    operation.draft.status = response.status;
    operation.draft.validation_failed = !response.valid;
  } else if (options.checkpoint === "apply-approval") {
    if (!operation.server_validation?.valid || options["review-digest"] !== operation.server_validation.sha256) fail("Separate Apply acknowledgement must bind the current complete server review.");
    if (stateFiles.read(session, operation.server_validation.path).digest !== operation.server_validation.sha256) fail("Server review changed.");
    operation.apply_approval = {source: "conversation", at: new Date().toISOString(), review_sha256: operation.server_validation.sha256,
      revision: operation.draft.revision, candidate_digest: operation.server_validation.candidate_digest};
  } else if (options.checkpoint === "apply") {
    if (response.applied !== true || response.status !== "applied" || (options.area === "metadata" && response.valid !== true) || !operation.apply_approval ||
        response.candidate_digest !== operation.apply_approval.candidate_digest) fail("Apply result does not match a separately approved validated candidate.");
    operation.apply = {applied: true, status: "applied", draft_revision: response.draft_revision,
      candidate_digest: response.candidate_digest, applied_at: response.applied_at, action_count: response.action_count,
      ...(response.model_revision !== undefined ? {model_revision: response.model_revision} : {})};
  } else fail("Checkpoint must be validation, apply-approval or apply.");
  stateFiles.write(session, document.relative, operation, document.digest);
  if (operation.apply) {
    const latest = stateFiles.session(session);
    latest.value.refresh_required ??= [];
    if (!latest.value.refresh_required.some((entry) => entry.area === options.area && entry.owner_tenant_id === owner.id)) {
      latest.value.refresh_required.push({area: options.area, owner_tenant_id: owner.id, reason: "Applied changes require a fresh Snapshot.", evidence: document.relative});
    }
    stateFiles.write(session, ".atlas/session.json", latest.value, latest.digest);
  }
  return {operation: operation.id, checkpoint: options.checkpoint, refresh_required: Boolean(operation.apply)};
}

function importProfileResults(options) {
  const context = changeSetContext({...options, area: "model"});
  assertExpectedDigest(options, context);
  const planPath = path.resolve(options["plan-file"] ?? "");
  if (!planPath.startsWith(`${context.session}${path.sep}`)) fail("Profiling plan must be inside this workspace.");
  stateFiles.safePath(context.session, path.relative(context.session, planPath).split(path.sep).join("/"));
  const plan = readJsonFile(planPath, "Profiling plan");
  if (plan.schema_version !== "1.0" || plan.kind !== "profiling" || plan.task !== context.taskId || !Array.isArray(plan.queries) || !Array.isArray(plan.inputs)) fail("Profiling plan/task mismatch.");
  const applied = loadAppliedMetadata(context), currentInputs = [snapshotBinding(context), ...applied.inputs];
  if (applied.missingMetadataOwners.length || plan.inputs.length !== currentInputs.length ||
      currentInputs.some((input) => !plan.inputs.some((saved) => stableStringify(saved) === stableStringify(input)))) fail("Profiling plan must bind the complete current Snapshot inputs.");
  const indexesByObject = new Map();
  for (const query of plan.queries) {
    if (!stateFiles.object(query) || !/^[0-9]{4,}\.sql$/.test(query.file ?? "") || !stateFiles.digest.test(query.sha256 ?? "") ||
        !Array.isArray(query.attributes) || !query.attributes.length || query.attributes.length > 50 || query.expected_row_count !== query.attributes.length ||
        !Number.isSafeInteger(query.connection_id) || query.connection_id < 1 || query.environment !== plan.environment || !["dev", "qa", "stg", "prod"].includes(query.environment)) fail("Invalid profiling query manifest.");
    const objectKey = stableStringify(query.object), seen = indexesByObject.get(objectKey) ?? new Set();
    for (const attribute of query.attributes) {
      if (!Number.isSafeInteger(attribute.attribute_index) || attribute.attribute_index < 1 || seen.has(attribute.attribute_index) ||
          Object.entries(query.object ?? {}).some(([field, value]) => attribute[field] !== value)) fail("Profiling Attribute identity/coverage mismatch.");
      seen.add(attribute.attribute_index);
    }
    indexesByObject.set(objectKey, seen);
  }
  for (const input of plan.inputs ?? []) {
    if (fileDigest(stateFiles.safePath(context.session, input.manifest_path)) !== input.manifest_sha256) fail("Profiling inputs changed.");
  }
  const results = readJsonFile(path.resolve(options["results-file"] ?? ""), "Profiling aggregate results");
  if (!Array.isArray(results) || results.length !== plan.queries.length) fail("Every planned query needs one complete aggregate result.");
  const profileDefinition = context.byName.get("profiling_profile");
  if (!profileDefinition) fail("Snapshot has no Profiling Profile dataset.");
  const profileSchema = datasetSchema(context, profileDefinition);
  const profileTypes = require("./profiling.js");
  const physicalAttributes = new Map([...(applied.metadata.get("source_attribute")?.baseline ?? []), ...(applied.metadata.get("bronze_attribute")?.baseline ?? [])]
    .filter((row) => row.is_active !== false).map((row) => [profileTypes.attributeKey(row), row]));
  const scope = context.byName.get("model_input_scope");
  const scopedObjects = new Set((scope ? readSnapshotRecords(context, scope) : []).filter((row) => row.is_active !== false).map((row) => profileTypes.key(row)));
  const rows = [], counts = new Map(), seenFiles = new Set();
  const metricNames = ["row_count", "non_null_count", "null_count", "blank_count", "distinct_count", "min_data_length", "max_data_length", "avg_data_length", "percent_populated", "percent_duplicates", "percent_null", "percent_blank", "percent_distinct"];
  const evidence = [];
  for (const query of plan.queries) {
    const result = results.find((item) => item.file === query.file);
    if (!result || seenFiles.has(query.file) || result.truncated === true || !Array.isArray(result.rows) || result.rows.length !== query.attributes.length ||
        result.connection_id !== query.connection_id || result.environment !== query.environment || typeof result.executed_at !== "string" || !Number.isFinite(Date.parse(result.executed_at))) fail("Profiling execution binding/coverage mismatch.");
    seenFiles.add(query.file);
    const sqlFile = path.join(path.dirname(planPath), query.file);
    stateFiles.safePath(context.session, path.relative(context.session, sqlFile).split(path.sep).join("/"));
    if (fileDigest(sqlFile) !== query.sha256) fail("Profiling SQL changed after planning.");
    const indexes = new Set();
    for (const row of result.rows) {
      if (!stateFiles.object(row) || Object.keys(row).some((name) => !["attribute_index", ...metricNames].includes(name)) || metricNames.some((name) => !Object.hasOwn(row, name))) fail("Profiling result columns must match the fixed aggregate contract.");
      const key = query.attributes.find((attribute) => attribute.attribute_index === row.attribute_index);
      if (!key || indexes.has(row.attribute_index)) fail("Profiling result has an unknown or duplicate Attribute index.");
      indexes.add(row.attribute_index);
      const {attribute_index: _index, ...identity} = key;
      const record = {...identity, ...Object.fromEntries(metricNames.map((name) => [name, row[name]]))};
      const issues = schemaIssues(record, profileSchema);
      if (issues.length) fail(`Profiling metrics fail the record schema: ${issues[0]}`);
      const physicalAttribute = physicalAttributes.get(profileTypes.attributeKey(record));
      if (!physicalAttribute || !scopedObjects.has(profileTypes.key(record))) fail("Profile Attribute must exist in active applied Model Input Scope.");
      const type = profileTypes.normalizedType(physicalAttribute.attribute_data_type);
      const stringMetric = profileTypes.stringType.test(type), distinctMetric = stringMetric || profileTypes.scalarType.test(type);
      for (const field of ["row_count", "non_null_count", "null_count", "blank_count", "distinct_count"]) {
        if (record[field] !== null && !Number.isSafeInteger(record[field])) fail("Profile counts exceed exact local integer precision.");
      }
      if (!stringMetric && ["blank_count", "min_data_length", "max_data_length", "avg_data_length", "percent_blank"].some((field) => record[field] !== null) ||
          !distinctMetric && ["distinct_count", "percent_duplicates", "percent_distinct"].some((field) => record[field] !== null)) fail("Profile metrics do not match the registered physical type.");
      const ratio = (numerator, denominator) => denominator === 0 ? 0 : Math.round(1000000 * numerator / denominator) / 10000;
      for (const [field, numerator, denominator, applicable] of [
        ["percent_populated", record.non_null_count, record.row_count, true],
        ["percent_null", record.null_count, record.row_count, true],
        ["percent_blank", record.blank_count, record.non_null_count, stringMetric],
        ["percent_distinct", record.distinct_count, record.non_null_count, distinctMetric],
        ["percent_duplicates", record.non_null_count - record.distinct_count, record.non_null_count, distinctMetric],
      ]) if (applicable && (record[field] === null || numerator === null || Math.abs(Number(record[field]) - ratio(numerator, denominator)) > 0.000001)) fail("Profile percentages do not reconcile with their counts.");
      if (record.row_count !== record.non_null_count + record.null_count || record.distinct_count !== null && record.distinct_count > record.non_null_count || record.blank_count !== null && record.blank_count > record.non_null_count) fail("Profiling metric counts are inconsistent.");
      const objectKey = stableStringify(query.object);
      if (counts.has(objectKey) && counts.get(objectKey) !== record.row_count) fail("Attribute groups observed different Object row counts; rerun instead of combining.");
      counts.set(objectKey, record.row_count);
      rows.push(record);
    }
    evidence.push({object: query.object, sql_sha256: query.sha256, connection_id: query.connection_id, environment: query.environment,
      executed_at: result.executed_at, batch_ids: query.batch_ids, attribute_count: query.attributes.length});
  }
  let expected = options["expected-digest"];
  for (let index = 0; index < rows.length; index += 200) {
    const result = upsertBatch({...options, area: "model", changes: JSON.stringify({profiling_profile: rows.slice(index, index + 200)}), "expected-digest": expected});
    expected = result.digest;
  }
  const relative = `.atlas/tasks/${context.taskId}.evidence/profiling-${crypto.randomUUID()}.json`;
  stateFiles.write(context.session, relative, {schema_version: "1.0", inputs: plan.inputs, coverage: evidence});
  return {profiles: rows.length, digest: expected, evidence: relative};
}
