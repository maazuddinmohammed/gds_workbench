import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { lstat, readFile, readdir, realpath, writeFile, rename, unlink } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, sep } from "node:path";
import { stableStringify, SHA256, UUID, MAX_MANIFEST_BYTES, MAX_PATH_CHARACTERS,
 MAX_LOCAL_PAYLOAD_BYTES, ALLOWED_DATASETS, fail, isObject, hasExactKeys,
 recordKey, normalizedTenantCode, type StageRequest, type StageApprovedManifestInput,
 type JsonRecord, type StageRequestDataset, type BackendIdentity } from "./stage-contract.js";
export async function workspaceDigest(
  directory: string,
  maximumPayloadBytes = MAX_LOCAL_PAYLOAD_BYTES.model,
): Promise<string> {
  const entries = await readdir(directory, { withFileTypes: true });
  const hash = createHash("sha256");
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(".json")) {
      fail("LOCAL_CHANGE_SET_INVALID", "Local Change Set contains an unsupported entry.");
    }
    const filePath = join(directory, entry.name);
    const stat = await lstat(filePath);
    if (!stat.isFile() || stat.isSymbolicLink()) {
      fail("LOCAL_CHANGE_SET_INVALID", "Local Change Set contains an unsupported entry.");
    }
    if (stat.size > maximumPayloadBytes) {
      fail("PAYLOAD_LIMIT", "Local Change Set payload exceeds its safe byte limit.");
    }
    hash.update(`${entry.name}\0${stat.size}\0`, "utf8");
    let bytesRead = 0;
    for await (const chunk of createReadStream(filePath)) {
      bytesRead += chunk.length;
      if (bytesRead > stat.size) fail("DIGEST_MISMATCH", "Local Change Set changed while reading.");
      hash.update(chunk);
    }
    if (bytesRead !== stat.size) fail("DIGEST_MISMATCH", "Local Change Set changed while reading.");
  }
  return hash.digest("hex");
}

function containedBy(path: string, root: string): boolean {
  const child = relative(root, path);
  return child === "" || (!child.startsWith(`..${sep}`) && child !== ".." && !isAbsolute(child));
}

export async function readRequest(
  input: StageApprovedManifestInput,
  workspaceRoots: string[],
  backend: BackendIdentity,
): Promise<ApprovedRequest> {
  if (
    !isObject(input) ||
    !hasExactKeys(input, input.recoverOnly === undefined ? ["manifestPath", "expectedDigest"] : ["manifestPath", "expectedDigest", "recoverOnly"]) ||
    (input.recoverOnly !== undefined && typeof input.recoverOnly !== "boolean") ||
    typeof input.manifestPath !== "string" ||
    input.manifestPath.length > MAX_PATH_CHARACTERS ||
    !isAbsolute(input.manifestPath) ||
    typeof input.expectedDigest !== "string" ||
    !SHA256.test(input.expectedDigest) ||
    workspaceRoots.length < 1 ||
    workspaceRoots.length > 32 ||
    workspaceRoots.some(
      (root) => typeof root !== "string" || root.length > MAX_PATH_CHARACTERS || !isAbsolute(root),
    )
  ) {
    fail("INVALID_INPUT", "Manifest path or expected digest is invalid.");
  }
  const inputStat = await lstat(input.manifestPath).catch(() =>
    fail("MANIFEST_NOT_FOUND", "Stage request manifest was not found."),
  );
  if (!inputStat.isFile() || inputStat.isSymbolicLink()) {
    fail("MANIFEST_INVALID", "Stage request manifest must be a regular file.");
  }
  const manifestPath = await realpath(input.manifestPath).catch(() =>
    fail("MANIFEST_NOT_FOUND", "Stage request manifest was not found."),
  );
  const roots = await Promise.all(
    workspaceRoots.map((root) => realpath(root).catch(() => root)),
  );
  if (!roots.some((root) => containedBy(manifestPath, root))) {
    fail("WORKSPACE_BOUNDARY", "Stage request manifest is outside the active workspace.");
  }
  const manifestStat = await lstat(manifestPath);
  if (!manifestStat.isFile() || manifestStat.isSymbolicLink()) {
    fail("MANIFEST_INVALID", "Stage request manifest must be a regular file.");
  }
  if (manifestStat.size > MAX_MANIFEST_BYTES) {
    fail("MANIFEST_LIMIT", "Stage request manifest exceeds its safe byte limit.");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(await readFile(manifestPath, "utf8"));
  } catch {
    fail("MANIFEST_INVALID", "Stage request manifest is not valid JSON.");
  }
  if (
    !isObject(parsed) ||
    !hasExactKeys(parsed, [
      "schema_version",
      "kind",
      "area",
      "task",
      "operation",
      "owner",
      "backend",
      "accepted_digest",
      "failed_retry",
      "snapshot",
      "target",
      "datasets",
    ])
  ) {
    fail("MANIFEST_INVALID", "Stage request manifest is invalid.");
  }
  const request = parsed as unknown as StageRequest;
  if (
    request.schema_version !== "1.0" ||
    request.kind !== "atlas-stage-request" ||
    !["metadata", "model"].includes(request.area) ||
    typeof request.task !== "string" || !UUID.test(request.task) ||
    !SHA256.test(request.accepted_digest) ||
    typeof request.failed_retry !== "boolean" ||
    !isObject(request.snapshot) ||
    !hasExactKeys(request.snapshot, ["manifest_path", "snapshot_id", "manifest_sha256"]) ||
    typeof request.snapshot.snapshot_id !== "string" ||
    !UUID.test(request.snapshot.snapshot_id) ||
    typeof request.snapshot.manifest_sha256 !== "string" ||
    !SHA256.test(request.snapshot.manifest_sha256) ||
    !isObject(request.target) ||
    !hasExactKeys(
      request.target,
      request.area === "metadata"
        ? ["tenant_code", "change_set_id", "starting_revision"]
        : [
            "model_id",
            "model_name",
            "model_revision",
            "change_set_id",
            "starting_revision",
          ],
    ) ||
    typeof request.target.change_set_id !== "string" ||
    !UUID.test(request.target.change_set_id) ||
    !Number.isSafeInteger(request.target.starting_revision) ||
    request.target.starting_revision < 1 ||
    !Array.isArray(request.datasets) ||
    request.datasets.length < 1 ||
    request.datasets.length > (request.area === "metadata" ? 16 : 25)
  ) {
    fail("MANIFEST_INVALID", "Stage request manifest is invalid.");
  }
  if (
    (request.area === "metadata" &&
      (typeof request.target.tenant_code !== "string" ||
        request.target.tenant_code.trim().length < 1 ||
        request.target.tenant_code.length > 100)) ||
    (request.area === "model" &&
      (!Number.isSafeInteger(request.target.model_id) ||
        Number(request.target.model_id) < 1 ||
        typeof request.target.model_name !== "string" ||
        request.target.model_name.trim().length < 1 ||
        request.target.model_name.length > 200 ||
        !Number.isSafeInteger(request.target.model_revision) ||
        Number(request.target.model_revision) < 1))
  ) {
    fail("MANIFEST_INVALID", "Stage request target is invalid.");
  }
  if (request.accepted_digest !== input.expectedDigest) {
    fail("DIGEST_MISMATCH", "Expected digest does not match the approved Stage request.");
  }
  if (!isObject(request.operation) || !hasExactKeys(request.operation, ["id", "path"]) ||
      typeof request.operation.id !== "string" || !UUID.test(request.operation.id) ||
      !isObject(request.owner) || !hasExactKeys(request.owner, ["id", "code", "root"]) ||
      !Number.isSafeInteger(request.owner.id) || request.owner.id < 1 ||
      typeof request.owner.code !== "string" || !request.owner.code.trim() || request.owner.code.length > 100 ||
      !isObject(request.backend) || !hasExactKeys(request.backend, ["profile", "endpoint_sha256"]) ||
      !["production", "local", "azureLocalTest"].includes(request.backend.profile) ||
      typeof request.backend.endpoint_sha256 !== "string" || !SHA256.test(request.backend.endpoint_sha256) ||
      stableStringify(request.backend) !== stableStringify(backend)) {
    fail("LOCAL_STATE_MISMATCH", "Stage owner, operation or backend identity is invalid.");
  }
  const evidenceDirectory = dirname(manifestPath);
  const session = dirname(dirname(dirname(evidenceDirectory)));
  const operationPath = `.atlas/tasks/${request.task}.evidence/${request.operation.id}.json`;
  if (basename(evidenceDirectory) !== `${request.task}.evidence` ||
      basename(dirname(evidenceDirectory)) !== "tasks" ||
      basename(dirname(dirname(evidenceDirectory))) !== ".atlas" ||
      basename(manifestPath) !== `${request.operation.id}.stage-request.json` ||
      request.operation.path !== operationPath) {
    fail("MANIFEST_INVALID", "Stage request is outside its bound operation evidence directory.");
  }
  await safePath(session, relative(session, manifestPath).split(sep).join("/"), "MANIFEST_INVALID");
  const state = await readRegularJson(await safePath(session, ".atlas/session.json", "LOCAL_STATE_MISMATCH"),
    "LOCAL_STATE_MISMATCH", "Atlas session state is invalid.");
  const task = await readRegularJson(await safePath(session, `.atlas/tasks/${request.task}.json`, "LOCAL_STATE_MISMATCH"),
    "LOCAL_STATE_MISMATCH", "Atlas task is invalid.");
  if (!isObject(state) || state.schema_version !== "1.0" || !isObject(state.tenant) ||
      !Number.isSafeInteger(state.tenant.id) || Number(state.tenant.id) < 1 || typeof state.tenant.code !== "string" ||
      !isObject(task) || task.schema_version !== "1.0" || typeof task.outcome !== "string" || !task.outcome.trim()) {
    fail("LOCAL_STATE_MISMATCH", "Atlas session or task binding is invalid.");
  }
  const ownerRoot = request.owner.id === state.tenant.id ? "." : `metadata-owners/tenant-${request.owner.id}`;
  if (request.owner.root !== ownerRoot || (request.area === "model" &&
      (ownerRoot !== "." || normalizedTenantCode(request.owner.code) !== normalizedTenantCode(state.tenant.code))) ||
      (request.area === "metadata" && normalizedTenantCode(request.owner.code) !== normalizedTenantCode(request.target.tenant_code))) {
    fail("TARGET_MISMATCH", "The request owner does not match its workspace placement.");
  }
  if (request.area === "metadata") {
    const registered = isObject(state.metadata_owners) ? state.metadata_owners[String(request.owner.id)] : undefined;
    if (!isObject(registered) || registered.id !== request.owner.id || registered.root !== ownerRoot ||
        normalizedTenantCode(registered.code) !== normalizedTenantCode(request.owner.code)) {
      fail("LOCAL_STATE_MISMATCH", "Metadata owner is not registered in this workspace.");
    }
  } else if (!isObject(state.model) || state.model.id !== request.target.model_id || state.model.name !== request.target.model_name) {
    fail("LOCAL_STATE_MISMATCH", "The workspace is bound to a different Model.");
  }
  const current = isObject(state.operations)
    ? request.area === "model" ? state.operations.model
      : isObject(state.operations.metadata) ? state.operations.metadata[String(request.owner.id)] : undefined
    : undefined;
  if (current !== operationPath) fail("LOCAL_STATE_MISMATCH", "The operation is no longer current for this owner.");
  const operationFile = await safePath(session, operationPath, "LOCAL_STATE_MISMATCH");
  const operationBytes = await readBounded(operationFile, "LOCAL_STATE_MISMATCH");
  let operation: unknown;
  try { operation = JSON.parse(operationBytes.toString("utf8")); }
  catch { fail("LOCAL_STATE_MISMATCH", "The operation record is invalid."); }
  if (!isObject(operation) || operation.schema_version !== "1.0" || operation.id !== request.operation.id ||
      operation.task_id !== request.task || operation.area !== request.area ||
      stableStringify(operation.owner) !== stableStringify(request.owner) ||
      stableStringify(operation.backend) !== stableStringify(request.backend) ||
      operation.local_digest !== request.accepted_digest || !Array.isArray(operation.inputs) ||
      !isObject(operation.validation) || operation.validation.outcome !== "valid" ||
      !isObject(operation.acknowledgement) || operation.acknowledgement.source !== "conversation" ||
      typeof operation.acknowledgement.at !== "string" || !Number.isFinite(Date.parse(operation.acknowledgement.at)) ||
      operation.acknowledgement.digest !== request.accepted_digest ||
      operation.acknowledgement.report_sha256 !== operation.validation.report_sha256 ||
      !isObject(operation.draft) || String(operation.draft.id).toLowerCase() !== request.target.change_set_id.toLowerCase() ||
      operation.draft.revision !== request.target.starting_revision || operation.draft.status !== "active") {
    fail("LOCAL_STATE_MISMATCH", "Approval, validation or draft binding no longer matches this request.");
  }
  const digestMatches = operation.draft.digest === request.accepted_digest;
  if ((!request.failed_retry && !digestMatches) ||
      (request.failed_retry && (digestMatches || operation.draft.validation_failed !== true))) {
    fail("LOCAL_STATE_MISMATCH", "The failed-draft recovery binding is invalid.");
  }
  if (isObject(operation.stage) && operation.stage.status === "staged" && !request.failed_retry) {
    fail("ALREADY_STAGED", "Inspect the verified Stage receipt before submitting this operation again.");
  }
  if (isObject(operation.stage_attempt) && operation.stage_attempt.status === "unknown" && input.recoverOnly !== true) {
    fail("STAGE_OUTCOME_UNKNOWN", "Inspect the prior uncertain Stage attempt before retrying.");
  }
  if (!isObject(operation.stage_request) || operation.stage_request.path !== relative(session, manifestPath).split(sep).join("/") ||
      operation.stage_request.sha256 !== sha256(await readBounded(manifestPath, "MANIFEST_LIMIT"))) {
    fail("MANIFEST_CHANGED", "The Stage request changed after preparation.");
  }
  const reportPath = operation.validation.report_path;
  if (typeof reportPath !== "string" || !reportPath.startsWith(`.atlas/tasks/${request.task}.evidence/`) ||
      typeof operation.validation.report_sha256 !== "string" || !SHA256.test(operation.validation.report_sha256) ||
      sha256(await readBounded(await safePath(session, reportPath, "MODELING_EVIDENCE_CHANGED"), "MODELING_EVIDENCE_CHANGED")) !== operation.validation.report_sha256) {
    fail("MODELING_EVIDENCE_CHANGED", "The reviewed local validation report changed or is missing.");
  }
  const report = await readRegularJson(await safePath(session, reportPath, "MODELING_EVIDENCE_CHANGED"),
    "MODELING_EVIDENCE_CHANGED", "The reviewed validation report is invalid.");
  if (!isObject(report) || report.schema_version !== "1.0" || report.valid !== true ||
      report.digest !== request.accepted_digest || report.area !== request.area ||
      report.owner_tenant_id !== request.owner.id || !Array.isArray(report.evidence_files) ||
      stableStringify(report.inputs) !== stableStringify(operation.inputs)) {
    fail("MODELING_EVIDENCE_CHANGED", "Validation does not cover the acknowledged owner, inputs and content.");
  }
  for (const evidence of report.evidence_files) {
    if (!isObject(evidence) || typeof evidence.path !== "string" ||
        (evidence.sha256 !== null && (typeof evidence.sha256 !== "string" || !SHA256.test(evidence.sha256)))) {
      fail("MODELING_EVIDENCE_CHANGED", "Validation evidence binding is invalid.");
    }
    const file = await safePath(session, evidence.path, "MODELING_EVIDENCE_CHANGED", false, evidence.sha256 === null);
    if (evidence.sha256 === null) {
      const stat = await lstat(file).catch((error: NodeJS.ErrnoException) => {
        if (error.code === "ENOENT") return null;
        fail("MODELING_EVIDENCE_CHANGED", "Validation evidence cannot be inspected.");
      });
      if (stat !== null) fail("MODELING_EVIDENCE_CHANGED", "Evidence changed after validation.");
    } else if (sha256(await readBounded(file, "MODELING_EVIDENCE_CHANGED")) !== evidence.sha256) {
      fail("MODELING_EVIDENCE_CHANGED", "Evidence changed after validation.");
    }
  }
  const expectedSnapshotPath = `${ownerRoot === "." ? "" : ownerRoot + "/"}${request.area}/${request.area}-snapshot/manifest.json`;
  if (request.snapshot.manifest_path !== expectedSnapshotPath) fail("SNAPSHOT_MISMATCH", "Snapshot belongs to a different owner root.");
  let primaryInput = false;
  for (const binding of operation.inputs) {
    if (!isObject(binding) || !["metadata", "model"].includes(String(binding.area)) ||
        !Number.isSafeInteger(binding.owner_tenant_id) || Number(binding.owner_tenant_id) < 1 ||
        typeof binding.manifest_path !== "string" || typeof binding.snapshot_id !== "string" || !UUID.test(binding.snapshot_id) ||
        typeof binding.manifest_sha256 !== "string" || !SHA256.test(binding.manifest_sha256)) {
      fail("SNAPSHOT_MISMATCH", "An operation Snapshot binding is invalid.");
    }
    const inputOwner = binding.area === "model" ? state.tenant
      : isObject(state.metadata_owners) ? state.metadata_owners[String(binding.owner_tenant_id)] : undefined;
    const inputRoot = binding.owner_tenant_id === state.tenant.id ? "." : `metadata-owners/tenant-${binding.owner_tenant_id}`;
    const inputPath = `${inputRoot === "." ? "" : inputRoot + "/"}${binding.area}/${binding.area}-snapshot/manifest.json`;
    if (!isObject(inputOwner) || inputOwner.id !== binding.owner_tenant_id ||
        binding.manifest_path !== inputPath || (binding.area === "metadata" && inputOwner.root !== inputRoot) ||
        (binding.area === "model" && (binding.owner_tenant_id !== state.tenant.id ||
          !isObject(state.model) || !Number.isSafeInteger(binding.model_revision) || Number(binding.model_revision) < 1))) {
      fail("SNAPSHOT_MISMATCH", "An input Snapshot owner or path is not registered in this workspace.");
    }
    if (Array.isArray(state.refresh_required) && state.refresh_required.some((item) => isObject(item) &&
        item.area === binding.area && item.owner_tenant_id === binding.owner_tenant_id)) {
      fail("MODELING_EVIDENCE_CHANGED", "An input Snapshot is marked stale.");
    }
    const bytes = await readBounded(await safePath(session, binding.manifest_path, "SNAPSHOT_MISMATCH"), "SNAPSHOT_MISMATCH");
    let inputManifest: unknown;
    try { inputManifest = JSON.parse(bytes.toString("utf8")); } catch { fail("SNAPSHOT_MISMATCH", "An input Snapshot is invalid."); }
    if (sha256(bytes) !== binding.manifest_sha256 || !isObject(inputManifest) ||
        inputManifest.snapshot_id !== binding.snapshot_id || inputManifest.snapshot_kind !== binding.area ||
        (binding.area === "model" && (inputManifest.model_revision !== binding.model_revision ||
          !isObject(state.model) || inputManifest.model_id !== state.model.id || inputManifest.model_name !== state.model.name)) ||
        (binding.area === "metadata" && normalizedTenantCode(inputManifest.tenant_code) !== normalizedTenantCode(inputOwner.code))) {
      fail("SNAPSHOT_MISMATCH", "An input Snapshot changed after acknowledgement.");
    }
    if (binding.area === request.area && binding.owner_tenant_id === request.owner.id &&
        binding.manifest_path === request.snapshot.manifest_path && binding.snapshot_id === request.snapshot.snapshot_id &&
        binding.manifest_sha256 === request.snapshot.manifest_sha256 &&
        (request.area !== "model" || binding.model_revision === request.target.model_revision)) primaryInput = true;
  }
  if (!primaryInput) fail("SNAPSHOT_MISMATCH", "The operation does not bind the Stage Snapshot.");
  const changeSetDirectory = await safePath(session, `${ownerRoot === "." ? "" : ownerRoot + "/"}${request.area}-change-set`, "LOCAL_CHANGE_SET_INVALID", true);
  if ((await workspaceDigest(changeSetDirectory, MAX_LOCAL_PAYLOAD_BYTES[request.area])) !== input.expectedDigest) {
    fail("DIGEST_MISMATCH", "Local Change Set changed after user acknowledgement.");
  }
  await verifySnapshotBinding(request, session);
  return { request, session, changeSetDirectory, operationFile, operation, operationSha256: sha256(operationBytes) };
}

export interface ApprovedRequest {
  request: StageRequest;
  session: string;
  changeSetDirectory: string;
  operationFile: string;
  operation: JsonRecord;
  operationSha256: string;
}

const sha256 = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");

async function readBounded(filePath: string, code: string): Promise<Buffer> {
  const stat = await lstat(filePath).catch(() => fail(code, "A bound local file was not found."));
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 4 * 1024 * 1024) fail(code, "A bound local file is invalid or too large.");
  const bytes = await readFile(filePath);
  if (bytes.length !== stat.size) fail(code, "A bound local file changed while reading.");
  return bytes;
}

async function readRegularJson(filePath: string, code: string, message: string): Promise<unknown> {
  try { return JSON.parse((await readBounded(filePath, code)).toString("utf8")); }
  catch { fail(code, message); }
}

async function safePath(root: string, local: string, code: string, directory = false, missingLeaf = false): Promise<string> {
  if (typeof local !== "string" || !local || local.length > MAX_PATH_CHARACTERS || isAbsolute(local) ||
      local.includes("\\") || local.split("/").some((part) => !part || part === "." || part === "..")) {
    fail(code, "A workspace-relative path is invalid.");
  }
  let current = root;
  const parts = local.split("/");
  for (const [index, part] of parts.entries()) {
    current = join(current, part);
    const stat = await lstat(current).catch((error: NodeJS.ErrnoException) => {
      if (missingLeaf && index === parts.length - 1 && error.code === "ENOENT") return null;
      fail(code, "A bound local path was not found.");
    });
    if (stat === null) return current;
    if (stat.isSymbolicLink() || (index < parts.length - 1 || directory ? !stat.isDirectory() : !stat.isFile())) {
      fail(code, "A bound local path is not a regular workspace path.");
    }
  }
  if (!containedBy(await realpath(current), root)) fail("WORKSPACE_BOUNDARY", "A bound path escaped the workspace.");
  return current;
}

export async function saveOperation(approved: ApprovedRequest, updates: JsonRecord): Promise<void> {
  await safePath(approved.session, approved.request.operation.path, "LOCAL_STATE_MISMATCH");
  if (sha256(await readBounded(approved.operationFile, "LOCAL_STATE_MISMATCH")) !== approved.operationSha256) {
    fail("LOCAL_STATE_MISMATCH", "Operation evidence changed before checkpoint storage.");
  }
  const next = { ...approved.operation, ...updates };
  const bytes = Buffer.from(`${JSON.stringify(next, null, 2)}\n`, "utf8");
  const temporary = `${approved.operationFile}.${randomUUID()}.tmp`;
  try {
    await writeFile(temporary, bytes, { flag: "wx", mode: 0o600 });
    if (sha256(await readBounded(approved.operationFile, "LOCAL_STATE_MISMATCH")) !== approved.operationSha256) {
      fail("LOCAL_STATE_MISMATCH", "Operation evidence changed before checkpoint replacement.");
    }
    await rename(temporary, approved.operationFile);
  } finally { await unlink(temporary).catch(() => undefined); }
  approved.operation = next;
  approved.operationSha256 = sha256(bytes);
}

async function verifySnapshotBinding(request: StageRequest, session: string): Promise<void> {
  const snapshotPath = await safePath(session, request.snapshot.manifest_path, "SNAPSHOT_MISMATCH");
  const snapshotDirectory = dirname(snapshotPath);
  const manifestBytes = await readBounded(snapshotPath, "SNAPSHOT_MISMATCH");
  if (
    createHash("sha256").update(manifestBytes).digest("hex") !==
    request.snapshot.manifest_sha256
  ) {
    fail("SNAPSHOT_MISMATCH", "The bound Snapshot changed after Stage preparation.");
  }
  let manifest: unknown;
  try {
    manifest = JSON.parse(manifestBytes.toString("utf8"));
  } catch {
    fail("SNAPSHOT_MISMATCH", "The bound Snapshot manifest is invalid.");
  }
  if (
    !isObject(manifest) ||
    manifest.snapshot_kind !== request.area ||
    manifest.snapshot_id !== request.snapshot.snapshot_id
  ) {
    fail("SNAPSHOT_MISMATCH", "The Stage request does not match its bound Snapshot.");
  }
  if (
    !isObject(manifest.catalog) ||
    manifest.catalog.path !== "catalog.json" ||
    typeof manifest.catalog.sha256 !== "string" ||
    !SHA256.test(manifest.catalog.sha256) ||
    !Array.isArray(manifest.members)
  ) {
    fail("SNAPSHOT_MISMATCH", "The bound Snapshot catalog descriptor is invalid.");
  }
  const catalogBytes = await readBounded(await safePath(session, relative(session, join(snapshotDirectory, "catalog.json")).split(sep).join("/"), "SNAPSHOT_MISMATCH"), "SNAPSHOT_MISMATCH");
  const catalogSha256 = createHash("sha256").update(catalogBytes).digest("hex");
  const catalogMember = manifest.members.find(
    (member) => isObject(member) && member.path === "catalog.json",
  );
  if (
    catalogSha256 !== manifest.catalog.sha256 ||
    !isObject(catalogMember) ||
    catalogMember.sha256 !== catalogSha256 ||
    catalogMember.size_bytes !== catalogBytes.length
  ) {
    fail("SNAPSHOT_MISMATCH", "The bound Snapshot catalog changed or is invalid.");
  }
  let catalog: unknown;
  try {
    catalog = JSON.parse(catalogBytes.toString("utf8"));
  } catch {
    fail("SNAPSHOT_MISMATCH", "The bound Snapshot catalog is invalid.");
  }
  if (!isObject(catalog) || catalog.snapshot_kind !== request.area || !Array.isArray(catalog.sections)) {
    fail("SNAPSHOT_MISMATCH", "The bound Snapshot catalog identity is invalid.");
  }
  const catalogDatasets = new Map<string, string[]>();
  for (const section of catalog.sections) {
    if (!isObject(section) || !Array.isArray(section.datasets)) {
      fail("SNAPSHOT_MISMATCH", "The bound Snapshot catalog datasets are invalid.");
    }
    for (const dataset of section.datasets) {
      if (
        !isObject(dataset) ||
        typeof dataset.name !== "string" ||
        !Array.isArray(dataset.canonical_key) ||
        dataset.canonical_key.some((field) => typeof field !== "string" || !field) ||
        catalogDatasets.has(dataset.name)
      ) {
        fail("SNAPSHOT_MISMATCH", "The bound Snapshot catalog datasets are invalid.");
      }
      catalogDatasets.set(dataset.name, dataset.canonical_key as string[]);
    }
  }
  for (const dataset of request.datasets) {
    if (
      !ALLOWED_DATASETS[request.area].has(dataset.dataset) ||
      stableStringify(catalogDatasets.get(dataset.dataset)) !==
        stableStringify(dataset.canonical_key)
    ) {
      fail("SNAPSHOT_MISMATCH", "A Stage dataset differs from the bound Snapshot contract.");
    }
  }
  if (request.area === "metadata") {
    if (
      typeof request.target.tenant_code !== "string" ||
      normalizedTenantCode(manifest.tenant_code) !==
        normalizedTenantCode(request.target.tenant_code)
    ) {
      fail("TARGET_MISMATCH", "Metadata Stage target does not match its Snapshot and session.");
    }
  } else if (
    manifest.model_id !== request.target.model_id ||
    manifest.model_name !== request.target.model_name ||
    manifest.model_revision !== request.target.model_revision ||
    !isObject(catalog.model) ||
    catalog.model.model_id !== request.target.model_id ||
    catalog.model.model_name !== request.target.model_name ||
    catalog.model.model_revision !== request.target.model_revision
  ) {
    fail("TARGET_MISMATCH", "Model Stage target does not match its Snapshot.");
  }
}

export async function readLocalDatasets(
  request: StageRequest,
  changeSetDirectory: string,
  workspace: string,
): Promise<Map<string, { definition: StageRequestDataset; records: JsonRecord[] }>> {
  const result = new Map<string, { definition: StageRequestDataset; records: JsonRecord[] }>();
  let previousDataset = "";
  for (const definition of request.datasets) {
    const maximumRecords = request.area === "metadata" ? 50_000 : 20_000;
    if (
      !isObject(definition) ||
      !hasExactKeys(definition, [
        "dataset",
        "canonical_key",
        "record_count",
        "payload_file",
        "sha256",
      ]) ||
      typeof definition.dataset !== "string" ||
      !/^[a-z][a-z0-9_]{0,99}$/.test(definition.dataset) ||
      !ALLOWED_DATASETS[request.area].has(definition.dataset) ||
      !Array.isArray(definition.canonical_key) ||
      (definition.canonical_key.length < 1 &&
        !(request.area === "model" && definition.dataset === "model_details")) ||
      definition.canonical_key.length > 16 ||
      definition.canonical_key.some(
        (field) => typeof field !== "string" || !/^[a-z][a-z0-9_]{0,99}$/.test(field),
      ) ||
      new Set(definition.canonical_key).size !== definition.canonical_key.length ||
      !Number.isSafeInteger(definition.record_count) ||
      definition.record_count < 0 ||
      definition.record_count > maximumRecords ||
      typeof definition.payload_file !== "string" ||
      definition.payload_file.length > MAX_PATH_CHARACTERS ||
      isAbsolute(definition.payload_file) ||
      typeof definition.sha256 !== "string" ||
      !SHA256.test(definition.sha256) ||
      result.has(definition.dataset) ||
      definition.dataset.localeCompare(previousDataset) <= 0
    ) {
      fail("MANIFEST_INVALID", "Stage request contains an invalid dataset descriptor.");
    }
    previousDataset = definition.dataset;
    const payloadPath = await safePath(workspace, definition.payload_file, "PAYLOAD_INVALID");
    if (
      payloadPath !== join(changeSetDirectory, `${definition.dataset}.json`) ||
      !containedBy(payloadPath, changeSetDirectory)
    ) {
      fail("WORKSPACE_BOUNDARY", `${definition.dataset} payload is outside its Change Set.`);
    }
    const stat = await lstat(payloadPath);
    if (!stat.isFile() || stat.isSymbolicLink()) {
      fail("PAYLOAD_INVALID", `${definition.dataset} payload must be a regular file.`);
    }
    if (stat.size > MAX_LOCAL_PAYLOAD_BYTES[request.area]) {
      fail("PAYLOAD_LIMIT", `${definition.dataset} payload exceeds its safe byte limit.`);
    }
    const bytes = await readFile(payloadPath);
    if (createHash("sha256").update(bytes).digest("hex") !== definition.sha256) {
      fail("DIGEST_MISMATCH", `${definition.dataset} payload hash changed.`);
    }
    let value: unknown;
    try {
      value = JSON.parse(bytes.toString("utf8"));
    } catch {
      fail("PAYLOAD_INVALID", `${definition.dataset} payload is not valid JSON.`);
    }
    if (!Array.isArray(value) || value.some((record) => !isObject(record))) {
      fail("PAYLOAD_INVALID", `${definition.dataset} payload must contain complete records.`);
    }
    const records = value as JsonRecord[];
    if (records.length !== definition.record_count) {
      fail("DIGEST_MISMATCH", `${definition.dataset} record count changed.`);
    }
    const keys = new Set(records.map((record) => recordKey(request.area, definition, record)));
    if (keys.size !== records.length) {
      fail("PAYLOAD_INVALID", `${definition.dataset} contains a duplicate canonical key.`);
    }
    result.set(definition.dataset, { definition, records });
  }
  if ((await readdir(changeSetDirectory)).length !== result.size) {
    fail("DIGEST_MISMATCH", "Stage request does not cover the complete local Change Set.");
  }
  return result;
}

