"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const hash = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const digest = /^[0-9a-f]{64}$/;
const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

function safePath(root, relative, createDirectories = false) {
  if (typeof relative !== "string" || !relative || path.isAbsolute(relative) ||
      /^[A-Za-z]:/.test(relative) || /[\\\0]/.test(relative) ||
      relative.split("/").some((part) => !part || part === "." || part === "..")) {
    throw Error("Expected a contained workspace-relative path.");
  }
  let current = root;
  const rootStat = fs.lstatSync(root);
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) throw Error("Workspace must be a regular directory.");
  const parts = relative.split("/");
  for (let index = 0; index < parts.length; index++) {
    current = path.join(current, parts[index]);
    if (!fs.existsSync(current)) {
      // lstat also detects dangling links, which existsSync does not.
      try { fs.lstatSync(current); throw Error("Workspace path is a dangling link."); }
      catch (error) { if (error.code !== "ENOENT") throw error; }
      if (index < parts.length - 1 && createDirectories) fs.mkdirSync(current, {mode: 0o700});
      else if (index < parts.length - 1) throw Error("Workspace parent directory is missing.");
      else return current;
    }
    const stat = fs.lstatSync(current);
    if (stat.isSymbolicLink() || (index < parts.length - 1 && !stat.isDirectory())) {
      throw Error("Workspace paths must not traverse symbolic links or non-directories.");
    }
  }
  return current;
}

function read(root, relative) {
  const file = safePath(root, relative);
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.size > 16 * 1024 * 1024) throw Error("Workspace JSON must be a bounded regular file.");
  const bytes = fs.readFileSync(file);
  return {value: JSON.parse(bytes.toString("utf8")), digest: hash(bytes), path: file};
}

function write(root, relative, value, expected = "absent") {
  const file = safePath(root, relative, true);
  const check = () => {
    if (fs.existsSync(file)) {
      if (expected === "absent" || !digest.test(expected) || read(root, relative).digest !== expected) {
        throw Error("Workspace file changed; reread before writing.");
      }
    } else if (expected !== "absent") throw Error("Workspace file disappeared; reread before writing.");
  };
  check();
  const temporary = `${file}.${crypto.randomUUID()}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value)}\n`, {flag: "wx", mode: 0o600});
  try { check(); fs.renameSync(temporary, file); }
  finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
  return hash(fs.readFileSync(file));
}

function identity(value, label) {
  if (!object(value) || !Number.isSafeInteger(value.id) || value.id < 1 ||
      typeof value.code !== "string" || !value.code.trim() || value.code.length > 255) {
    throw Error(`${label} needs a verified positive ID and nonblank code.`);
  }
}

function session(root) {
  const document = read(root, ".atlas/session.json");
  const state = document.value;
  if (!object(state) || state.schema_version !== "1.0") throw Error("Invalid Atlas session version.");
  identity(state.tenant, "Tenant");
  if (state.model !== null && (!object(state.model) || !Number.isSafeInteger(state.model.id) ||
      state.model.id < 1 || typeof state.model.name !== "string" || !state.model.name.trim())) {
    throw Error("Invalid active Model identity.");
  }
  if (state.active_task !== null && !uuid.test(state.active_task ?? "")) throw Error("Invalid active task ID.");
  if (state.sql !== undefined && (!object(state.sql) || !["never", "essential", "proactive"].includes(state.sql.policy) ||
      (state.sql.environment !== undefined && !["dev", "qa", "stg", "prod"].includes(state.sql.environment)))) {
    throw Error("Invalid SQL policy/environment.");
  }
  if (state.metadata_owners !== undefined && !object(state.metadata_owners)) throw Error("Invalid Metadata owner registry.");
  for (const [id, owner] of Object.entries(state.metadata_owners ?? {})) {
    identity(owner, "Metadata owner");
    if (String(owner.id) !== id || owner.root !== (owner.id === state.tenant.id ? "." : `metadata-owners/tenant-${owner.id}`) ||
        (owner.id === state.tenant.id && owner.code !== state.tenant.code)) throw Error("Metadata owner registry conflicts with workspace identity.");
  }
  if (state.refresh_required !== undefined && (!Array.isArray(state.refresh_required) || state.refresh_required.some((entry) =>
    !object(entry) || !["metadata", "model"].includes(entry.area) || !Number.isSafeInteger(entry.owner_tenant_id) || entry.owner_tenant_id < 1))) {
    throw Error("Invalid Snapshot refresh markers.");
  }
  return document;
}

function owner(state, area, selected) {
  if (!["metadata", "model"].includes(area)) throw Error("--area must be metadata or model.");
  const id = selected === undefined ? state.tenant.id : Number(selected);
  if (!Number.isSafeInteger(id) || id < 1) throw Error("--owner must be a positive Tenant ID.");
  if (area === "model") {
    if (id !== state.tenant.id) throw Error("Model ownership must match the primary Tenant.");
    return {id: state.tenant.id, code: state.tenant.code, root: "."};
  }
  if (id === state.tenant.id) return {id: state.tenant.id, code: state.tenant.code, root: "."};
  const result = state.metadata_owners?.[String(id)];
  if (!result || !state.model) throw Error("Additional Metadata owner requires a selected Model and registered owner.");
  return {id: result.id, code: result.code, root: result.root};
}

function task(root, id) {
  if (!uuid.test(id ?? "")) throw Error("A task UUID is required.");
  const document = read(root, `.atlas/tasks/${id}.json`);
  const value = document.value;
  if (!object(value) || value.schema_version !== "1.0" || typeof value.outcome !== "string" || !value.outcome.trim() ||
      (value.progress !== undefined && typeof value.progress !== "string") ||
      (value.inputs !== undefined && !object(value.inputs)) ||
      ["work", "evidence"].some((key) => value[key] !== undefined && (!Array.isArray(value[key]) || value[key].some((entry) =>
        !object(entry) || typeof entry.path !== "string" || typeof entry.purpose !== "string")))) {
    throw Error("Invalid Atlas task; outcome is required and progress stays free-form.");
  }
  return document;
}

function operation(root, state, area, selectedOwner) {
  const relative = area === "model" ? state.operations?.model : state.operations?.metadata?.[String(selectedOwner.id)];
  if (!relative) throw Error("A digest-bound acknowledgement is required first.");
  const document = read(root, relative);
  const value = document.value;
  if (!object(value) || value.schema_version !== "1.0" || !uuid.test(value.id ?? "") || !uuid.test(value.task_id ?? "") ||
      relative !== `.atlas/tasks/${value.task_id}.evidence/${value.id}.json` || value.area !== area ||
      value.owner?.id !== selectedOwner.id || value.owner?.code !== selectedOwner.code || value.owner?.root !== selectedOwner.root ||
      !digest.test(value.local_digest ?? "")) throw Error("Operation evidence does not match its owner/area/path.");
  task(root, value.task_id);
  return {...document, relative};
}

module.exports = {safePath, read, write, session, owner, task, operation, identity, object, uuid, digest, hash};
