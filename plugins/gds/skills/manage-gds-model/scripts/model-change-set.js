#!/usr/bin/env node

"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { TextEncoder } = require("node:util");

const DATASETS = Object.freeze([
  "model_details", "model_scope", "profiling_profile", "analysis_result",
  "modeling_assertion_document", "modeling_assertion_record",
  "conceptual_object", "conceptual_relationship", "logical_submodel",
  "logical_entity", "logical_attribute", "logical_relationship",
  "dimensional_submodel", "dimensional_entity", "dimensional_attribute",
  "dimensional_relationship", "mapping_dependency", "mapping_object",
  "mapping_attribute"
]);
const DATASET_SET = new Set(DATASETS);
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const ROOT_ENTRIES = new Set(["model-change-set.json", "datasets", "stage-review.json"]);

function fail(message) {
  process.stderr.write("ok=false\n");
  process.stderr.write(`error=${String(message).replace(/[\r\n]+/g, " ")}\n`);
  process.exitCode = 2;
}

function output(name, value) {
  process.stdout.write(`${name}=${value}\n`);
}

function parseArguments(values) {
  const options = new Map();
  for (let index = 0; index < values.length; index += 1) {
    const name = values[index];
    if (!name.startsWith("--")) throw new Error(`Unexpected argument: ${name}.`);
    const value = values[index + 1];
    if (value === undefined || value.startsWith("--")) throw new Error(`Missing value for ${name}.`);
    if (options.has(name) && name !== "--server-dataset-count") {
      throw new Error(`Option supplied more than once: ${name}.`);
    }
    if (name === "--server-dataset-count") {
      const existing = options.get(name) || [];
      existing.push(value);
      options.set(name, existing);
    } else {
      options.set(name, value);
    }
    index += 1;
  }
  return options;
}

function take(options, name, required = true) {
  const value = options.get(name);
  if (required && (value === undefined || value === "")) throw new Error(`${name} is required.`);
  return value;
}

function assertNoUnknown(options, allowed) {
  for (const name of options.keys()) {
    if (!allowed.has(name)) throw new Error(`Unknown option: ${name}.`);
  }
}

function positiveInteger(value, label) {
  if (!/^[1-9][0-9]*$/.test(String(value))) throw new Error(`${label} must be a positive integer.`);
  const number = Number(value);
  if (!Number.isSafeInteger(number)) throw new Error(`${label} is too large.`);
  return number;
}

function booleanValue(value, label) {
  if (value !== "true" && value !== "false") throw new Error(`${label} must be true or false.`);
  return value === "true";
}

function uuid(value, label) {
  if (!UUID_PATTERN.test(String(value))) throw new Error(`${label} must be a UUID.`);
  return String(value).toLocaleLowerCase("en-US");
}

function serverStatus(value) {
  if (value !== "active" && value !== "validated") {
    throw new Error("Server status must be active or validated.");
  }
  return value;
}

function readJson(file, label) {
  let text;
  try {
    text = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "");
  } catch (_) {
    throw new Error(`${label} cannot be read.`);
  }
  try {
    return JSON.parse(text);
  } catch (_) {
    throw new Error(`${label} is not valid JSON.`);
  }
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function assertRegularFile(file, label) {
  let stat;
  try {
    stat = fs.lstatSync(file);
  } catch (_) {
    throw new Error(`${label} is missing.`);
  }
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(`${label} must be a regular file.`);
  }
  return stat;
}

function assertDirectory(directory, label) {
  let stat;
  try {
    stat = fs.lstatSync(directory);
  } catch (_) {
    throw new Error(`${label} is missing.`);
  }
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`${label} must be a real directory.`);
  }
}

function resolveWorkspace(changeSetInput) {
  const candidate = path.resolve(changeSetInput);
  if (path.basename(candidate) !== "model-change-set") {
    throw new Error("Local directory must be named model-change-set.");
  }
  assertDirectory(candidate, "Local Model Change Set");
  const workspace = path.dirname(candidate);
  if (path.basename(workspace) !== "GDS") {
    throw new Error("Local Model Change Set must be directly under GDS.");
  }
  assertDirectory(workspace, "GDS workspace");
  const snapshot = path.join(workspace, "model-snapshot");
  const stateFile = path.join(candidate, "model-change-set.json");
  const datasetsDirectory = path.join(candidate, "datasets");
  assertDirectory(snapshot, "Referenced model-snapshot");
  assertRegularFile(stateFile, "model-change-set.json");
  assertDirectory(datasetsDirectory, "Model Change Set datasets directory");

  for (const entry of fs.readdirSync(candidate, { withFileTypes: true })) {
    if (!ROOT_ENTRIES.has(entry.name)) {
      throw new Error(`Unexpected Model Change Set root entry: ${entry.name}.`);
    }
    const stat = fs.lstatSync(path.join(candidate, entry.name));
    if (stat.isSymbolicLink()) {
      throw new Error("Local Model Change Set cannot contain symbolic links.");
    }
  }
  for (const entry of fs.readdirSync(datasetsDirectory, { withFileTypes: true })) {
    if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(".json")) {
      throw new Error("Model Change Set datasets may contain only regular JSON files.");
    }
    const dataset = entry.name.slice(0, -5);
    if (!DATASET_SET.has(dataset)) {
      throw new Error(`Dataset is not Model Change Set eligible: ${dataset}.`);
    }
  }
  return { changeSet: candidate, workspace, snapshot, stateFile, datasetsDirectory };
}

function safeSnapshotPath(snapshot, relativePath) {
  if (typeof relativePath !== "string" || !relativePath ||
      relativePath.includes("\\") || path.isAbsolute(relativePath)) {
    throw new Error("Model Snapshot manifest contains an unsafe member path.");
  }
  const parts = relativePath.split("/");
  if (parts.some((part) => !part || part === "." || part === ".." ||
      part.includes(":"))) {
    throw new Error("Model Snapshot manifest contains an unsafe member path.");
  }
  let parent = path.resolve(snapshot);
  for (const part of parts.slice(0, -1)) {
    parent = path.join(parent, part);
    let stat;
    try {
      stat = fs.lstatSync(parent);
    } catch (_) {
      throw new Error("Model Snapshot member parent directory is missing.");
    }
    if (!stat.isDirectory() || stat.isSymbolicLink()) {
      throw new Error(
        "Model Snapshot member path cannot traverse a symbolic link."
      );
    }
  }
  const resolved = path.resolve(snapshot, ...parts);
  if (!resolved.startsWith(`${path.resolve(snapshot)}${path.sep}`)) {
    throw new Error("Model Snapshot manifest contains an unsafe member path.");
  }
  return resolved;
}

function manifestMembers(snapshot, manifest) {
  if (!Array.isArray(manifest.members)) {
    throw new Error("Model Snapshot manifest has no member inventory.");
  }
  const members = new Map();
  for (const member of manifest.members) {
    if (!isObject(member) || typeof member.path !== "string" ||
        typeof member.sha256 !== "string" ||
        !SHA256_PATTERN.test(member.sha256) ||
        !Number.isInteger(member.size_bytes) || member.size_bytes < 0 ||
        members.has(member.path)) {
      throw new Error("Model Snapshot manifest member inventory is invalid.");
    }
    safeSnapshotPath(snapshot, member.path);
    members.set(member.path, member);
  }
  return members;
}

function readVerifiedMember(snapshot, members, relativePath, label) {
  const member = members.get(relativePath);
  if (!member) {
    throw new Error(`${label} is not authorized by the Snapshot manifest.`);
  }
  const file = safeSnapshotPath(snapshot, relativePath);
  const stat = assertRegularFile(file, label);
  if (stat.size !== member.size_bytes) {
    throw new Error(`${label} does not match its Snapshot size.`);
  }
  const content = fs.readFileSync(file);
  const digest = crypto.createHash("sha256").update(content).digest("hex");
  if (digest !== member.sha256) {
    throw new Error(`${label} does not match its Snapshot SHA-256.`);
  }
  return content.toString("utf8").replace(/^\uFEFF/, "");
}

function loadLogic() {
  const logicFile = path.resolve(
    __dirname,
    "../../open-gds-metadata-workbench/assets/workbench/logic.js"
  );
  assertRegularFile(logicFile, "Bundled Workbench logic");
  const context = { TextEncoder };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(logicFile, "utf8"), context, { filename: logicFile });
  if (!context.GdsWorkbenchLogic) {
    throw new Error("Bundled Workbench logic did not load.");
  }
  return context.GdsWorkbenchLogic;
}

function loadWorkspace(changeSetInput) {
  const locations = resolveWorkspace(changeSetInput);
  const logic = loadLogic();
  const manifestFile = path.join(locations.snapshot, "manifest.json");
  assertRegularFile(manifestFile, "Model Snapshot manifest");
  const manifest = readJson(manifestFile, "Model Snapshot manifest");
  const members = manifestMembers(locations.snapshot, manifest);
  if (manifest.catalog?.path !== "catalog.json" ||
      manifest.catalog?.sha256 !== members.get("catalog.json")?.sha256) {
    throw new Error("Model Snapshot catalog manifest entry is invalid.");
  }
  let catalog;
  try {
    catalog = JSON.parse(
      readVerifiedMember(
        locations.snapshot,
        members,
        "catalog.json",
        "Model Snapshot catalog"
      )
    );
  } catch (error) {
    if (error && typeof error.message === "string" &&
        error.message.startsWith("Model Snapshot catalog")) {
      throw error;
    }
    throw new Error("Model Snapshot catalog is not valid JSON.");
  }
  const state = readJson(locations.stateFile, "model-change-set.json");
  validateIdentity(state, manifest, catalog);
  return { ...locations, logic, manifest, members, catalog, state };
}

function validateIdentity(state, manifest, catalog) {
  if (!isObject(manifest) || manifest.schema_version !== "2.0" ||
      manifest.snapshot_kind !== "model" || typeof manifest.snapshot_id !== "string" ||
      !Number.isInteger(manifest.model_id) || manifest.model_id <= 0 ||
      typeof manifest.model_name !== "string" || !manifest.model_name.trim() ||
      !Number.isInteger(manifest.model_revision) || manifest.model_revision <= 0) {
    throw new Error("Model Snapshot manifest identity is invalid.");
  }
  if (!isObject(catalog) || catalog.schema_version !== "2.0" ||
      catalog.snapshot_kind !== "model" ||
      catalog.model?.model_id !== manifest.model_id ||
      catalog.model?.model_name !== manifest.model_name ||
      catalog.model?.model_revision !== manifest.model_revision ||
      !Array.isArray(catalog.sections)) {
    throw new Error("Model Snapshot catalog identity is invalid.");
  }
  if (!isObject(state) || state.format_version !== "1.0" ||
      state.model?.model_id !== manifest.model_id ||
      state.model?.model_name !== manifest.model_name ||
      state.model?.model_revision !== manifest.model_revision ||
      state.snapshot?.snapshot_id !== manifest.snapshot_id ||
      state.snapshot?.path !== "../model-snapshot" ||
      !isObject(state.server_change_set) || !isObject(state.datasets)) {
    throw new Error("Local Model Change Set identity does not match its Snapshot.");
  }
  const status = state.server_change_set.status;
  if (!["local", "active", "validated"].includes(status)) {
    throw new Error("Local server status is invalid.");
  }
  const id = state.server_change_set.model_change_set_id;
  const revision = state.server_change_set.draft_revision;
  const bound = id !== null && id !== undefined;
  if (bound !== (revision !== null && revision !== undefined) ||
      (bound && (!UUID_PATTERN.test(String(id)) ||
        !Number.isInteger(revision) || revision <= 0 || status === "local")) ||
      (!bound && status !== "local")) {
    throw new Error("Model Change Set ID, revision, and status are inconsistent.");
  }
}

function catalogDatasets(workspace) {
  const index = new Map();
  for (const section of workspace.catalog.sections) {
    if (!isObject(section) || !Array.isArray(section.datasets)) {
      throw new Error("Model Snapshot catalog sections are invalid.");
    }
    for (const item of section.datasets) {
      if (!isObject(item) || !DATASET_SET.has(item.name) || index.has(item.name) ||
          typeof item.schema_file !== "string" || typeof item.rows_file !== "string") {
        throw new Error("Model Snapshot catalog dataset inventory is invalid.");
      }
      index.set(item.name, item);
    }
  }
  if (index.size !== DATASETS.length) {
    throw new Error("Model Snapshot catalog must contain all 19 Model datasets.");
  }
  return index;
}

function sha256(text) {
  return crypto.createHash("sha256").update(text, "utf8").digest("hex");
}

function stable(value) {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (isObject(value)) {
    return `{${Object.keys(value).sort().map(
      (key) => `${JSON.stringify(key)}:${stable(value[key])}`
    ).join(",")}}`;
  }
  return JSON.stringify(value);
}

function keyFor(record, schema, logic) {
  return JSON.stringify(logic.canonicalColumns(schema).map((column) => {
    const value = record[column];
    return [
      value === null ? "null" : typeof value,
      logic.normalizeKeyValue(column, value, schema)
    ];
  }));
}

function readDataset(file, dataset, schema, logic) {
  assertRegularFile(file, `${dataset}.json`);
  const text = fs.readFileSync(file, "utf8");
  const records = logic.parseRows(text, `${dataset}.json`);
  const errors = logic.validateDataset(records, schema);
  if (errors.length) {
    const first = errors[0];
    const row = first.row === null || first.row === undefined
      ? ""
      : ` row ${first.row + 1}`;
    throw new Error(
      `${dataset}${row} is invalid at ${first.field}: ${first.message}`
    );
  }
  return {
    records,
    text,
    bytes: Buffer.byteLength(text, "utf8"),
    digest: sha256(text)
  };
}

function loadDatasetInputs(workspace) {
  const catalog = catalogDatasets(workspace);
  const inputs = new Map();
  let total = 0;
  for (const fileName of fs.readdirSync(workspace.datasetsDirectory).sort()) {
    const dataset = fileName.slice(0, -5);
    const catalogItem = catalog.get(dataset);
    let schema;
    try {
      schema = JSON.parse(readVerifiedMember(
        workspace.snapshot,
        workspace.members,
        catalogItem.schema_file,
        `${dataset} Snapshot schema`
      ));
    } catch (error) {
      if (error && typeof error.message === "string" &&
          error.message.startsWith(`${dataset} Snapshot schema`)) {
        throw error;
      }
      throw new Error(`${dataset} Snapshot schema is not valid JSON.`);
    }
    workspace.logic.validateSchema(schema, dataset, true);
    const value = readDataset(
      path.join(workspace.datasetsDirectory, fileName),
      dataset,
      schema,
      workspace.logic
    );
    total += value.records.length;
    inputs.set(dataset, { ...value, schema, catalogItem });
  }
  if (!inputs.size) throw new Error("At least one local Model dataset is required.");
  if (total > workspace.logic.MAX_MODEL_TOTAL_RECORDS) {
    throw new Error("Local Model Change Set exceeds 50,000 total records.");
  }
  return inputs;
}

function snapshotRows(workspace, input) {
  const records = workspace.logic.parseRows(
    readVerifiedMember(
      workspace.snapshot,
      workspace.members,
      input.catalogItem.rows_file,
      `${input.catalogItem.name} Snapshot rows`
    ),
    input.catalogItem.rows_file
  );
  const errors = workspace.logic.validateDataset(records, input.schema);
  if (errors.length) {
    throw new Error(
      `${input.catalogItem.name} Snapshot rows do not match their schema.`
    );
  }
  return records;
}

function writeJsonAtomic(file, value) {
  const temporary = `${file}.${crypto.randomUUID()}.tmp`;
  fs.writeFileSync(
    temporary,
    `${JSON.stringify(value, null, 2)}\n`,
    { encoding: "utf8", flag: "wx", mode: 0o600 }
  );
  fs.renameSync(temporary, file);
}

function bind(options) {
  assertNoUnknown(options, new Set([
    "--change-set", "--model-id", "--current-model-revision",
    "--model-change-set-id", "--draft-revision", "--server-status",
    "--created", "--server-draft"
  ]));
  const workspace = loadWorkspace(take(options, "--change-set"));
  const modelId = positiveInteger(take(options, "--model-id"), "Model ID");
  const currentModelRevision = positiveInteger(
    take(options, "--current-model-revision"),
    "Current Model revision"
  );
  const changeSetId = uuid(
    take(options, "--model-change-set-id"),
    "Model Change Set ID"
  );
  const draftRevision = positiveInteger(
    take(options, "--draft-revision"),
    "Draft revision"
  );
  const status = serverStatus(take(options, "--server-status"));
  const created = booleanValue(take(options, "--created"), "Created");
  const serverDraftFile = take(options, "--server-draft", false);
  if (workspace.state.server_change_set.status !== "local") {
    throw new Error(
      "Local Model Change Set is already bound; use the state-recording commands."
    );
  }
  if (modelId !== workspace.manifest.model_id) {
    throw new Error("Model ID does not match the local Snapshot.");
  }
  if (currentModelRevision !== workspace.manifest.model_revision) {
    throw new Error(
      "Current Model revision differs from the local Snapshot baseline; rebase before binding."
    );
  }
  if (created && serverDraftFile) {
    throw new Error(
      "A newly created server draft must not supply resumed-draft data."
    );
  }
  if (!created && !serverDraftFile) {
    throw new Error(
      "A resumed server draft requires --server-draft after every nonempty server dataset is fetched and reconciled."
    );
  }
  const inputs = loadDatasetInputs(workspace);
  if (!created) {
    verifyResumedDraft(workspace, inputs, serverDraftFile, {
      modelId, changeSetId, draftRevision, status
    });
  }
  if (Object.keys(workspace.state.datasets).length) {
    throw new Error("Unbound local state cannot contain server Stage markers.");
  }
  workspace.state.snapshot.usage = "fresh";
  workspace.state.snapshot.outdated_snapshot_warning_acknowledged = false;
  workspace.state.server_change_set = {
    model_change_set_id: changeSetId,
    draft_revision: draftRevision,
    status
  };
  writeJsonAtomic(workspace.stateFile, workspace.state);
  output("ok", "true");
  output("change_set", workspace.changeSet);
  output("model_id", modelId);
  output("model_change_set_id", changeSetId);
  output("draft_revision", draftRevision);
  output("server_status", status);
  output("adopted_local_draft", "true");
  output("resumed_server_draft_verified", String(!created));
  output("dataset_count", inputs.size);
}

function verifyResumedDraft(workspace, inputs, serverDraftFile, expected) {
  const resolved = path.resolve(serverDraftFile);
  assertRegularFile(resolved, "Normalized resumed server draft");
  const draft = readJson(resolved, "Normalized resumed server draft");
  if (!isObject(draft) || draft.schema_version !== "1.0" ||
      draft.model_id !== expected.modelId ||
      String(draft.model_change_set_id).toLocaleLowerCase("en-US") !==
        expected.changeSetId ||
      draft.draft_revision !== expected.draftRevision ||
      draft.status !== expected.status || !Array.isArray(draft.dataset_counts) ||
      !isObject(draft.datasets)) {
    throw new Error("Normalized resumed server draft identity is invalid.");
  }
  const counts = new Map();
  for (const item of draft.dataset_counts) {
    if (!isObject(item) || !DATASET_SET.has(item.dataset) ||
        counts.has(item.dataset) || !Number.isInteger(item.record_count) ||
        item.record_count < 0) {
      throw new Error("Normalized resumed server draft counts are invalid.");
    }
    counts.set(item.dataset, item.record_count);
  }
  for (const name of Object.keys(draft.datasets)) {
    if (!DATASET_SET.has(name) || !counts.has(name) ||
        counts.get(name) === 0 || !Array.isArray(draft.datasets[name])) {
      throw new Error(`Unexpected resumed server dataset: ${name}.`);
    }
  }
  for (const [dataset, count] of counts) {
    if (count === 0) continue;
    const serverRecords = draft.datasets[dataset];
    if (!Array.isArray(serverRecords) || serverRecords.length !== count) {
      throw new Error(
        `Resumed server dataset is missing or incomplete: ${dataset}.`
      );
    }
    const input = inputs.get(dataset);
    if (!input) {
      throw new Error(
        `Local draft has not reconciled resumed server dataset: ${dataset}.`
      );
    }
    const errors = workspace.logic.validateDataset(serverRecords, input.schema);
    if (errors.length) {
      throw new Error(
        `Resumed server dataset does not match the Snapshot schema: ${dataset}.`
      );
    }
    const localByKey = new Map(input.records.map(
      (record) => [keyFor(record, input.schema, workspace.logic), record]
    ));
    for (const record of serverRecords) {
      const key = keyFor(record, input.schema, workspace.logic);
      const local = localByKey.get(key);
      if (!local || stable(local) !== stable(record)) {
        throw new Error(
          `Local draft has not preserved a resumed server record in ${dataset}.`
        );
      }
    }
  }
}

function validate(options, requireBound = false, requireReviewed = false,
  requireStaged = false) {
  assertNoUnknown(options, new Set(["--change-set"]));
  const workspace = loadWorkspace(take(options, "--change-set"));
  const inputs = loadDatasetInputs(workspace);
  const bound = workspace.state.server_change_set.status !== "local";
  if (requireBound && !bound) {
    throw new Error("Local Model Change Set must be bound before Stage review.");
  }
  let staged = 0;
  for (const [dataset, input] of inputs) {
    const marker = workspace.state.datasets[dataset];
    const synchronized = isObject(marker) &&
      marker.file === `datasets/${dataset}.json` &&
      marker.record_count === input.records.length &&
      marker.staged_sha256 === input.digest &&
      Number.isInteger(marker.staged_revision) && marker.staged_revision > 0 &&
      marker.staged_revision <=
        workspace.state.server_change_set.draft_revision;
    if (synchronized) staged += 1;
    if (requireStaged && !synchronized) {
      throw new Error(
        `Dataset is not synchronized with a successful Stage: ${dataset}.`
      );
    }
  }
  let reviewed = false;
  const reviewFile = path.join(workspace.changeSet, "stage-review.json");
  if (fs.existsSync(reviewFile)) {
    reviewed = reviewMatches(
      workspace,
      inputs,
      readJson(reviewFile, "Model Stage review")
    );
  }
  if (requireReviewed && !reviewed) {
    throw new Error(
      "Model Stage review is missing or stale; prepare it again before Stage approval."
    );
  }
  output("ok", "true");
  output("change_set", workspace.changeSet);
  output("model_id", workspace.manifest.model_id);
  output(
    "model_change_set_id",
    bound ? workspace.state.server_change_set.model_change_set_id : "unbound"
  );
  output(
    "draft_revision",
    bound ? workspace.state.server_change_set.draft_revision : "unbound"
  );
  output("server_status", workspace.state.server_change_set.status);
  for (const [dataset, input] of inputs) {
    output(
      "dataset",
      `${dataset}|${input.records.length}|${input.bytes}|${input.digest}`
    );
  }
  output("dataset_count", inputs.size);
  output("reviewed", String(reviewed));
  output("staged_dataset_count", staged);
  return { workspace, inputs };
}

function reviewMatches(workspace, inputs, review) {
  if (!isObject(review) || review.schema_version !== "1.0" ||
      review.model?.model_id !== workspace.manifest.model_id ||
      review.model?.model_revision !== workspace.manifest.model_revision ||
      review.snapshot_id !== workspace.manifest.snapshot_id ||
      review.server_change_set?.model_change_set_id !==
        workspace.state.server_change_set.model_change_set_id ||
      review.server_change_set?.draft_revision !==
        workspace.state.server_change_set.draft_revision ||
      !isObject(review.datasets) ||
      Object.keys(review.datasets).length !== inputs.size) {
    return false;
  }
  for (const [dataset, input] of inputs) {
    const item = review.datasets[dataset];
    if (!isObject(item) || item.file !== `datasets/${dataset}.json` ||
        item.record_count !== input.records.length ||
        item.size_bytes !== input.bytes || item.sha256 !== input.digest) {
      return false;
    }
  }
  return true;
}

function prepareStage(options) {
  const { workspace, inputs } = validate(options, true, false, false);
  const changes = {};
  const datasets = {};
  const totals = {
    insert: 0, update: 0, deactivate: 0, reactivate: 0, no_change: 0
  };
  for (const [dataset, input] of inputs) {
    const baseline = snapshotRows(workspace, input);
    const actions = {
      insert: 0, update: 0, deactivate: 0, reactivate: 0, no_change: 0
    };
    const keys = [];
    for (const record of input.records) {
      const action = workspace.logic.classifyRecord(
        record,
        baseline,
        input.schema
      );
      actions[action] += 1;
      totals[action] += 1;
      if (keys.length < 100) {
        keys.push({
          action,
          natural_key: Object.fromEntries(
            workspace.logic.canonicalColumns(input.schema).map(
              (field) => [field, record[field]]
            )
          )
        });
      }
    }
    datasets[dataset] = {
      file: `datasets/${dataset}.json`,
      record_count: input.records.length,
      size_bytes: input.bytes,
      sha256: input.digest,
      actions,
      keys,
      keys_truncated: input.records.length > keys.length
    };
    changes[dataset] = input.records;
  }
  const effective = totals.insert + totals.update +
    totals.deactivate + totals.reactivate;
  if (totals.no_change) {
    throw new Error(
      "Remove unchanged pending Model records before preparing Stage review."
    );
  }
  if (!effective) throw new Error("No effective Model change is present.");
  workspace.logic.modelStageDocument(
    workspace.manifest,
    workspace.state,
    changes
  );
  const review = {
    schema_version: "1.0",
    model: {
      model_id: workspace.manifest.model_id,
      model_name: workspace.manifest.model_name,
      model_revision: workspace.manifest.model_revision
    },
    snapshot_id: workspace.manifest.snapshot_id,
    server_change_set: {
      model_change_set_id:
        workspace.state.server_change_set.model_change_set_id,
      draft_revision: workspace.state.server_change_set.draft_revision,
      status: workspace.state.server_change_set.status
    },
    datasets,
    totals
  };
  const reviewFile = path.join(workspace.changeSet, "stage-review.json");
  writeJsonAtomic(reviewFile, review);
  output("stage_review", reviewFile);
  output("effective_record_count", effective);
  output("no_change_count", totals.no_change);
  output("stage_ready", "true");
}

function parseServerCounts(values) {
  const counts = new Map();
  for (const value of values || []) {
    const match = /^([a-z_]+)=([0-9]+)$/.exec(value);
    if (!match || !DATASET_SET.has(match[1]) || counts.has(match[1])) {
      throw new Error(
        "Each server dataset count must be one unique dataset=count pair."
      );
    }
    counts.set(match[1], Number(match[2]));
  }
  return counts;
}

function recordStage(options) {
  assertNoUnknown(options, new Set([
    "--change-set", "--model-change-set-id",
    "--expected-current-revision", "--server-revision",
    "--server-dataset-count"
  ]));
  const workspace = loadWorkspace(take(options, "--change-set"));
  const inputs = loadDatasetInputs(workspace);
  const changeSetId = uuid(
    take(options, "--model-change-set-id"),
    "Model Change Set ID"
  );
  const expected = positiveInteger(
    take(options, "--expected-current-revision"),
    "Expected current revision"
  );
  const serverRevision = positiveInteger(
    take(options, "--server-revision"),
    "Server revision"
  );
  const counts = parseServerCounts(options.get("--server-dataset-count"));
  if (workspace.state.server_change_set.model_change_set_id !== changeSetId) {
    throw new Error("Model Change Set ID does not match local state.");
  }
  if (workspace.state.server_change_set.draft_revision !== expected) {
    throw new Error("Expected revision does not match local state.");
  }
  if (serverRevision !== expected + 1) {
    throw new Error(
      "A successful Model Stage must increment revision by exactly one."
    );
  }
  const reviewFile = path.join(workspace.changeSet, "stage-review.json");
  assertRegularFile(reviewFile, "Model Stage review");
  const review = readJson(reviewFile, "Model Stage review");
  if (!reviewMatches(workspace, inputs, review)) {
    throw new Error(
      "Model Stage review is stale; prepare it again before recording Stage."
    );
  }
  if (counts.size !== inputs.size) {
    throw new Error(
      "Server Stage counts must cover every reviewed dataset exactly once."
    );
  }
  for (const [dataset, input] of inputs) {
    if (counts.get(dataset) !== input.records.length) {
      throw new Error(
        `Server Stage count does not match reviewed dataset: ${dataset}.`
      );
    }
  }
  workspace.state.server_change_set.draft_revision = serverRevision;
  workspace.state.server_change_set.status = "active";
  for (const [dataset, input] of inputs) {
    workspace.state.datasets[dataset] = {
      file: `datasets/${dataset}.json`,
      record_count: input.records.length,
      staged_sha256: input.digest,
      staged_revision: serverRevision
    };
  }
  writeJsonAtomic(workspace.stateFile, workspace.state);
  output("ok", "true");
  output("model_change_set_id", changeSetId);
  output("previous_revision", expected);
  output("draft_revision", serverRevision);
  output("server_status", "active");
  output("staged_dataset_count", inputs.size);
}

function recordValidation(options) {
  assertNoUnknown(options, new Set([
    "--change-set", "--model-change-set-id",
    "--expected-current-revision", "--server-revision", "--server-status"
  ]));
  const workspace = loadWorkspace(take(options, "--change-set"));
  const inputs = loadDatasetInputs(workspace);
  const changeSetId = uuid(
    take(options, "--model-change-set-id"),
    "Model Change Set ID"
  );
  const expected = positiveInteger(
    take(options, "--expected-current-revision"),
    "Expected current revision"
  );
  const serverRevision = positiveInteger(
    take(options, "--server-revision"),
    "Server revision"
  );
  const status = serverStatus(take(options, "--server-status"));
  if (workspace.state.server_change_set.model_change_set_id !== changeSetId) {
    throw new Error("Model Change Set ID does not match local state.");
  }
  if (workspace.state.server_change_set.draft_revision !== expected ||
      serverRevision !== expected) {
    throw new Error(
      "Validation must report the exact current draft revision."
    );
  }
  if (status === "validated") {
    for (const [dataset, input] of inputs) {
      const marker = workspace.state.datasets[dataset];
      if (!isObject(marker) || marker.staged_revision !== expected ||
          marker.staged_sha256 !== input.digest ||
          marker.record_count !== input.records.length) {
        throw new Error(
          `Validated state cannot be recorded before the local dataset matches Stage: ${dataset}.`
        );
      }
    }
  }
  workspace.state.server_change_set.status = status;
  writeJsonAtomic(workspace.stateFile, workspace.state);
  output("ok", "true");
  output("model_change_set_id", changeSetId);
  output("draft_revision", serverRevision);
  output("server_status", status);
  output("validation_recorded", "true");
}

function main() {
  const command = process.argv[2];
  if (![
    "bind", "validate", "prepare-stage", "record-stage", "record-validation"
  ].includes(command)) {
    throw new Error(
      "Usage: model-change-set.js <bind|validate|prepare-stage|record-stage|record-validation> [options]."
    );
  }
  const options = parseArguments(process.argv.slice(3));
  if (command === "bind") bind(options);
  else if (command === "validate") validate(options);
  else if (command === "prepare-stage") prepareStage(options);
  else if (command === "record-stage") recordStage(options);
  else recordValidation(options);
}

try {
  main();
} catch (error) {
  fail(
    error && typeof error.message === "string"
      ? error.message
      : "Model Change Set helper failed."
  );
}
