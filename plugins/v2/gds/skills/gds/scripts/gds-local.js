#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const crypto = require("node:crypto");
const childProcess = require("node:child_process");
const unicode = require("../workbench/unicode.js");
const workbenchCore = require("../workbench/core.js");
const workbenchCommon = require("../workbench/validation/common.js");
const workbenchAreas = {
  metadata: require("../workbench/metadata.js"),
  model: require("../workbench/model.js"),
};
const workbenchDbml = require("../workbench/dbml.js");

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

const HELPER_CONTRACT_PATH = path.resolve(__dirname, "..", "contracts", "local-helper.json");
const PREFERRED_STAGE_PAYLOAD_BYTES = 64 * 1024;
const DIRECT_STAGE_MAX_BYTES = PREFERRED_STAGE_PAYLOAD_BYTES;
const METADATA_STAGE_CHUNK_MAX_BYTES = 450 * 1024;
const MODEL_STAGE_RECORD_CHUNK_MAX_BYTES = 1024 * 1024;
const MODEL_STAGE_FRAGMENT_MAX_BYTES = 1024 * 1024;
const STAGE_CHUNK_MAX_RECORDS = 5000;
const STAGE_MAX_CHUNKS = 64;

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

function validationReportPath(session, area) {
  let current = session;
  for (const segment of ["reports", "local-validation"]) {
    current = path.join(current, segment);
    if (!fs.existsSync(current)) {
      fs.mkdirSync(current, { mode: 0o700 });
      continue;
    }
    const stat = fs.lstatSync(current);
    if (!stat.isDirectory() || stat.isSymbolicLink()) {
      fail("Local validation report directory must be a regular directory.");
    }
  }
  return path.join(current, `${area}.json`);
}

function writeValidationReport(context, validationIssues, output) {
  const manifestPath = path.join(context.root, "manifest.json");
  writeJsonAtomic(validationReportPath(context.session, optionsArea(context)), {
    schema_version: "1.0",
    area: optionsArea(context),
    run_by: "agent",
    generated_at: new Date().toISOString(),
    digest: output.digest,
    snapshot: {
      id: context.manifest.snapshot_id,
      revision: context.manifest.model_revision ?? null,
      manifest_digest: crypto.createHash("sha256").update(fs.readFileSync(manifestPath)).digest("hex"),
    },
    valid: output.valid,
    issue_count: validationIssues.length,
    truncated: output.truncated,
    issues: output.repairs.map((repair) => ({
      severity: "error",
      dataset: repair.dataset,
      record: repair.record,
      code: repair.code,
      fields: repair.fields,
      message: repair.message,
    })),
  });
}

function readManifest(filePath) {
  if (!fs.existsSync(filePath)) return { current: null, highest: 0 };
  const stat = fs.lstatSync(filePath);
  if (!stat.isFile() || stat.isSymbolicLink()) fail("Tenant manifest must be a regular file.");
  let value;
  try {
    value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    fail("Tenant manifest is not valid JSON.");
  }
  if (
    !value ||
    typeof value !== "object" ||
    !Number.isSafeInteger(value.highest) ||
    value.highest < 0 ||
    (value.current !== null && typeof value.current !== "string")
  ) {
    fail("Tenant manifest has an invalid shape.");
  }
  return value;
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

function requireSessionPath(sessionOption) {
  if (!sessionOption) fail("--session is required.");
  const session = path.resolve(sessionOption);
  const stat = fs.lstatSync(session);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    fail("Session must be a regular directory.");
  }
  if (!fs.existsSync(path.join(session, "session.json"))) {
    fail("Session does not contain session.json.");
  }
  return session;
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
  const resolved = path.resolve(root, ...relativePath.split("/"));
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

function locateSnapshot(options) {
  if (!new Set(["metadata", "model"]).has(options.area)) {
    fail("--area must be metadata or model.");
  }
  const session = requireSessionPath(options.session);
  const areaDirectory = path.join(session, options.area);
  if (!fs.existsSync(areaDirectory)) fail(`${options.area} Snapshot directory is missing.`);
  const candidates = [];
  const hasContract = (directory) =>
    fs.existsSync(path.join(directory, "catalog.json")) &&
    fs.existsSync(path.join(directory, "manifest.json"));
  if (hasContract(areaDirectory)) candidates.push(areaDirectory);
  for (const entry of fs.readdirSync(areaDirectory, { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.isSymbolicLink()) {
      const candidate = path.join(areaDirectory, entry.name);
      if (hasContract(candidate)) candidates.push(candidate);
    }
  }
  if (candidates.length !== 1) {
    fail(`Expected exactly one unzipped ${options.area} Snapshot; found ${candidates.length}.`);
  }

  return loadSnapshotRoot(candidates[0], session, options.area);
}

function loadSnapshotRoot(root, session, area, bindSession = true) {
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
  assertSessionSnapshotIdentity(session, area, manifest, catalog, bindSession);
  return { root, catalog, manifest, inventory, datasets, byName };
}

function readSessionState(session) {
  const state = readJsonFile(path.join(session, "session.json"), "Session state");
  const invalidSqlPolicy =
    state?.sql !== undefined &&
    !new Set(["never", "essential", "as_needed"]).has(state.sql);
  const invalidModel =
    state?.model !== undefined &&
    (!Array.isArray(state.model) ||
      state.model.length !== 2 ||
      !Number.isSafeInteger(state.model[0]) ||
      state.model[0] <= 0 ||
      typeof state.model[1] !== "string" ||
      !state.model[1].trim() ||
      state.model[1].length > 255);
  const invalidDraftCache =
    state?.cs !== undefined &&
    (!state.cs ||
      Array.isArray(state.cs) ||
      typeof state.cs !== "object" ||
      Object.entries(state.cs).some(
        ([area, draft]) =>
          !new Set(["metadata", "model"]).has(area) ||
          !Array.isArray(draft) ||
          draft.length !== 5 ||
          typeof draft[0] !== "string" ||
          !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
            draft[0],
          ) ||
          !Number.isSafeInteger(draft[1]) ||
          draft[1] < 0 ||
          !new Set(["active", "validated"]).has(draft[2]) ||
          typeof draft[3] !== "string" ||
          !/^\d{2,}$/.test(draft[3]) ||
          typeof draft[4] !== "string" ||
          !/^[0-9a-f]{64}$/.test(draft[4]),
      ));
  if (
    !state ||
    typeof state !== "object" ||
    !Array.isArray(state.tasks) ||
    (state.current !== null && typeof state.current !== "string") ||
    invalidModel ||
    invalidSqlPolicy ||
    invalidDraftCache ||
    state.tasks.some(
      (task) =>
        !Array.isArray(task) ||
        task.length !== 4 ||
        task.some((value) => typeof value !== "string") ||
        !/^\d{2,}$/.test(task[0]) ||
        !new Set(["metadata", "model", "code", "validation"]).has(task[1]) ||
        !task[2] ||
        !Object.hasOwn(TASK_TRANSITIONS, task[3]),
    )
  ) {
    fail("Session state has an invalid shape.");
  }
  const taskIds = new Set(state.tasks.map((task) => task[0]));
  if (taskIds.size !== state.tasks.length || (state.current !== null && !taskIds.has(state.current))) {
    fail("Session state has an invalid shape.");
  }
  for (const [area, draft] of Object.entries(state.cs ?? {})) {
    const task = state.tasks.find((item) => item[0] === draft[3]);
    if (!task || task[1] !== area) {
      fail("Session server-draft cache does not match its bound task area.");
    }
  }
  return state;
}

function assertSessionSnapshotIdentity(session, area, manifest, catalog, bindSession = true) {
  if (area === "metadata") {
    const sessionTenant = path.basename(path.dirname(session));
    if (
      typeof manifest.tenant_code !== "string" ||
      normalizedValue("metadata", "tenant_code", manifest.tenant_code) !==
        normalizedValue("metadata", "tenant_code", sessionTenant)
    ) {
      fail("Metadata Snapshot Tenant Code does not match the session Tenant Code.");
    }
    return;
  }

  const catalogModel = catalog.model;
  const modelId = manifest.model_id;
  const modelName = manifest.model_name;
  const modelRevision = manifest.model_revision;
  if (
    !catalogModel ||
    Array.isArray(catalogModel) ||
    typeof catalogModel !== "object" ||
    !Number.isSafeInteger(modelId) ||
    modelId <= 0 ||
    typeof modelName !== "string" ||
    !modelName.trim() ||
    modelName.length > 255 ||
    !Number.isSafeInteger(modelRevision) ||
    modelRevision < 0 ||
    catalogModel.model_id !== modelId ||
    catalogModel.model_name !== modelName ||
    catalogModel.model_revision !== modelRevision
  ) {
    fail("Model identity does not match between Snapshot manifest and catalog.");
  }

  const state = readSessionState(session);
  if (state.model && state.model[0] !== modelId) {
    fail(
      `Session is bound to Model ${state.model[0]}; start a new session for Model ${modelId}.`,
    );
  }
  if (bindSession && (!state.model || state.model[1] !== modelName)) {
    state.model = [modelId, modelName];
    writeJsonAtomic(path.join(session, "session.json"), state);
  }
}

function parsePlan(value) {
  let plan;
  try {
    plan = JSON.parse(value ?? "");
  } catch {
    fail("--plan must be a JSON array of action lines.");
  }
  return validatePlan(plan);
}

function validatePlan(plan) {
  if (
    !Array.isArray(plan) ||
    plan.length < 1 ||
    plan.length > 64 ||
    plan.some(
      (line) =>
        typeof line !== "string" ||
        !line.trim() ||
        line.length > 300 ||
        line !== line.trim(),
    )
  ) {
    fail("--plan must contain 1 to 64 trimmed action lines of at most 300 characters.");
  }
  return plan;
}

function fileDigest(filePath) {
  const stat = fs.lstatSync(filePath);
  if (!stat.isFile() || stat.isSymbolicLink()) fail("Task plan must be a regular file.");
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function addTask(options) {
  const session = requireSessionPath(options.session);
  if (!new Set(["metadata", "model", "code", "validation"]).has(options.area)) {
    fail("--area must be metadata, model, code, or validation.");
  }
  if (
    typeof options.title !== "string" ||
    !options.title.trim() ||
    options.title !== options.title.trim() ||
    options.title.length > 120
  ) {
    fail("--title must be a trimmed string of at most 120 characters.");
  }
  const plan = parsePlan(options.plan);
  const state = readSessionState(session);
  if (state.current === null && new Set(["metadata", "model"]).has(options.area)) {
    const live = pendingSummary(pendingDirectory(session, options.area));
    if (live.files > 0) {
      fail(`The live ${options.area} Local Change Set is not task-bound; use task-stash/task-restore before starting another task.`);
    }
  }
  const highest = state.tasks.reduce((value, task) => {
    const numeric = Number(task[0]);
    return Number.isSafeInteger(numeric) ? Math.max(value, numeric) : value;
  }, 0);
  const next = highest + 1;
  const taskId = next < 100 ? String(next).padStart(2, "0") : String(next);
  const planPath = path.join(session, "tasks", `${taskId}.json`);
  if (fs.existsSync(planPath)) fail(`Task plan ${taskId} already exists.`);
  const taskState = state.current === null ? "doing" : "queued";

  writeJsonAtomic(planPath, plan);
  state.tasks.push([taskId, options.area, options.title, taskState]);
  if (taskState === "doing") state.current = taskId;
  writeJsonAtomic(path.join(session, "session.json"), state);
  return { task: taskId, state: taskState, plan_digest: fileDigest(planPath) };
}

function updateTaskPlan(options) {
  const session = requireSessionPath(options.session);
  if (!/^\d{2,}$/.test(options.task ?? "")) fail("--task must be a numeric task ID.");
  if (!/^[0-9a-f]{64}$/.test(options["expected-digest"] ?? "")) {
    fail("--expected-digest must be a lowercase SHA-256 digest.");
  }
  const state = readSessionState(session);
  const task = state.tasks.find((item) => item[0] === options.task);
  if (!task) fail(`Task ${options.task} does not exist.`);
  if (!new Set(["queued", "todo", "doing", "waiting", "review"]).has(task[3])) {
    fail(`Task plan cannot change in ${task[3]} state.`);
  }
  const planPath = path.join(session, "tasks", `${options.task}.json`);
  const actual = fileDigest(planPath);
  if (actual !== options["expected-digest"]) {
    fail(`Task plan digest conflict: expected ${options["expected-digest"]}, found ${actual}.`);
  }
  const plan = parsePlan(options.plan);
  writeJsonAtomic(planPath, plan);
  return { task: options.task, plan_digest: fileDigest(planPath) };
}

function cacheServerDraft(options) {
  const session = requireSessionPath(options.session);
  if (!new Set(["metadata", "model"]).has(options.area)) {
    fail("--area must be metadata or model.");
  }
  const state = readSessionState(session);
  const cache = { ...(state.cs ?? {}) };
  if (options.clear !== undefined) {
    if (options.clear !== "true") fail("--clear must be true when supplied.");
    if (options.id !== undefined || options.revision !== undefined || options.status !== undefined) {
      fail("--clear cannot be combined with --id, --revision, or --status.");
    }
    const existing = cache[options.area];
    if (!existing) fail(`No cached ${options.area} server draft exists.`);
    if (
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        options["expected-id"] ?? "",
      ) ||
      !/^\d+$/.test(options["expected-revision"] ?? "") ||
      !Number.isSafeInteger(Number(options["expected-revision"]))
    ) {
      fail("--expected-id and --expected-revision must identify a valid cached server draft.");
    }
    if (
      options["expected-id"]?.toLowerCase() !== existing[0] ||
      Number(options["expected-revision"]) !== existing[1]
    ) {
      fail("--expected-id and --expected-revision must match the exact cached server draft.");
    }
    if (existing && state.current !== existing[3]) {
      fail(`Cached ${options.area} server draft belongs to task ${existing[3]}; make it current before clearing.`);
    }
    delete cache[options.area];
    if (Object.keys(cache).length) state.cs = cache;
    else delete state.cs;
    writeJsonAtomic(path.join(session, "session.json"), state);
    return { area: options.area, draft: null };
  }
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(options.id ?? "")) {
    fail("--id must be a UUID.");
  }
  const revision = Number(options.revision);
  if (!Number.isSafeInteger(revision) || revision < 0) {
    fail("--revision must be a nonnegative integer.");
  }
  if (!new Set(["active", "validated"]).has(options.status)) {
    fail("--status must be active or validated.");
  }
  const task = state.tasks.find((item) => item[0] === state.current);
  if (!task || task[1] !== options.area) {
    fail(`A current ${options.area} task is required to cache a server draft.`);
  }
  const digest = acceptedWorkspaceDigest(session, task, options.area);
  const draft = [options.id.toLowerCase(), revision, options.status, task[0], digest];
  const existing = cache[options.area];
  if (existing && (existing[0] !== draft[0] || existing[3] !== draft[3])) {
    fail("Cached server draft ID and task are immutable; archive and clear it first.");
  }
  if (existing && revision < existing[1]) {
    fail("Cached server draft revision cannot decrease.");
  }
  if (
    existing &&
    existing[2] === "validated" &&
    options.status === "active" &&
    revision === existing[1]
  ) {
    fail("Cached server draft status cannot regress at the same revision.");
  }
  if (
    existing &&
    existing[4] !== digest &&
    (revision <= existing[1] || options.status !== "active")
  ) {
    fail("A new accepted digest requires a newer active Stage revision for the same server draft.");
  }
  cache[options.area] = draft;
  state.cs = cache;
  writeJsonAtomic(path.join(session, "session.json"), state);
  return { area: options.area, draft };
}

const TASK_TRANSITIONS = {
  queued: new Set(["todo", "doing", "waiting", "cancelled"]),
  todo: new Set(["doing", "waiting", "cancelled"]),
  doing: new Set(["waiting", "review", "done", "cancelled"]),
  waiting: new Set(["todo", "doing", "cancelled"]),
  review: new Set(["doing", "ready", "overridden", "cancelled"]),
  ready: new Set(["doing", "staged", "cancelled"]),
  overridden: new Set(["doing", "staged", "cancelled"]),
  staged: new Set(["doing", "review", "ready", "overridden", "applied", "cancelled"]),
  applied: new Set(),
  done: new Set(),
  cancelled: new Set(),
};

function updateTaskState(options) {
  const session = requireSessionPath(options.session);
  if (!/^\d{2,}$/.test(options.task ?? "")) fail("--task must be a numeric task ID.");
  if (!Object.hasOwn(TASK_TRANSITIONS, options.state ?? "")) fail("--state is invalid.");
  const state = readSessionState(session);
  const index = state.tasks.findIndex((task) => task[0] === options.task);
  if (index < 0) fail(`Task ${options.task} does not exist.`);
  const task = state.tasks[index];
  const previous = task[3];
  if (
    new Set(["metadata", "model"]).has(task[1]) &&
    new Set(["waiting", "done", "cancelled"]).has(options.state) &&
    state.current === task[0]
  ) {
    const live = pendingSummary(pendingDirectory(session, task[1]));
    if (live.files > 0) {
      fail(`Task ${task[0]} has live pending work; use task-stash instead of ${options.state}.`);
    }
    if (state.cs?.[task[1]]?.[3] === task[0]) {
      fail(`Task ${task[0]} has a cached server draft; archive it explicitly and clear the cache first.`);
    }
  }
  if (!TASK_TRANSITIONS[previous]?.has(options.state)) {
    fail(`Task transition ${previous} -> ${options.state} is not allowed.`);
  }
  if (options.state === "doing" && state.current !== null && state.current !== options.task) {
    fail(`Task ${state.current} is current; move it to waiting or terminal state first.`);
  }
  if (
    options.state === "doing" &&
    state.current === null &&
    new Set(["metadata", "model"]).has(task[1])
  ) {
    if (fs.existsSync(taskStashDirectory(session, task))) {
      fail(`Task ${task[0]} has stashed work; use task-restore.`);
    }
    const live = pendingSummary(pendingDirectory(session, task[1]));
    if (live.files > 0) {
      fail(`The live ${task[1]} Local Change Set belongs to another task; use task-stash/task-restore.`);
    }
  }
  let appliedAcceptance = null;
  if (options.state === "staged") {
    if (!new Set(["metadata", "model"]).has(task[1])) {
      fail("Only Metadata or Model tasks can enter staged state.");
    }
    if (Array.isArray(state.stale) && state.stale.includes(task[1])) {
      fail(`${task[1]} Snapshot is stale; refresh it before Stage.`);
    }
    const changeDirectory = path.join(session, `${task[1]}-change-set`);
    if (fs.readdirSync(changeDirectory).length === 0) {
      fail("Local Change Set is empty; there is nothing to Stage.");
    }
    const acceptancePath = path.join(session, "tasks", `${options.task}.accept.json`);
    if (!fs.existsSync(acceptancePath)) fail("Task has no accepted digest; review and accept first.");
    const acceptance = readJsonFile(acceptancePath, "Task acceptance");
    const actual = workspaceDigest({ directory: changeDirectory });
    if (
      !Array.isArray(acceptance) ||
      !/^[0-9a-f]{64}$/.test(acceptance[0] ?? "") ||
      acceptance[0] !== actual ||
      (previous === "ready" && acceptance[1] !== "valid") ||
      (previous === "overridden" && acceptance[1] !== "override")
    ) {
      fail("Task accepted digest does not match the exact local Change Set.");
    }
    assertCachedDraftBinding(state, task, task[1], actual);
  }
  if (options.state === "applied" && new Set(["metadata", "model"]).has(task[1])) {
    const acceptancePath = path.join(session, "tasks", `${options.task}.accept.json`);
    appliedAcceptance = readJsonFile(acceptancePath, "Task acceptance");
    const actual = workspaceDigest({ directory: pendingDirectory(session, task[1]) });
    if (
      !Array.isArray(appliedAcceptance) ||
      appliedAcceptance[0] !== actual ||
      !new Set(["valid", "override"]).has(appliedAcceptance[1])
    ) {
      fail("Task accepted digest does not match the exact local Change Set.");
    }
    assertCachedDraftBinding(state, task, task[1], actual, true);
  }

  task[3] = options.state;
  if (options.state === "doing") state.current = options.task;
  if (new Set(["waiting", "applied", "done", "cancelled"]).has(options.state)) {
    if (state.current === options.task) state.current = null;
  } else {
    state.current = options.task;
  }
  if (options.state === "applied" && new Set(["metadata", "model"]).has(task[1])) {
    const acceptance = appliedAcceptance;
    const snapshotIndex = acceptance[1] === "override" ? 3 : 2;
    const snapshotId = acceptance[snapshotIndex];
    const revision = acceptance[snapshotIndex + 1] ?? null;
    if (typeof snapshotId !== "string" || !snapshotId) {
      fail("Task acceptance does not identify its input Snapshot.");
    }
    writeJsonAtomic(path.join(session, "tasks", `${options.task}.applied.json`), [
      task[1],
      snapshotId,
      revision,
    ]);
    const stale = Array.isArray(state.stale) ? state.stale : [];
    if (!stale.includes(task[1])) stale.push(task[1]);
    state.stale = stale.sort();
    if (state.cs?.[task[1]]) {
      delete state.cs[task[1]];
      if (Object.keys(state.cs).length === 0) delete state.cs;
    }
  }
  writeJsonAtomic(path.join(session, "session.json"), state);
  return { task: options.task, state: options.state };
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

const COMPACT_SCHEMA_OMISSIONS = new Set([
  "x-gds-columns",
  "x-gds-governed-authoring-schema",
  "x-gds-stage-record-validation",
]);

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

function normalizedValue(area, field, value) {
  if (typeof value !== "string") return value;
  if (area === "model") {
    return unicode.casefold(value.replace(/^ +| +$/g, ""));
  }
  if (/(_code|_name|_schema)$/.test(field)) {
    return unicode.lower(value.replace(/^ +| +$/g, ""));
  }
  return value;
}

function stableStringify(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
    .join(",")}}`;
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

function changeSetContext(options) {
  const snapshot = locateSnapshot(options);
  const session = path.dirname(path.join(snapshot.root, "..", "placeholder"));
  const resolvedSession = requireSessionPath(options.session);
  if (session !== resolvedSession) {
    // The Snapshot may live one child below its area, but never outside the session.
    const expectedPrefix = `${path.join(resolvedSession, options.area)}${path.sep}`;
    if (!snapshot.root.startsWith(expectedPrefix)) fail("Snapshot is outside its session area.");
  }
  const state = readSessionState(resolvedSession);
  if (Array.isArray(state.stale) && state.stale.includes(options.area)) {
    fail(`${options.area} Snapshot is stale; replace it before local mutation.`);
  }
  const current = state.tasks.find((task) => task[0] === state.current);
  if (!current || current[1] !== options.area) {
    fail(`A current ${options.area} task is required before local mutation.`);
  }
  const directory = path.join(resolvedSession, `${options.area}-change-set`);
  const stat = fs.lstatSync(directory);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    fail("Local Change Set must be a regular directory.");
  }
  return { ...snapshot, session: resolvedSession, state, current, directory };
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

function pendingDirectory(session, area) {
  const directory = path.join(session, `${area}-change-set`);
  const stat = fs.lstatSync(directory);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    fail("Local Change Set must be a regular directory.");
  }
  return directory;
}

function pendingSummary(directory) {
  let files = 0;
  let bytes = 0;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(".json")) {
      fail("Local Change Set contains an unsupported entry.");
    }
    files += 1;
    bytes += fs.statSync(path.join(directory, entry.name)).size;
  }
  return { files, bytes, digest: workspaceDigest({ directory }) };
}

function acceptedWorkspaceDigest(session, task, area) {
  if (!new Set(["ready", "overridden", "staged"]).has(task[3])) {
    fail("Current task must have a digest-bound acceptance before caching a server draft.");
  }
  const acceptancePath = path.join(session, "tasks", `${task[0]}.accept.json`);
  if (!fs.existsSync(acceptancePath)) fail("Task has no accepted digest; review and accept first.");
  const acceptance = readJsonFile(acceptancePath, "Task acceptance");
  const actual = workspaceDigest({ directory: pendingDirectory(session, area) });
  if (
    !Array.isArray(acceptance) ||
    acceptance[0] !== actual ||
    (task[3] === "ready" && acceptance[1] !== "valid") ||
    (task[3] === "overridden" && acceptance[1] !== "override") ||
    (task[3] === "staged" && !new Set(["valid", "override"]).has(acceptance[1]))
  ) {
    fail("Task accepted digest does not match the exact local Change Set.");
  }
  return actual;
}

function assertCachedDraftBinding(state, task, area, digest, requireValidated = false) {
  const draft = state.cs?.[area];
  if (!draft) fail(`Cache the ${area} server draft before continuing.`);
  if (draft[3] !== task[0]) {
    fail(`Cached ${area} server draft belongs to task ${draft[3]}, not task ${task[0]}.`);
  }
  if (draft[4] !== digest) {
    fail("Cached server draft is bound to a different accepted local digest.");
  }
  if (requireValidated && draft[2] !== "validated") {
    fail("Cached server draft must be validated before marking the task applied.");
  }
  return draft;
}

function taskStashDirectory(session, task) {
  return path.join(session, "tasks", task[0], `${task[1]}-change-set`);
}

function validatePortablePendingSet(directory) {
  const summary = pendingSummary(directory);
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const records = readJsonFile(path.join(directory, entry.name), `${entry.name} pending file`);
    if (
      !Array.isArray(records) ||
      records.some((record) => !record || Array.isArray(record) || typeof record !== "object")
    ) {
      fail(`${entry.name} pending file must contain a JSON array of complete records.`);
    }
  }
  return summary;
}

function stashTask(options) {
  const session = requireSessionPath(options.session);
  if (!/^\d{2,}$/.test(options.task ?? "")) fail("--task must be a numeric task ID.");
  if (!/^[0-9a-f]{64}$/.test(options["expected-digest"] ?? "")) {
    fail("--expected-digest must be a lowercase SHA-256 digest.");
  }
  const state = readSessionState(session);
  const task = state.tasks.find((item) => item[0] === options.task);
  if (!task) fail(`Task ${options.task} does not exist.`);
  if (state.current !== task[0]) fail(`Task ${task[0]} must be current before it can be stashed.`);
  if (!new Set(["metadata", "model"]).has(task[1])) {
    fail("Only Metadata or Model tasks can stash a Local Change Set.");
  }
  if (!new Set(["doing", "review", "ready", "overridden", "staged"]).has(task[3])) {
    fail(`Task ${task[0]} cannot be stashed in ${task[3]} state.`);
  }
  if (state.cs?.[task[1]]) {
    fail(`Archive the cached ${task[1]} server draft and clear its cache before task-stash.`);
  }

  const live = pendingDirectory(session, task[1]);
  const summary = validatePortablePendingSet(live);
  if (summary.files === 0) fail("Local Change Set is empty; there is nothing to stash.");
  if (summary.digest !== options["expected-digest"]) {
    fail(
      `Local Change Set digest conflict: expected ${options["expected-digest"]}, found ${summary.digest}.`,
    );
  }
  const taskDirectory = path.dirname(taskStashDirectory(session, task));
  if (fs.existsSync(taskDirectory)) {
    const stat = fs.lstatSync(taskDirectory);
    if (!stat.isDirectory() || stat.isSymbolicLink()) fail("Task stash parent must be a regular directory.");
  } else {
    fs.mkdirSync(taskDirectory, { mode: 0o700 });
  }
  const stash = taskStashDirectory(session, task);
  if (fs.existsSync(stash)) fail(`Task ${task[0]} already has a ${task[1]} stash.`);

  const acceptancePath = path.join(session, "tasks", `${task[0]}.accept.json`);
  const acceptance = fs.existsSync(acceptancePath) ? fs.readFileSync(acceptancePath) : null;
  fs.renameSync(live, stash);
  try {
    fs.mkdirSync(live, { mode: 0o700 });
    if (acceptance !== null) fs.unlinkSync(acceptancePath);
    task[3] = "waiting";
    state.current = null;
    writeJsonAtomic(path.join(session, "session.json"), state);
  } catch (error) {
    if (fs.existsSync(live) && fs.readdirSync(live).length === 0) fs.rmdirSync(live);
    if (fs.existsSync(stash) && !fs.existsSync(live)) fs.renameSync(stash, live);
    if (acceptance !== null && !fs.existsSync(acceptancePath)) {
      fs.writeFileSync(acceptancePath, acceptance, { mode: 0o600 });
    }
    throw error;
  }
  return { task: task[0], area: task[1], digest: summary.digest, files: summary.files };
}

function restoreTask(options) {
  const session = requireSessionPath(options.session);
  if (!/^\d{2,}$/.test(options.task ?? "")) fail("--task must be a numeric task ID.");
  if (!/^[0-9a-f]{64}$/.test(options["expected-digest"] ?? "")) {
    fail("--expected-digest must be a lowercase SHA-256 digest.");
  }
  let state = readSessionState(session);
  let task = state.tasks.find((item) => item[0] === options.task);
  if (!task) fail(`Task ${options.task} does not exist.`);
  if (state.current !== null) fail(`Task ${state.current} is current; finish or stash it first.`);
  if (task[3] !== "waiting") fail(`Task ${task[0]} must be waiting before restore.`);
  if (!new Set(["metadata", "model"]).has(task[1])) {
    fail("Only Metadata or Model tasks can restore a Local Change Set.");
  }
  if (Array.isArray(state.stale) && state.stale.includes(task[1])) {
    fail(`${task[1]} Snapshot is stale; replace it before task-restore.`);
  }
  if (state.cs?.[task[1]]) fail(`Clear the cached ${task[1]} server draft before task-restore.`);

  const snapshot = locateSnapshot({ session, area: task[1] });
  state = readSessionState(session);
  task = state.tasks.find((item) => item[0] === options.task);
  if (state.current !== null || task?.[3] !== "waiting") {
    fail("Session task state changed during restore; retry from status.");
  }
  const live = pendingDirectory(session, task[1]);
  if (pendingSummary(live).files !== 0) {
    fail(`The live ${task[1]} Local Change Set must be empty before task-restore.`);
  }
  const stash = taskStashDirectory(session, task);
  if (!fs.existsSync(stash)) fail(`Task ${task[0]} has no ${task[1]} stash.`);
  const stashStat = fs.lstatSync(stash);
  if (!stashStat.isDirectory() || stashStat.isSymbolicLink()) {
    fail("Task stash must be a regular directory.");
  }
  const context = {
    ...snapshot,
    session,
    state,
    current: task,
    directory: stash,
  };
  readPending(context);
  const summary = pendingSummary(stash);
  if (summary.files === 0) fail("Task stash is empty.");
  if (summary.digest !== options["expected-digest"]) {
    fail(`Task stash digest conflict: expected ${options["expected-digest"]}, found ${summary.digest}.`);
  }

  fs.rmdirSync(live);
  try {
    fs.renameSync(stash, live);
    const acceptancePath = path.join(session, "tasks", `${task[0]}.accept.json`);
    if (fs.existsSync(acceptancePath)) fs.unlinkSync(acceptancePath);
    task[3] = "doing";
    state.current = task[0];
    writeJsonAtomic(path.join(session, "session.json"), state);
  } catch (error) {
    if (fs.existsSync(live) && !fs.existsSync(stash)) fs.renameSync(live, stash);
    if (!fs.existsSync(live)) fs.mkdirSync(live, { mode: 0o700 });
    throw error;
  }
  return { task: task[0], area: task[1], digest: summary.digest, files: summary.files };
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

function writePendingDataset(context, dataset, records) {
  records.sort((left, right) =>
    compareKeys(
      canonicalKey(optionsArea(context), dataset, left),
      canonicalKey(optionsArea(context), dataset, right),
    ),
  );
  writeJsonAtomic(path.join(context.directory, `${dataset.name}.json`), records);
}

function markLocalEditForReview(context) {
  const task = context.state.tasks.find((item) => item[0] === context.state.current);
  if (!task) fail("Current task disappeared during local edit.");
  if (!new Set(["doing", "review", "ready", "overridden", "staged"]).has(task[3])) {
    fail(`Task state ${task[3]} does not permit local editing.`);
  }
  task[3] = "review";
  writeJsonAtomic(path.join(context.session, "session.json"), context.state);
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
    } else {
      records[index] = record;
    }
  }
  pending[dataset.name] = records;
  writePendingDataset(context, dataset, records);
  markLocalEditForReview(context);
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
  writePendingDataset(context, dataset, records);
  markLocalEditForReview(context);
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

  for (const item of prepared) writePendingDataset(context, item.dataset, item.records);
  markLocalEditForReview(context);
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
  writePendingDataset(context, dataset, records);
  markLocalEditForReview(context);
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

function validateChangeSet(options) {
  const context = changeSetContext(options);
  const pending = readPending(context);
  const loaded = new Map();
  for (const dataset of context.datasets) {
    const schema = datasetSchema(context, dataset);
    const baseline = readSnapshotRecords(context, dataset);
    const draft = pending[dataset.name] ?? [];
    let effective = baseline;
    let overlayError = null;
    try {
      effective = workbenchCore.overlay(options.area, dataset, baseline, draft);
    } catch (error) {
      overlayError = error.message;
    }
    loaded.set(dataset.name, {
      definition: {
        ...dataset,
        record_type: schema["x-gds-record-type"] ?? dataset.record_type ?? dataset.name,
      },
      schema,
      baseline,
      pending: draft,
      effective,
      overlayError,
    });
  }
  let metadata = null;
  let metadataTenantCode = options.area === "metadata"
    ? context.manifest.tenant_code
    : context.catalog.model?.tenant_code ?? null;
  if (options.area === "model" && !context.state.stale?.includes("metadata")) {
    try {
      const snapshot = locateSnapshot({ session: context.session, area: "metadata" });
      metadata = new Map();
      for (const dataset of snapshot.datasets) {
        const schema = datasetSchema(snapshot, dataset);
        metadata.set(dataset.name, {
          definition: {
            ...dataset,
            record_type: schema["x-gds-record-type"] ?? dataset.record_type ?? dataset.name,
          },
          schema,
          baseline: readSnapshotRecords(snapshot, dataset),
        });
      }
    } catch (error) {
      if (error.message !== "Expected exactly one unzipped metadata Snapshot; found 0.") {
        throw error;
      }
    }
  }
  const validationIssues = workbenchAreas[options.area].validate(loaded, metadata, {
    tenantCode: metadataTenantCode,
    model: context.catalog.model ?? null,
  });
  const boundedIssues = validationIssues.slice(0, 200);
  const repairs = boundedIssues.map((issue) => {
    const detail = issue.message || issue.target || issue.endpoint || issue.field || issue.code;
    const fields = [];
    if (typeof issue.field === "string" && issue.field) fields.push(issue.field);
    const path = typeof detail === "string" ? detail.match(/\$((?:\.[^.\[\]]+|\[\d+\])*)/) : null;
    if (path) {
      for (const match of path[1].matchAll(/\.([^.\[\]]+)|\[(\d+)\]/g)) {
        fields.push(match[1] ?? match[2]);
      }
    }
    return {
      dataset: issue.dataset ?? options.area,
      record: issue.record ?? null,
      code: issue.code,
      fields: [...new Set(fields)],
      message: detail,
    };
  });
  const issues = boundedIssues.map((issue) => {
    const detail = issue.message || issue.target || issue.endpoint || issue.field || issue.code;
    const humanCode = issue.code.replaceAll("_", " ");
    return [
      issue.dataset ?? options.area,
      issue.record ?? null,
      detail === issue.code
        ? `${issue.code}: ${humanCode}`
        : `${issue.code}: ${humanCode}: ${detail}`,
    ];
  });
  const output = {
    valid: validationIssues.length === 0,
    issues,
    repairs,
    truncated: validationIssues.length > boundedIssues.length,
    digest: workspaceDigest(context),
  };
  writeValidationReport(context, validationIssues, output);
  return output;
}

function generateLocalDbml(options) {
  if (options.area !== "model") fail("--area must be model for generate-dbml.");
  const modelType = options["model-type"] ?? "full";
  if (!new Set(["full", "conceptual", "logical", "dimensional"]).has(modelType)) {
    fail("--model-type must be full, conceptual, logical, or dimensional.");
  }
  const includeSubmodels = options["include-submodels"] ?? "true";
  if (!new Set(["true", "false"]).has(includeSubmodels)) {
    fail("--include-submodels must be true or false.");
  }
  const context = changeSetContext(options);
  const pending = readPending(context);
  const loaded = new Map();
  for (const dataset of context.datasets) {
    const baseline = readSnapshotRecords(context, dataset);
    const draft = pending[dataset.name] ?? [];
    loaded.set(dataset.name, {
      effective: workbenchCore.overlay("model", dataset, baseline, draft),
    });
  }
  const documents = workbenchDbml.render(loaded, context.catalog.model, {
    modelType,
    includeSubmodels: includeSubmodels === "true",
  });

  const directory = path.join(context.session, "model-dbml");
  if (!fs.existsSync(directory)) fs.mkdirSync(directory, { mode: 0o700 });
  const directoryStat = fs.lstatSync(directory);
  if (!directoryStat.isDirectory() || directoryStat.isSymbolicLink()) {
    fail("Generated DBML path must be a regular directory.");
  }
  const previousManifestPath = path.join(directory, "manifest.json");
  let previousFiles = [];
  if (fs.existsSync(previousManifestPath)) {
    const previous = readJsonFile(previousManifestPath, "Generated DBML manifest");
    if (Array.isArray(previous.files)) {
      previousFiles = previous.files
        .map((item) => item?.path)
        .filter((name) => typeof name === "string" && /^[A-Za-z0-9_][A-Za-z0-9_.-]*\.dbml$/.test(name));
    }
  }
  const files = documents.map((document) => {
    const filePath = path.join(directory, document.path);
    writeTextAtomic(filePath, document.content);
    const bytes = Buffer.from(document.content, "utf8");
    return {
      path: document.path,
      layer: document.layer,
      view: document.view,
      submodel_name: document.submodel_name,
      table_count: document.table_count,
      relationship_count: document.relationship_count,
      size_bytes: bytes.length,
      sha256: sha256Bytes(bytes),
    };
  });
  const currentFiles = new Set(files.map((item) => item.path));
  for (const name of previousFiles) {
    if (currentFiles.has(name)) continue;
    const stalePath = path.join(directory, name);
    if (!fs.existsSync(stalePath)) continue;
    const stat = fs.lstatSync(stalePath);
    if (!stat.isFile() || stat.isSymbolicLink()) fail("Stale DBML member must be a regular file.");
    fs.unlinkSync(stalePath);
  }
  const manifest = {
    schema_version: "1.0",
    snapshot_kind: "dbml",
    source: "local_effective_model",
    model: {
      id: context.catalog.model.model_id,
      name: context.catalog.model.model_name,
      revision: context.catalog.model.model_revision,
    },
    draft_digest: workspaceDigest(context),
    model_type: modelType,
    include_submodels: includeSubmodels === "true",
    files,
  };
  writeJsonAtomic(previousManifestPath, manifest);
  return {
    directory,
    manifest: previousManifestPath,
    file_count: files.length,
    draft_digest: manifest.draft_digest,
    files: files.map((item) => item.path),
  };
}

function acceptChangeSet(options) {
  const context = changeSetContext(options);
  if (!/^[0-9a-f]{64}$/.test(options.digest ?? "")) {
    fail("--digest must be a lowercase SHA-256 digest.");
  }
  const actual = workspaceDigest(context);
  if (actual !== options.digest) {
    fail(`Local Change Set digest conflict: accepted ${options.digest}, found ${actual}.`);
  }
  const override = options.override === "true";
  if (options.override !== undefined && !new Set(["true", "false"]).has(options.override)) {
    fail("--override must be true or false.");
  }
  const validation = validateChangeSet(options);
  if (!validation.valid && !override) {
    fail("Local validation fails; fix issues or explicitly accept an override.");
  }
  if (
    !validation.valid &&
    (typeof options.reason !== "string" ||
      !options.reason.trim() ||
      options.reason !== options.reason.trim() ||
      options.reason.length > 300)
  ) {
    fail("--reason is required for an override and must be at most 300 characters.");
  }
  const task = context.state.tasks.find((item) => item[0] === context.state.current);
  if (!task || !new Set(["review", "ready", "overridden"]).has(task[3])) {
    fail("Current task must be in review before acceptance.");
  }
  const nextState = validation.valid ? "ready" : "overridden";
  const acceptance = validation.valid
    ? [
        actual,
        "valid",
        context.manifest.snapshot_id,
        context.manifest.model_revision ?? null,
      ]
    : [
        actual,
        "override",
        options.reason,
        context.manifest.snapshot_id,
        context.manifest.model_revision ?? null,
      ];
  writeJsonAtomic(path.join(context.session, "tasks", `${task[0]}.accept.json`), acceptance);
  task[3] = nextState;
  writeJsonAtomic(path.join(context.session, "session.json"), context.state);
  return {
    task: task[0],
    state: nextState,
    digest: actual,
  };
}

function acceptRefreshedSnapshot(options) {
  if (!new Set(["metadata", "model"]).has(options.area)) {
    fail("--area must be metadata or model.");
  }
  const session = requireSessionPath(options.session);
  const current = locateSnapshot(options);
  const state = readSessionState(session);
  if (!Array.isArray(state.stale) || !state.stale.includes(options.area)) {
    fail(`${options.area} is not marked stale.`);
  }
  let applied = null;
  for (let index = state.tasks.length - 1; index >= 0; index -= 1) {
    const task = state.tasks[index];
    if (task[1] !== options.area || task[3] !== "applied") continue;
    const markerPath = path.join(session, "tasks", `${task[0]}.applied.json`);
    if (fs.existsSync(markerPath)) {
      applied = readJsonFile(markerPath, "Applied Snapshot marker");
      break;
    }
  }
  if (
    !Array.isArray(applied) ||
    applied.length !== 3 ||
    applied[0] !== options.area ||
    typeof applied[1] !== "string"
  ) {
    fail(`No applied ${options.area} Snapshot marker is available.`);
  }
  const currentId = current.manifest.snapshot_id;
  const currentRevision = current.manifest.model_revision ?? null;
  if (typeof currentId !== "string" || currentId === applied[1]) {
    fail(`${options.area} Snapshot was not replaced after Apply.`);
  }
  if (
    options.area === "model" &&
    (!Number.isSafeInteger(currentRevision) ||
      !Number.isSafeInteger(applied[2]) ||
      currentRevision <= applied[2])
  ) {
    fail("Refreshed Model Snapshot revision must be greater than the applied base revision.");
  }
  const changeDirectory = path.join(session, `${options.area}-change-set`);
  const files = [];
  for (const entry of fs.readdirSync(changeDirectory, { withFileTypes: true })) {
    if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(".json")) {
      fail("Local Change Set contains an unsupported entry.");
    }
    const filePath = path.join(changeDirectory, entry.name);
    const records = readJsonFile(filePath, `${entry.name.slice(0, -5)} pending file`);
    if (!Array.isArray(records)) fail(`${entry.name} must contain a JSON array.`);
    if (records.length > 0) {
      const name = entry.name.slice(0, -5);
      const dataset = current.byName.get(name);
      if (!dataset) fail(`Refreshed Snapshot has no dataset ${name}.`);
      const baseline = new Map();
      for (const record of readSnapshotRecords(current, dataset)) {
        const key = stableStringify(canonicalKey(options.area, dataset, record));
        if (baseline.has(key)) fail(`Refreshed Snapshot ${name} has a duplicate canonical key.`);
        baseline.set(key, record);
      }
      for (const record of records) {
        if (!record || Array.isArray(record) || typeof record !== "object") {
          fail(`${name} pending file contains a non-object record.`);
        }
        const key = stableStringify(canonicalKey(options.area, dataset, record));
        if (!baseline.has(key) || stableStringify(baseline.get(key)) !== stableStringify(record)) {
          fail(`Refreshed Snapshot does not contain the exact applied local record for ${name}.`);
        }
      }
    }
    files.push(filePath);
  }
  for (const filePath of files) fs.unlinkSync(filePath);
  state.stale = state.stale.filter((area) => area !== options.area);
  if (!state.stale.length) delete state.stale;
  writeJsonAtomic(path.join(session, "session.json"), state);
  return { area: options.area, id: currentId, revision: currentRevision, retired: files.length };
}

function removeSnapshotInstallPath(target, session) {
  const resolved = path.resolve(target);
  const parent = path.dirname(resolved);
  const name = path.basename(resolved);
  if (parent !== session || !name.startsWith(".")) {
    fail("Refusing to remove an unsafe Snapshot installation path.");
  }
  if (fs.existsSync(resolved)) fs.rmSync(resolved, { recursive: true, force: false });
}

function snapshotArchiveEntries(archive) {
  const result = childProcess.spawnSync("tar", ["-tf", archive], {
    encoding: "utf8",
    maxBuffer: 4 * 1024 * 1024,
    windowsHide: true,
  });
  if (result.error || result.status !== 0) fail("Snapshot ZIP could not be inspected.");
  const entries = result.stdout.split(/\r?\n/).filter(Boolean);
  if (!entries.length || entries.length > 4096) fail("Snapshot ZIP member count is invalid.");
  const seen = new Set();
  for (const entry of entries) {
    const member = entry.endsWith("/") ? entry.slice(0, -1) : entry;
    assertSafeSnapshotMemberPath(member);
    if (seen.has(member)) fail(`Snapshot ZIP contains duplicate member path ${member}.`);
    seen.add(member);
  }
  return entries;
}

function inspectExtractedSnapshot(root) {
  let fileCount = 0;
  let expandedBytes = 0;
  const pending = [root];
  while (pending.length) {
    const directory = pending.pop();
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name);
      const stat = fs.lstatSync(target);
      if (stat.isSymbolicLink() || (!stat.isDirectory() && !stat.isFile())) {
        fail("Snapshot ZIP may contain only regular files and directories.");
      }
      if (stat.isDirectory()) pending.push(target);
      else {
        fileCount += 1;
        expandedBytes += stat.size;
        if (fileCount > 4096 || expandedBytes > 512 * 1024 * 1024) {
          fail("Snapshot ZIP expands beyond the local safety limit.");
        }
      }
    }
  }
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

function installSnapshot(options) {
  if (!new Set(["metadata", "model"]).has(options.area)) {
    fail("--area must be metadata or model.");
  }
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    options["snapshot-id"] ?? "",
  )) fail("--snapshot-id must be a UUID.");
  if (!/^[0-9a-f]{64}$/.test(options.sha256 ?? "")) {
    fail("--sha256 must be a lowercase SHA-256 digest.");
  }
  const expectedSize = Number(options["size-bytes"]);
  if (!Number.isSafeInteger(expectedSize) || expectedSize <= 0) {
    fail("--size-bytes must be a positive integer.");
  }
  const session = requireSessionPath(options.session);
  const archive = path.resolve(options.archive ?? "");
  if (!fs.existsSync(archive)) fail("Snapshot ZIP was not found.");
  const archiveStat = fs.lstatSync(archive);
  if (!archiveStat.isFile() || archiveStat.isSymbolicLink()) {
    fail("Snapshot ZIP must be a regular file.");
  }
  if (archiveStat.size !== expectedSize) fail("Snapshot ZIP size does not match the MCP result.");
  const archiveDigest = crypto.createHash("sha256").update(fs.readFileSync(archive)).digest("hex");
  if (archiveDigest !== options.sha256) fail("Snapshot ZIP SHA-256 does not match the MCP result.");
  snapshotArchiveEntries(archive);

  const state = readSessionState(session);
  const stale = Array.isArray(state.stale) && state.stale.includes(options.area);
  const pending = pendingSummary(pendingDirectory(session, options.area));
  if (pending.files > 0 && !stale) {
    fail(`Cannot replace the ${options.area} Snapshot while unapplied local records exist.`);
  }
  const stage = fs.mkdtempSync(path.join(session, `.${options.area}-install-`));
  const extracted = path.join(stage, "next");
  fs.mkdirSync(extracted, { mode: 0o700 });
  const backup = `${stage}-previous`;
  const destination = path.join(session, options.area);
  let movedPrevious = false;
  let movedNext = false;
  try {
    const extraction = childProcess.spawnSync("tar", ["-xf", archive, "-C", extracted], {
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
      windowsHide: true,
    });
    if (extraction.error || extraction.status !== 0) fail("Snapshot ZIP could not be extracted.");
    inspectExtractedSnapshot(extracted);
    const root = findExtractedSnapshotRoot(extracted);
    const candidate = loadSnapshotRoot(root, session, options.area, false);
    if (candidate.manifest.snapshot_id.toLowerCase() !== options["snapshot-id"].toLowerCase()) {
      fail("Snapshot ZIP ID does not match the MCP result.");
    }

    fs.renameSync(destination, backup);
    movedPrevious = true;
    fs.renameSync(extracted, destination);
    movedNext = true;
    const installed = locateSnapshot({ session, area: options.area });
    let refreshed = false;
    if (stale) {
      acceptRefreshedSnapshot({ session, area: options.area });
      refreshed = true;
    }
    removeSnapshotInstallPath(backup, session);
    movedPrevious = false;
    removeSnapshotInstallPath(stage, session);
    return {
      area: options.area,
      snapshot_id: installed.manifest.snapshot_id,
      model_revision: installed.manifest.model_revision ?? null,
      dataset_count: installed.datasets.length,
      refreshed,
    };
  } catch (error) {
    if (movedNext && fs.existsSync(destination)) fs.rmSync(destination, { recursive: true });
    if (movedPrevious && fs.existsSync(backup)) fs.renameSync(backup, destination);
    if (fs.existsSync(stage)) removeSnapshotInstallPath(stage, session);
    if (fs.existsSync(backup)) removeSnapshotInstallPath(backup, session);
    throw error;
  }
}

function assertAcceptedChangeSet(context) {
  const task = context.state.tasks.find((item) => item[0] === context.state.current);
  if (!task || !new Set(["ready", "overridden", "staged"]).has(task[3])) {
    fail("Current task must have a digest-bound acceptance before reconciliation.");
  }
  const acceptance = readJsonFile(
    path.join(context.session, "tasks", `${task[0]}.accept.json`),
    "Task acceptance",
  );
  const digest = workspaceDigest(context);
  if (
    !Array.isArray(acceptance) ||
    acceptance[0] !== digest ||
    (task[3] === "ready" && acceptance[1] !== "valid") ||
    (task[3] === "overridden" && acceptance[1] !== "override") ||
    (task[3] === "staged" && !new Set(["valid", "override"]).has(acceptance[1]))
  ) {
    fail("Task accepted digest does not match the exact local Change Set.");
  }
  return digest;
}

function assertBoundServerDraft(context, digest) {
  const task = context.state.tasks.find((item) => item[0] === context.state.current);
  const area = optionsArea(context);
  const draft = context.state.cs?.[area];
  if (!draft) fail(`Cache the ${area} server draft before reconciliation.`);
  if (draft[3] !== task[0]) {
    fail(`Cached ${area} server draft belongs to task ${draft[3]}, not task ${task[0]}.`);
  }
  return draft[4] === digest;
}

function reconcileChangeSet(options) {
  const context = changeSetContext(options);
  const digest = assertAcceptedChangeSet(context);
  const cacheBound = assertBoundServerDraft(context, digest);
  const pending = readPending(context);
  const server = parseObjectOption(options.server, "--server");
  const datasetNames = [...new Set([...Object.keys(pending), ...Object.keys(server)])].sort();
  const datasets = [];
  const conflicts = [];

  for (const name of datasetNames) {
    const dataset = context.byName.get(name);
    if (!dataset) fail(`Server draft contains unknown dataset ${name}.`);
    const localRecords = pending[name] ?? null;
    const serverRecords = server[name] ?? [];
    if (!Array.isArray(serverRecords)) fail(`Server draft dataset ${name} must be a JSON array.`);
    const schema = editableDatasetSchema(context, dataset);
    for (const record of serverRecords) {
      const issues = schemaIssues(record, schema);
      if (issues.length) fail(`Server draft ${name} record is invalid: ${issues[0]}`);
    }
    if (localRecords?.length === 0 && serverRecords.length > 0) {
      datasets.push([name, "conflict", 0, serverRecords.length]);
      conflicts.push([name, { explicit_clear: true }]);
      continue;
    }
    const localMap = new Map(
      (localRecords ?? []).map((record) => [
        stableStringify(canonicalKey(options.area, dataset, record)),
        record,
      ]),
    );
    const serverMap = new Map();
    for (const record of serverRecords) {
      const key = stableStringify(canonicalKey(options.area, dataset, record));
      if (serverMap.has(key)) fail(`Server draft ${name} contains a duplicate canonical key.`);
      serverMap.set(key, record);
    }
    let exactOverlap = 0;
    let onlyLocal = 0;
    let onlyServer = 0;
    for (const [key, record] of localMap) {
      if (!serverMap.has(key)) {
        onlyLocal += 1;
      } else if (stableStringify(record) === stableStringify(serverMap.get(key))) {
        exactOverlap += 1;
      } else {
        conflicts.push([
          name,
          Object.fromEntries(
            dataset.canonical_key.map((field, index) => [field, JSON.parse(key)[index]]),
          ),
        ]);
      }
    }
    for (const key of serverMap.keys()) if (!localMap.has(key)) onlyServer += 1;
    let classification;
    if (conflicts.some((item) => item[0] === name)) classification = "conflict";
    else if (onlyLocal === 0 && onlyServer === 0) classification = "exact";
    else if (onlyLocal === 0 && exactOverlap === localMap.size) classification = "contained";
    else classification = "non_overlap";
    datasets.push([name, classification, localMap.size, serverMap.size]);
  }

  let classification = "exact";
  if (conflicts.length) classification = "conflict";
  else if (datasets.some((item) => item[1] === "non_overlap")) classification = "non_overlap";
  else if (datasets.some((item) => item[1] === "contained")) classification = "contained";
  return {
    classification,
    ready: classification !== "conflict",
    datasets,
    conflicts,
    digest,
    cache_bound: cacheBound,
    ...(classification === "conflict"
      ? {
          resolution_prompt:
            "Server draft and local records differ at the listed canonical keys. Choose which complete record is authoritative; never overwrite automatically.",
        }
      : {}),
  };
}

function mergeStageDocuments(context, pending, server) {
  const merged = {};
  for (const name of Object.keys(pending).sort()) {
    const dataset = context.byName.get(name);
    const records = new Map();
    for (const record of server[name] ?? []) {
      records.set(stableStringify(canonicalKey(optionsArea(context), dataset, record)), record);
    }
    for (const record of pending[name]) {
      records.set(stableStringify(canonicalKey(optionsArea(context), dataset, record)), record);
    }
    merged[name] = [...records.values()].sort((left, right) =>
      compareKeys(
        canonicalKey(optionsArea(context), dataset, left),
        canonicalKey(optionsArea(context), dataset, right),
      ),
    );
  }
  return merged;
}

function sha256Bytes(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function recordChunks(records, maximumBytes) {
  const chunks = [];
  let current = [];
  for (const record of records) {
    const candidate = [...current, record];
    const candidateBytes = Buffer.byteLength(stableStringify(candidate), "utf8");
    if (candidate.length <= STAGE_CHUNK_MAX_RECORDS && candidateBytes <= maximumBytes) {
      current = candidate;
      continue;
    }
    if (current.length === 0) return null;
    chunks.push(current);
    current = [record];
    if (Buffer.byteLength(stableStringify(current), "utf8") > maximumBytes) return null;
  }
  if (current.length) chunks.push(current);
  return chunks;
}

function transportSafeRecordChunks(records, hardMaximumBytes) {
  let chunks = recordChunks(records, PREFERRED_STAGE_PAYLOAD_BYTES);
  if (chunks !== null && chunks.length <= STAGE_MAX_CHUNKS) {
    return { chunks, maximumBytes: PREFERRED_STAGE_PAYLOAD_BYTES };
  }
  let lower = PREFERRED_STAGE_PAYLOAD_BYTES + 1;
  let upper = hardMaximumBytes;
  let best = null;
  while (lower <= upper) {
    const candidateMaximum = Math.floor((lower + upper) / 2);
    const candidate = recordChunks(records, candidateMaximum);
    if (candidate !== null && candidate.length <= STAGE_MAX_CHUNKS) {
      best = { chunks: candidate, maximumBytes: candidateMaximum };
      upper = candidateMaximum - 1;
    } else {
      lower = candidateMaximum + 1;
    }
  }
  return best;
}

function prepareStage(options) {
  const reconciliation = reconcileChangeSet(options);
  if (!reconciliation.ready) fail("Resolve reconciliation conflicts before preparing Stage.");
  if (!reconciliation.cache_bound) {
    fail("Cached server draft is not bound to the accepted local Change Set digest.");
  }
  const context = changeSetContext(options);
  const area = optionsArea(context);
  const draft = context.state.cs?.[area];
  if (!draft || draft[2] !== "active") fail(`Cached ${area} server draft must be active.`);
  const pending = readPending(context);
  if (Object.keys(pending).length === 0) fail("Local Change Set has no affected datasets.");
  const server = parseObjectOption(options.server, "--server");
  const documents = mergeStageDocuments(context, pending, server);
  const maximumRecords = area === "metadata" ? 50_000 : 20_000;
  for (const [name, records] of Object.entries(documents)) {
    if (records.length > maximumRecords) {
      fail(`${name} exceeds the ${maximumRecords}-record dataset limit.`);
    }
  }

  const names = Object.keys(documents).sort();
  const directNames = new Set(names);
  const directDocument = () =>
    names
      .filter((name) => directNames.has(name))
      .map((dataset) => ({ dataset, records: documents[dataset] }));
  while (Buffer.byteLength(stableStringify(directDocument()), "utf8") > DIRECT_STAGE_MAX_BYTES) {
    const removable = names
      .filter((name) => directNames.has(name) && documents[name].length > 0)
      .sort((left, right) => {
        const sizeDifference =
          Buffer.byteLength(stableStringify(documents[right]), "utf8") -
          Buffer.byteLength(stableStringify(documents[left]), "utf8");
        return sizeDifference || left.localeCompare(right);
      });
    if (!removable.length) fail("Direct Stage envelope exceeds its safe byte limit.");
    directNames.delete(removable[0]);
  }

  const taskId = context.current[0];
  const stageDirectory = path.join(context.session, "tasks", `${taskId}.stage`);
  if (fs.existsSync(stageDirectory)) fs.rmSync(stageDirectory, { recursive: true });
  fs.mkdirSync(stageDirectory, { mode: 0o700 });
  const directChanges = directDocument();
  let direct = null;
  if (directChanges.length) {
    const directPath = path.join(stageDirectory, "direct.json");
    writeJsonAtomic(directPath, directChanges);
    direct = {
      file: directPath,
      datasets: directChanges.map((change) => change.dataset),
      bytes: Buffer.byteLength(stableStringify(directChanges), "utf8"),
    };
  }

  const batches = [];
  const recordChunkHardBytes =
    area === "metadata"
      ? METADATA_STAGE_CHUNK_MAX_BYTES
      : MODEL_STAGE_RECORD_CHUNK_MAX_BYTES;
  for (const name of names.filter((dataset) => !directNames.has(dataset))) {
    const records = documents[name];
    const preferredChunks = recordChunks(records, PREFERRED_STAGE_PAYLOAD_BYTES);
    const preferFragments =
      area === "model" &&
      name === "generated_code" &&
      (preferredChunks === null || preferredChunks.length > STAGE_MAX_CHUNKS);
    const recordPacking = preferFragments
      ? null
      : transportSafeRecordChunks(records, recordChunkHardBytes);
    let chunks = recordPacking?.chunks ?? null;
    let chunkBytes = recordPacking?.maximumBytes ?? PREFERRED_STAGE_PAYLOAD_BYTES;
    let payloadMode = "records";
    let totalPayloadBytes = null;
    if (chunks === null) {
      if (area !== "model" || name !== "generated_code") {
        fail(
          `${name} cannot fit within ${STAGE_MAX_CHUNKS} chunks of ` +
            `${STAGE_CHUNK_MAX_RECORDS} records and ${recordChunkHardBytes} bytes.`,
        );
      }
      payloadMode = "json_fragments";
      const payload = Buffer.from(stableStringify(records), "utf8");
      totalPayloadBytes = payload.length;
      chunkBytes = Math.max(
        PREFERRED_STAGE_PAYLOAD_BYTES,
        Math.ceil(payload.length / STAGE_MAX_CHUNKS),
      );
      if (chunkBytes > MODEL_STAGE_FRAGMENT_MAX_BYTES) {
        fail(`generated_code exceeds the ${STAGE_MAX_CHUNKS} MiB fragment limit.`);
      }
      chunks = [];
      for (let offset = 0; offset < payload.length; offset += chunkBytes) {
        chunks.push(payload.subarray(offset, offset + chunkBytes));
      }
      if (chunks.length > STAGE_MAX_CHUNKS) {
        fail(`generated_code exceeds the ${STAGE_MAX_CHUNKS} MiB fragment limit.`);
      }
    }
    const batchDirectory = path.join(stageDirectory, name);
    fs.mkdirSync(batchDirectory, { mode: 0o700 });
    const chunkDocuments = [];
    for (let index = 0; index < chunks.length; index += 1) {
      const chunk = chunks[index];
      const chunkPath = path.join(
        batchDirectory,
        `chunk-${String(index + 1).padStart(2, "0")}.json`,
      );
      const canonical = payloadMode === "records" ? stableStringify(chunk) : chunk;
      if (payloadMode === "records") writeJsonAtomic(chunkPath, chunk);
      else writeJsonAtomic(chunkPath, chunk.toString("base64"));
      chunkDocuments.push({
        index: index + 1,
        file: chunkPath,
        records: payloadMode === "records" ? chunk.length : 0,
        bytes: Buffer.byteLength(canonical),
        sha256: sha256Bytes(canonical),
      });
    }
    batches.push({
      dataset: name,
      payload_mode: payloadMode,
      total_record_count: records.length,
      total_chunk_count: chunkDocuments.length,
      chunk_bytes: chunkBytes,
      ...(totalPayloadBytes === null ? {} : { total_payload_bytes: totalPayloadBytes }),
      batch_sha256: sha256Bytes(
        Buffer.from(chunkDocuments.map((chunk) => chunk.sha256).join(""), "ascii"),
      ),
      chunks: chunkDocuments,
    });
  }

  const strategy = direct && batches.length ? "mixed" : direct ? "direct" : "batched";
  const operations = [];
  let expectedRevisionFrom = "manifest.starting_revision";
  if (direct) {
    operations.push({
      sequence: operations.length + 1,
      tool: `stage_${area}_change_set`,
      payload_file: direct.file,
      expected_revision_from: expectedRevisionFrom,
      returns_revision_for: "next operation",
    });
    expectedRevisionFrom = `operation ${operations.length} response draft_revision`;
  }
  for (const batch of batches) {
    const beginSequence = operations.length + 1;
    operations.push({
      sequence: beginSequence,
      tool: `begin_${area}_stage_batch`,
      dataset: batch.dataset,
      total_record_count: batch.total_record_count,
      total_chunk_count: batch.total_chunk_count,
      payload_mode: batch.payload_mode,
      ...(batch.total_payload_bytes === undefined
        ? {}
        : { total_payload_bytes: batch.total_payload_bytes }),
      batch_sha256: batch.batch_sha256,
      expected_revision_from: expectedRevisionFrom,
      returns_stage_batch_id_for: "following Put and Commit operations",
    });
    for (const chunk of batch.chunks) {
      operations.push({
        sequence: operations.length + 1,
        tool: `put_${area}_stage_chunk`,
        dataset: batch.dataset,
        chunk_index: chunk.index,
        payload_mode: batch.payload_mode,
        payload_file: chunk.file,
        chunk_sha256: chunk.sha256,
        stage_batch_id_from: `operation ${beginSequence} response stage_batch_id`,
      });
    }
    operations.push({
      sequence: operations.length + 1,
      tool: `commit_${area}_stage_batch`,
      dataset: batch.dataset,
      expected_revision_from: "matching begin operation",
      stage_batch_id_from: `operation ${beginSequence} response stage_batch_id`,
      returns_revision_for: "next operation",
    });
    expectedRevisionFrom = `operation ${operations.length} response draft_revision`;
  }
  const manifest = {
    schema_version: "1.0",
    area,
    task: taskId,
    digest: reconciliation.digest,
    change_set_id: draft[0],
    starting_revision: draft[1],
    strategy,
    limits: {
      direct_bytes: DIRECT_STAGE_MAX_BYTES,
      preferred_payload_bytes: PREFERRED_STAGE_PAYLOAD_BYTES,
      hard_chunk_bytes: recordChunkHardBytes,
      chunk_records: STAGE_CHUNK_MAX_RECORDS,
      chunks_per_batch: STAGE_MAX_CHUNKS,
    },
    revision_rule: "Use the returned draft_revision after direct Stage and after every batch commit.",
    direct,
    batches,
    operations,
  };
  const manifestPath = path.join(stageDirectory, "manifest.json");
  writeJsonAtomic(manifestPath, manifest);
  return {
    strategy,
    manifest: manifestPath,
    direct_datasets: direct?.datasets ?? [],
    batch_datasets: batches.map((batch) => batch.dataset),
    operation_count: operations.length,
    next_operation: operations[0],
  };
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

function initializeSession(options) {
  if (!options.root) fail("--root is required.");
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(options.tenant ?? "")) {
    fail("Tenant Code must contain only letters, numbers, dot, underscore, or hyphen.");
  }

  const root = path.resolve(options.root);
  const tenantRoot = path.join(root, "GDS", options.tenant);
  fs.mkdirSync(tenantRoot, { recursive: true, mode: 0o700 });

  const manifestPath = path.join(tenantRoot, "manifest.json");
  const manifest = readManifest(manifestPath);
  const next = manifest.highest + 1;
  const session = next < 100 ? String(next).padStart(2, "0") : String(next);
  const sessionPath = path.join(tenantRoot, session);
  if (fs.existsSync(sessionPath)) {
    fail(`Session ${session} already exists; repair manifest.json before continuing.`);
  }

  fs.mkdirSync(sessionPath, { mode: 0o700 });
  for (const directory of [
    "tasks",
    "metadata",
    "metadata-change-set",
    "model",
    "model-change-set",
    "code",
  ]) {
    fs.mkdirSync(path.join(sessionPath, directory), { mode: 0o700 });
  }
  writeJsonAtomic(path.join(sessionPath, "session.json"), {
    current: null,
    tasks: [],
  });
  writeJsonAtomic(manifestPath, { current: session, highest: next });

  return { tenant: options.tenant, session, path: sessionPath };
}

const READINESS_TARGETS = {
  "metadata-authoring": ["metadata"],
  "model-input-scope": ["metadata", "model"],
  "logical-build": ["metadata", "model"],
  "silver-registration": ["metadata", "model"],
  "logical-binding": ["metadata", "model"],
  "logical-mapping": ["metadata", "model"],
  "logical-code": ["metadata", "model"],
  "dimensional-build": ["metadata", "model"],
  "gold-registration": ["metadata", "model"],
  "dimensional-binding": ["metadata", "model"],
  "dimensional-mapping": ["metadata", "model"],
  "dimensional-code": ["metadata", "model"],
  validation: ["metadata", "model"],
  "process-registration": ["metadata", "model"],
};

function selectedSystemCodes(options) {
  if (options["system-codes"] === undefined) {
    fail("--system-codes is required for Validation readiness.");
  }
  let values;
  try {
    values = JSON.parse(options["system-codes"]);
  } catch {
    fail("--system-codes must be a JSON array of 1..1000 System codes.");
  }
  if (!Array.isArray(values) || values.length < 1 || values.length > 1000) {
    fail("--system-codes must be a JSON array of 1..1000 System codes.");
  }
  const codes = values.map((value) => (typeof value === "string" ? value.trim() : value));
  if (
    codes.some(
      (value) =>
        typeof value !== "string" ||
        !value ||
        value.length > 100 ||
        /[\u0000-\u001f\u007f]/u.test(value),
    )
  ) {
    fail("--system-codes must contain 1..1000 nonblank System codes of at most 100 characters.");
  }
  const normalized = codes.map((value) => unicode.casefold(value));
  if (new Set(normalized).size !== normalized.length) {
    fail("--system-codes must be unique case-insensitively.");
  }
  return codes;
}

function readinessIssueCollector() {
  const counts = new Map();
  const examples = [];
  let truncated = false;
  return {
    add(code, example = null, amount = 1) {
      counts.set(code, (counts.get(code) ?? 0) + amount);
      if (example !== null) {
        if (examples.length < 10) examples.push([code, example]);
        else truncated = true;
      }
    },
    has(code) {
      return counts.has(code);
    },
    output() {
      return {
        blockers: [...counts].map(([code, count]) => [code, count]),
        examples,
        truncated,
      };
    },
  };
}

function readinessPrompt(issues) {
  return issues.has("snapshot_missing") || issues.has("snapshot_stale")
    ? "Create, download, and install each fresh required Snapshot, then resume."
    : "";
}

function workflowReadiness(options) {
  const requiredAreas = READINESS_TARGETS[options.target];
  if (!requiredAreas) {
    fail(`--target must be one of: ${Object.keys(READINESS_TARGETS).join(", ")}.`);
  }
  const systems = options.target === "validation" ? selectedSystemCodes(options) : [];
  if (options.target !== "validation" && options["system-codes"] !== undefined) {
    fail("--system-codes is available only for Validation readiness.");
  }
  const session = requireSessionPath(options.session);
  const state = readSessionState(session);
  const issues = readinessIssueCollector();
  const snapshots = {};
  const inputs = [];
  for (const area of requiredAreas) {
    try {
      const snapshot = locateSnapshot({ session, area });
      snapshots[area] = snapshot;
      inputs.push([
        area,
        snapshot.manifest.snapshot_id ?? null,
        snapshot.manifest.model_revision ?? null,
      ]);
    } catch (error) {
      if (error.message === `Expected exactly one unzipped ${area} Snapshot; found 0.`) {
        issues.add("snapshot_missing", [area]);
        inputs.push([area, null, null]);
      } else {
        throw error;
      }
    }
    if (Array.isArray(state.stale) && state.stale.includes(area)) {
      issues.add("snapshot_stale", [area]);
    }
  }

  const counts = {};
  if (!issues.has("snapshot_missing") && !issues.has("snapshot_stale")) {
    for (const area of requiredAreas) {
      const definitions = [...snapshots[area].byName.values()];
      counts[area] = {
        datasets: definitions.length,
        records: definitions.reduce((total, item) => total + (item.row_count ?? 0), 0),
      };
    }
    if (systems.length) counts.selected_systems = systems.length;
  }
  const issueOutput = issues.output();
  const prompt = readinessPrompt(issues);
  return {
    target: options.target,
    ready: issueOutput.blockers.length === 0,
    inputs,
    counts,
    ...issueOutput,
    ...(prompt ? { resolution_prompt: prompt } : {}),
  };
}

function sessionStatus(options) {
  const session = requireSessionPath(options.session);
  const snapshots = {};
  for (const area of ["metadata", "model"]) {
    try {
      const snapshot = locateSnapshot({ session, area });
      snapshots[area] = [
        snapshot.manifest.snapshot_id ?? null,
        snapshot.manifest.model_revision ?? null,
      ];
    } catch (error) {
      if (error.message === `Expected exactly one unzipped ${area} Snapshot; found 0.`) {
        snapshots[area] = null;
      } else {
        throw error;
      }
    }
  }
  const state = readSessionState(session);
  const current = state.tasks.find((task) => task[0] === state.current) ?? null;
  const resume = current
    ? null
    : state.tasks.find((task) => task[3] === "waiting") ??
      state.tasks.find((task) => new Set(["todo", "queued"]).has(task[3])) ??
      null;
  const planTask = current ?? resume;
  let plan = null;
  let planDigest = null;
  if (planTask) {
    const planPath = path.join(session, "tasks", `${planTask[0]}.json`);
    plan = validatePlan(readJsonFile(planPath, "Active or waiting task plan"));
    planDigest = fileDigest(planPath);
  }
  let acceptance = null;
  if (current) {
    const acceptancePath = path.join(session, "tasks", `${current[0]}.accept.json`);
    if (fs.existsSync(acceptancePath)) {
      const accepted = readJsonFile(acceptancePath, "Task acceptance");
      const offset = accepted?.[1] === "valid" ? 2 : accepted?.[1] === "override" ? 3 : -1;
      if (
        !Array.isArray(accepted) ||
        !/^[0-9a-f]{64}$/.test(accepted[0] ?? "") ||
        offset < 0 ||
        typeof accepted[offset] !== "string" ||
        (accepted[offset + 1] !== null &&
          (!Number.isSafeInteger(accepted[offset + 1]) || accepted[offset + 1] < 0))
      ) {
        fail("Task acceptance has an invalid shape.");
      }
      acceptance = {
        task: current[0],
        digest: accepted[0],
        mode: accepted[1],
        snapshot_id: accepted[offset],
        model_revision: accepted[offset + 1],
      };
    }
  }
  const pending = {};
  for (const area of ["metadata", "model"]) {
    const summary = pendingSummary(pendingDirectory(session, area));
    pending[area] = [summary.files, summary.bytes, summary.digest];
  }
  const stashes = [];
  for (const task of state.tasks) {
    if (!new Set(["metadata", "model"]).has(task[1])) continue;
    const directory = taskStashDirectory(session, task);
    if (!fs.existsSync(directory)) continue;
    const stat = fs.lstatSync(directory);
    if (!stat.isDirectory() || stat.isSymbolicLink()) fail("Task stash must be a regular directory.");
    const summary = pendingSummary(directory);
    if (summary.files === 0) fail("Task stash must not be empty.");
    stashes.push([task[0], task[1], summary.files, summary.digest]);
  }
  return {
    current,
    resume,
    plan,
    plan_digest: planDigest,
    tasks: state.tasks,
    model: state.model ?? null,
    sql_policy: state.sql ?? null,
    cs: state.cs ?? {},
    stale: Array.isArray(state.stale) ? state.stale : [],
    snapshots,
    pending,
    stashes,
    acceptance,
  };
}

function setSqlPolicy(options) {
  const session = requireSessionPath(options.session);
  if (!new Set(["never", "essential", "as_needed"]).has(options.policy)) {
    fail("--policy must be never, essential, or as_needed.");
  }
  const state = readSessionState(session);
  state.sql = options.policy;
  writeJsonAtomic(path.join(session, "session.json"), state);
  return { sql_policy: state.sql };
}

async function main() {
  const { command, options } = parseArguments(process.argv.slice(2));
  let output;
  if (command === "command-contract") output = commandContract(options);
  else if (command === "session-init") output = initializeSession(options);
  else if (command === "status") output = sessionStatus(options);
  else if (command === "sql-policy") output = setSqlPolicy(options);
  else if (command === "readiness") output = workflowReadiness(options);
  else if (command === "inspect") output = inspectSnapshot(options);
  else if (command === "describe") output = describeDataset(options);
  else if (command === "select") output = await selectRecords(options);
  else if (command === "task-add") output = addTask(options);
  else if (command === "task-plan") output = updateTaskPlan(options);
  else if (command === "draft-cache") output = cacheServerDraft(options);
  else if (command === "task-state") output = updateTaskState(options);
  else if (command === "task-stash") output = stashTask(options);
  else if (command === "task-restore") output = restoreTask(options);
  else if (command === "copy") output = await copyRecords(options);
  else if (command === "upsert") output = upsertRecord(options);
  else if (command === "upsert-batch") output = upsertBatch(options);
  else if (command === "discard") output = discardRecord(options);
  else if (command === "review") output = reviewChangeSet(options);
  else if (command === "validate") output = validateChangeSet(options);
  else if (command === "generate-dbml") output = generateLocalDbml(options);
  else if (command === "accept") output = acceptChangeSet(options);
  else if (command === "snapshot-install") output = installSnapshot(options);
  else if (command === "snapshot-refresh") output = acceptRefreshedSnapshot(options);
  else if (command === "reconcile") output = reconcileChangeSet(options);
  else if (command === "prepare-stage") output = prepareStage(options);
  else fail(`Unknown command: ${command}.`);
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

main().catch((error) => {
  process.stderr.write(`gds-local: ${error.message}\n`);
  process.exitCode = 1;
});
