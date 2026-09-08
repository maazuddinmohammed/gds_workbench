import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import {
  lstat,
  readFile,
  readdir,
  realpath,
} from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, sep } from "node:path";

import { unicodeCasefold, unicodeLower } from "./unicode.js";
// @ts-expect-error The shared CommonJS asset intentionally has no declaration file.
import workbenchCore from "../../gds/skills/gds/workbench/core.js";

const stableStringify = workbenchCore.stableStringify as (value: unknown) => string;

const SHA256 = /^[0-9a-f]{64}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_MANIFEST_BYTES = 128 * 1024;
const MAX_PATH_CHARACTERS = 4_096;
const DIRECT_STAGE_MAX_BYTES = 64 * 1024;
const MAX_STAGE_CHUNKS = 64;
const MAX_STAGE_CHUNK_RECORDS = 5_000;
const METADATA_STAGE_CHUNK_MAX_BYTES = 450 * 1024;
const MODEL_STAGE_CHUNK_MAX_BYTES = 1024 * 1024;
const MAX_LOCAL_PAYLOAD_BYTES: Record<Area, number> = {
  metadata: MAX_STAGE_CHUNKS * METADATA_STAGE_CHUNK_MAX_BYTES + 1024,
  model: MAX_STAGE_CHUNKS * MODEL_STAGE_CHUNK_MAX_BYTES + 1024,
};
const ALLOWED_DATASETS: Record<Area, ReadonlySet<string>> = {
  metadata: new Set([
    "source_object",
    "source_attribute",
    "bronze_object",
    "bronze_attribute",
    "silver_object",
    "silver_attribute",
    "gold_object",
    "gold_attribute",
    "ingestion_object_mapping",
    "ingestion_attribute_mapping",
    "copy_group",
    "member_group",
    "copy_group_control",
    "copy",
    "process_group",
    "process",
  ]),
  model: new Set([
    "model_details",
    "model_input_scope",
    "profiling_profile",
    "analysis_result",
    "modeling_assertion_document",
    "modeling_assertion_record",
    "conceptual_object",
    "conceptual_relationship",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "model_object_binding",
    "model_attribute_binding",
    "mapping_dependency",
    "mapping_object",
    "mapping_attribute",
    "generated_code",
    "generated_code_source_system",
    "validation_group",
    "validation_check",
  ]),
};

type Area = "metadata" | "model";
type JsonRecord = Record<string, unknown>;

interface StageRequestDataset {
  dataset: string;
  canonical_key: string[];
  record_count: number;
  payload_file: string;
  sha256: string;
}

interface StageRequest {
  schema_version: "2.0";
  kind: "gds-stage-request";
  area: Area;
  task: string;
  accepted_digest: string;
  failed_retry: boolean;
  snapshot: {
    snapshot_id: string;
    manifest_sha256: string;
  };
  target: {
    tenant_code?: string;
    model_id?: number;
    model_name?: string;
    model_revision?: number;
    change_set_id: string;
    starting_revision: number;
  };
  datasets: StageRequestDataset[];
}

export interface McpToolClient {
  callTool(name: string, input: Record<string, unknown>): Promise<unknown>;
}

export interface StageApprovedManifestInput {
  manifestPath: string;
  expectedDigest: string;
}

export interface StageRunnerDependencies {
  mcp: McpToolClient;
  workspaceRoots: string[];
  isCancellationRequested?: () => boolean;
  onWriteStart?: () => void;
}

export interface StageReceipt {
  schemaVersion: "1.0";
  status: "staged";
  area: Area;
  changeSetId: string;
  startingRevision: number;
  resultingRevision: number;
  acceptedDigest: string;
  stageFingerprint: string;
  fingerprintVerified: true;
  datasets: Array<{ dataset: string; recordCount: number }>;
}

export class StageRunnerError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
    this.name = "StageRunnerError";
  }
}

function fail(code: string, message: string): never {
  throw new StageRunnerError(code, message);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const required = [...expected].sort();
  return actual.length === required.length && actual.every((key, index) => key === required[index]);
}

export function canonicalRecordsSha256(records: JsonRecord[]): string {
  return createHash("sha256").update(stableStringify(records), "utf8").digest("hex");
}

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

function requireObject(value: unknown, code: string): Record<string, unknown> {
  if (!isObject(value)) fail(code, "Stage Runner received an unexpected MCP response.");
  return value;
}

function containedBy(path: string, root: string): boolean {
  const child = relative(root, path);
  return child === "" || (!child.startsWith(`..${sep}`) && child !== ".." && !isAbsolute(child));
}

async function readRequest(
  input: StageApprovedManifestInput,
  workspaceRoots: string[],
): Promise<{ request: StageRequest; session: string; changeSetDirectory: string }> {
  if (
    !isObject(input) ||
    !hasExactKeys(input, ["manifestPath", "expectedDigest"]) ||
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
    request.schema_version !== "2.0" ||
    request.kind !== "gds-stage-request" ||
    !["metadata", "model"].includes(request.area) ||
    !/^\d{2,12}$/.test(request.task) ||
    !SHA256.test(request.accepted_digest) ||
    typeof request.failed_retry !== "boolean" ||
    !isObject(request.snapshot) ||
    !hasExactKeys(request.snapshot, ["snapshot_id", "manifest_sha256"]) ||
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
  const tasksDirectory = dirname(manifestPath);
  if (
    tasksDirectory.split(sep).at(-1) !== "tasks" ||
    basename(manifestPath) !== `${request.task}.stage-request.json`
  ) {
    fail("MANIFEST_INVALID", "Stage request manifest is outside the session tasks directory.");
  }
  const session = dirname(tasksDirectory);
  const changeSetDirectory = join(session, `${request.area}-change-set`);
  const directoryStat = await lstat(changeSetDirectory).catch(
    () => fail("LOCAL_CHANGE_SET_INVALID", "Local Change Set directory was not found."),
  );
  if (!directoryStat.isDirectory() || directoryStat.isSymbolicLink()) {
    fail("LOCAL_CHANGE_SET_INVALID", "Local Change Set must be a regular session directory.");
  }
  if ((await workspaceDigest(changeSetDirectory, MAX_LOCAL_PAYLOAD_BYTES[request.area])) !== input.expectedDigest) {
    fail("DIGEST_MISMATCH", "Local Change Set changed after user acknowledgement.");
  }
  await verifyLocalStateBinding(request, session);
  await verifySnapshotBinding(request, session);
  return { request, session, changeSetDirectory };
}

async function readRegularJson(filePath: string, code: string, message: string): Promise<unknown> {
  const stat = await lstat(filePath).catch(() => fail(code, message));
  if (!stat.isFile() || stat.isSymbolicLink()) fail(code, message);
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch {
    fail(code, message);
  }
}

async function verifyLocalStateBinding(request: StageRequest, session: string): Promise<void> {
  const state = await readRegularJson(
    join(session, "session.json"),
    "LOCAL_STATE_MISMATCH",
    "The GDS session state is invalid.",
  );
  if (!isObject(state) || state.current !== request.task || !Array.isArray(state.tasks)) {
    fail("LOCAL_STATE_MISMATCH", "The Stage task is no longer current.");
  }
  const task = state.tasks.find(
    (candidate) => Array.isArray(candidate) && candidate[0] === request.task,
  );
  if (
    !Array.isArray(task) ||
    task.length !== 4 ||
    task[1] !== request.area ||
    !["ready", "overridden", "staged"].includes(String(task[3]))
  ) {
    fail("LOCAL_STATE_MISMATCH", "The current task is not accepted for Stage.");
  }
  if (Array.isArray(state.stale) && state.stale.includes(request.area)) {
    fail("LOCAL_STATE_MISMATCH", "The bound Snapshot is stale.");
  }
  const cache = isObject(state.cs) ? state.cs[request.area] : undefined;
  if (
    !Array.isArray(cache) ||
    ![5, 6].includes(cache.length) ||
    String(cache[0]).toLowerCase() !== request.target.change_set_id.toLowerCase() ||
    cache[1] !== request.target.starting_revision ||
    cache[2] !== "active" ||
    cache[3] !== request.task
  ) {
    fail("LOCAL_STATE_MISMATCH", "The cached server draft no longer matches this Stage request.");
  }
  const cacheDigestMatches = cache[4] === request.accepted_digest;
  if (
    (!request.failed_retry && !cacheDigestMatches) ||
    (request.failed_retry && (cacheDigestMatches || cache[5] !== "validation_failed"))
  ) {
    fail("LOCAL_STATE_MISMATCH", "The failed-draft recovery binding is invalid.");
  }
  const acceptance = await readRegularJson(
    join(session, "tasks", `${request.task}.accept.json`),
    "LOCAL_STATE_MISMATCH",
    "The task acceptance is invalid.",
  );
  const acceptedMode = task[3] === "ready" ? "valid" : task[3] === "overridden" ? "override" : null;
  if (
    !Array.isArray(acceptance) ||
    acceptance[0] !== request.accepted_digest ||
    !["valid", "override"].includes(String(acceptance[1])) ||
    (acceptedMode !== null && acceptance[1] !== acceptedMode)
  ) {
    fail("LOCAL_STATE_MISMATCH", "The task acceptance no longer matches this Stage request.");
  }
  const snapshotIndex = acceptance[1] === "override" ? 3 : 2;
  if (
    acceptance[snapshotIndex] !== request.snapshot.snapshot_id ||
    (request.area === "model" && acceptance[snapshotIndex + 1] !== request.target.model_revision)
  ) {
    fail("LOCAL_STATE_MISMATCH", "The task acceptance is bound to a different Snapshot.");
  }
  if (
    request.area === "model" &&
    (!Array.isArray(state.model) ||
      state.model[0] !== request.target.model_id ||
      state.model[1] !== request.target.model_name)
  ) {
    fail("LOCAL_STATE_MISMATCH", "The session is bound to a different Model.");
  }
}

async function verifySnapshotBinding(request: StageRequest, session: string): Promise<void> {
  const areaDirectory = join(session, request.area);
  const areaStat = await lstat(areaDirectory).catch(() =>
    fail("SNAPSHOT_MISMATCH", "The bound Snapshot directory was not found."),
  );
  if (!areaStat.isDirectory() || areaStat.isSymbolicLink()) {
    fail("SNAPSHOT_MISMATCH", "The bound Snapshot directory is invalid.");
  }
  const candidates: string[] = [];
  const inspectCandidate = async (directory: string): Promise<void> => {
    const manifestPath = join(directory, "manifest.json");
    const catalogPath = join(directory, "catalog.json");
    const stats = await Promise.all([
      lstat(manifestPath).catch(() => null),
      lstat(catalogPath).catch(() => null),
    ]);
    if (stats.every((stat) => stat?.isFile() && !stat.isSymbolicLink())) {
      candidates.push(directory);
    } else if (stats.some((stat) => stat !== null)) {
      fail("SNAPSHOT_MISMATCH", "The bound Snapshot contract is incomplete or unsafe.");
    }
  };
  await inspectCandidate(areaDirectory);
  for (const entry of await readdir(areaDirectory, { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.isSymbolicLink()) {
      await inspectCandidate(join(areaDirectory, entry.name));
    }
  }
  if (candidates.length !== 1) {
    fail("SNAPSHOT_MISMATCH", "Expected exactly one bound Snapshot for the Stage request.");
  }
  const manifestBytes = await readFile(join(candidates[0] as string, "manifest.json"));
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
  const catalogBytes = await readFile(join(candidates[0] as string, "catalog.json"));
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
        normalizedTenantCode(request.target.tenant_code) ||
      normalizedTenantCode(request.target.tenant_code) !==
        normalizedTenantCode(basename(dirname(session)))
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

function normalizedKeyValue(area: Area, field: string, value: unknown): unknown {
  if (typeof value !== "string") return value;
  if (area === "model") return unicodeCasefold(value.replace(/^ +| +$/g, ""));
  return /(_code|_name|_schema)$/.test(field)
    ? unicodeLower(value.replace(/^ +| +$/g, ""))
    : value;
}

function normalizedTenantCode(value: unknown): unknown {
  return normalizedKeyValue("metadata", "tenant_code", value);
}

function recordKey(area: Area, dataset: StageRequestDataset, record: JsonRecord): string {
  return stableStringify(
    dataset.canonical_key.map((field) => {
      if (!Object.hasOwn(record, field)) {
        fail("LOCAL_CHANGE_SET_INVALID", `${dataset.dataset} has an invalid canonical key.`);
      }
      return normalizedKeyValue(area, field, record[field]);
    }),
  );
}

async function readLocalDatasets(
  request: StageRequest,
  changeSetDirectory: string,
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
      !isAbsolute(definition.payload_file) ||
      typeof definition.sha256 !== "string" ||
      !SHA256.test(definition.sha256) ||
      result.has(definition.dataset) ||
      definition.dataset.localeCompare(previousDataset) <= 0
    ) {
      fail("MANIFEST_INVALID", "Stage request contains an invalid dataset descriptor.");
    }
    previousDataset = definition.dataset;
    const payloadPath = await realpath(definition.payload_file).catch(() =>
      fail("PAYLOAD_INVALID", `${definition.dataset} payload was not found.`),
    );
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

async function resolveMetadataTenant(mcp: McpToolClient, tenantCode: string): Promise<number> {
  let cursor: string | null = null;
  const matchingTenantIds = new Set<number>();
  const seenTenantIds = new Set<number>();
  const seenCursors = new Set<string>();
  for (let page = 0; page < 100; page += 1) {
    const response = requireObject(
      await mcp.callTool("list_tenants", {
        page_size: 100,
        ...(cursor === null ? {} : { cursor }),
      }),
      "MCP_RESPONSE_INVALID",
    );
    if (
      response.schema_version !== "1.0" ||
      !Array.isArray(response.tenants) ||
      response.tenants.length > 200 ||
      (response.next_cursor !== null &&
        (typeof response.next_cursor !== "string" ||
          !response.next_cursor ||
          response.next_cursor.length > 2_048))
    ) {
      fail("MCP_RESPONSE_INVALID", "Tenant lookup response is invalid.");
    }
    for (const tenant of response.tenants) {
      if (
        !isObject(tenant) ||
        typeof tenant.tenant_id !== "number" ||
        !Number.isSafeInteger(tenant.tenant_id) ||
        tenant.tenant_id < 1 ||
        typeof tenant.tenant_code !== "string" ||
        !tenant.tenant_code ||
        tenant.tenant_code.length > 100 ||
        seenTenantIds.has(tenant.tenant_id)
      ) {
        fail("MCP_RESPONSE_INVALID", "Tenant lookup response is invalid.");
      }
      seenTenantIds.add(tenant.tenant_id);
      if (normalizedTenantCode(tenant.tenant_code) === normalizedTenantCode(tenantCode)) {
        matchingTenantIds.add(tenant.tenant_id);
      }
    }
    cursor = response.next_cursor as string | null;
    if (cursor === null) break;
    if (seenCursors.has(cursor)) {
      fail("MCP_RESPONSE_INVALID", "Tenant lookup cursor repeated.");
    }
    seenCursors.add(cursor);
    if (page === 99) {
      fail("MCP_RESPONSE_INVALID", "Tenant lookup exceeded its page limit.");
    }
  }
  if (matchingTenantIds.size === 1) {
    return [...matchingTenantIds][0] as number;
  }
  fail("TARGET_MISMATCH", "The Stage request Tenant is not uniquely accessible.");
}

function reconcileDataset(
  area: Area,
  definition: StageRequestDataset,
  local: JsonRecord[],
  server: JsonRecord[],
  failedRetry: boolean,
): JsonRecord[] {
  if (failedRetry) return local;
  if (local.length === 0 && server.length > 0) {
    fail("RECONCILIATION_CONFLICT", `${definition.dataset} requires explicit clear resolution.`);
  }
  const merged = new Map<string, JsonRecord>();
  for (const record of server) {
    const key = recordKey(area, definition, record);
    if (merged.has(key)) {
      fail("MCP_RESPONSE_INVALID", `${definition.dataset} server records contain a duplicate key.`);
    }
    merged.set(key, record);
  }
  for (const record of local) {
    const key = recordKey(area, definition, record);
    const existing = merged.get(key);
    if (existing !== undefined && stableStringify(existing) !== stableStringify(record)) {
      fail("RECONCILIATION_CONFLICT", `${definition.dataset} has a conflicting canonical key.`);
    }
    merged.set(key, record);
  }
  return [...merged.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, record]) => record);
}

function recordChunks(records: JsonRecord[], maximumBytes: number): JsonRecord[][] | null {
  const chunks: JsonRecord[][] = [];
  let current: JsonRecord[] = [];
  let currentBytes = 2; // JSON array brackets.
  for (const record of records) {
    const recordBytes = Buffer.byteLength(stableStringify(record), "utf8");
    if (recordBytes + 2 > maximumBytes) return null;
    if (
      current.length > 0 &&
      (current.length === MAX_STAGE_CHUNK_RECORDS || currentBytes + recordBytes + 1 > maximumBytes)
    ) {
      chunks.push(current);
      current = [];
      currentBytes = 2;
    }
    currentBytes += recordBytes + (current.length > 0 ? 1 : 0);
    current.push(record);
  }
  if (current.length > 0) chunks.push(current);
  return chunks;
}

function transportSafeRecordChunks(
  records: JsonRecord[],
  hardMaximumBytes: number,
): JsonRecord[][] | null {
  const preferred = recordChunks(records, DIRECT_STAGE_MAX_BYTES);
  if (preferred !== null && preferred.length <= MAX_STAGE_CHUNKS) return preferred;
  let lower = DIRECT_STAGE_MAX_BYTES + 1;
  let upper = hardMaximumBytes;
  let best: JsonRecord[][] | null = null;
  while (lower <= upper) {
    const candidateMaximum = Math.floor((lower + upper) / 2);
    const candidate = recordChunks(records, candidateMaximum);
    if (candidate !== null && candidate.length <= MAX_STAGE_CHUNKS) {
      best = candidate;
      upper = candidateMaximum - 1;
    } else {
      lower = candidateMaximum + 1;
    }
  }
  return best;
}

function stageTarget(request: StageRequest, scopeId: number): Record<string, unknown> {
  return request.area === "metadata"
    ? {
        tenant_id: scopeId,
        metadata_change_set_id: request.target.change_set_id,
      }
    : {
        model_id: scopeId,
        model_change_set_id: request.target.change_set_id,
    };
}

function responseMatchesTarget(
  request: StageRequest,
  target: Record<string, unknown>,
  response: Record<string, unknown>,
): boolean {
  const scopeKey = request.area === "metadata" ? "tenant_id" : "model_id";
  const changeSetKey =
    request.area === "metadata" ? "metadata_change_set_id" : "model_change_set_id";
  return (
    response[scopeKey] === target[scopeKey] &&
    typeof response[changeSetKey] === "string" &&
    typeof target[changeSetKey] === "string" &&
    response[changeSetKey].toLowerCase() === target[changeSetKey].toLowerCase()
  );
}

function verifyDirectStageResponse(
  request: StageRequest,
  target: Record<string, unknown>,
  expectedRevision: number,
  changes: Array<{ dataset: string; records: JsonRecord[] }>,
  response: Record<string, unknown>,
): void {
  if (
    response.schema_version !== "1.0" ||
    !responseMatchesTarget(request, target, response) ||
    response.staged !== true ||
    response.status !== "active" ||
    response.draft_revision !== expectedRevision + 1 ||
    !Array.isArray(response.datasets) ||
    response.datasets.length !== changes.length
  ) {
    fail("MCP_RESPONSE_INVALID", "Direct Stage response does not match its request.");
  }
  const expected = new Map(changes.map((change) => [change.dataset, change.records.length]));
  const received = new Set<string>();
  for (const dataset of response.datasets) {
    if (
      !isObject(dataset) ||
      typeof dataset.dataset !== "string" ||
      received.has(dataset.dataset) ||
      !expected.has(dataset.dataset) ||
      dataset.record_count !== expected.get(dataset.dataset)
    ) {
      fail("MCP_RESPONSE_INVALID", "Direct Stage response does not match its datasets.");
    }
    received.add(dataset.dataset);
  }
}

function sameUuid(value: unknown, expected: string): boolean {
  return typeof value === "string" && value.toLowerCase() === expected.toLowerCase();
}

function verifyBeginStageResponse(
  request: StageRequest,
  target: Record<string, unknown>,
  revision: number,
  change: { dataset: string; records: JsonRecord[] },
  chunkCount: number,
  fragmentMode: boolean,
  payloadBytes: number,
  response: Record<string, unknown>,
): { stageBatchId: string; receivedChunkCount: number } {
  if (
    response.schema_version !== "1.0" ||
    !responseMatchesTarget(request, target, response) ||
    typeof response.stage_batch_id !== "string" ||
    !UUID.test(response.stage_batch_id) ||
    response.dataset !== change.dataset ||
    typeof response.created !== "boolean" ||
    response.total_record_count !== change.records.length ||
    response.total_chunk_count !== chunkCount ||
    !Number.isSafeInteger(response.received_chunk_count) ||
    Number(response.received_chunk_count) < 0 ||
    Number(response.received_chunk_count) > chunkCount ||
    (response.created === true && response.received_chunk_count !== 0) ||
    response.expected_draft_revision !== revision ||
    (request.area === "model" &&
      (response.payload_mode !== (fragmentMode ? "json_fragments" : "records") ||
        response.total_payload_bytes !== (fragmentMode ? payloadBytes : null)))
  ) {
    fail("MCP_RESPONSE_INVALID", "Begin Stage response does not match its request.");
  }
  return {
    stageBatchId: response.stage_batch_id as string,
    receivedChunkCount: Number(response.received_chunk_count),
  };
}

function verifyPutStageResponse(
  request: StageRequest,
  target: Record<string, unknown>,
  stageBatchId: string,
  change: { dataset: string; records: JsonRecord[] },
  chunkIndex: number,
  chunkCount: number,
  recordCount: number,
  fragmentByteCount: number | null,
  response: Record<string, unknown>,
): void {
  const fragmentMode = fragmentByteCount !== null;
  if (
    response.schema_version !== "1.0" ||
    !responseMatchesTarget(request, target, response) ||
    !sameUuid(response.stage_batch_id, stageBatchId) ||
    response.dataset !== change.dataset ||
    response.accepted !== true ||
    typeof response.duplicate !== "boolean" ||
    response.chunk_index !== chunkIndex ||
    response.record_count !== recordCount ||
    response.received_chunk_count !== chunkIndex ||
    response.total_chunk_count !== chunkCount ||
    (request.area === "model" &&
      (response.payload_mode !== (fragmentMode ? "json_fragments" : "records") ||
        response.payload_byte_count !== fragmentByteCount))
  ) {
    fail("MCP_RESPONSE_INVALID", "Put Stage response does not match its request.");
  }
}

function verifyCommitStageResponse(
  request: StageRequest,
  target: Record<string, unknown>,
  stageBatchId: string,
  change: { dataset: string; records: JsonRecord[] },
  revision: number,
  response: Record<string, unknown>,
): void {
  if (
    response.schema_version !== "1.0" ||
    !responseMatchesTarget(request, target, response) ||
    !sameUuid(response.stage_batch_id, stageBatchId) ||
    response.dataset !== change.dataset ||
    response.committed !== true ||
    typeof response.replayed !== "boolean" ||
    response.record_count !== change.records.length ||
    response.draft_revision !== revision + 1 ||
    response.status !== "active"
  ) {
    fail("MCP_RESPONSE_INVALID", "Commit Stage response does not match its request.");
  }
}

function verifyChangeSetReadResponse(
  request: StageRequest,
  target: Record<string, unknown>,
  expectedRevision: number,
  dataset: string | null,
  response: Record<string, unknown>,
): JsonRecord[] | null {
  if (
    response.schema_version !== "1.0" ||
    !responseMatchesTarget(request, target, response) ||
    !Array.isArray(response.dataset_counts) ||
    response.dataset !== dataset ||
    (dataset === null
      ? response.records !== null
      : !Array.isArray(response.records) ||
        response.records.some((record) => !isObject(record)))
  ) {
    fail("MCP_RESPONSE_INVALID", "Change Set read response does not match its request.");
  }
  if (response.status !== "active" || response.draft_revision !== expectedRevision) {
    fail("REVISION_CONFLICT", "Server Change Set status or revision changed before Stage.");
  }
  return dataset === null ? null : (response.records as JsonRecord[]);
}

function verifyStageFingerprint(
  request: StageRequest,
  scopeId: number,
  resultingRevision: number,
  changes: Array<{ dataset: string; records: JsonRecord[] }>,
  value: unknown,
): string {
  const fingerprint = requireObject(value, "MCP_RESPONSE_INVALID");
  if (
    fingerprint.schema_version !== "1.0" ||
    fingerprint.fingerprint_version !== "1.0" ||
    fingerprint.area !== request.area ||
    fingerprint.status !== "active" ||
    fingerprint.draft_revision !== resultingRevision ||
    typeof fingerprint.fingerprint !== "string" ||
    !SHA256.test(fingerprint.fingerprint) ||
    fingerprint.dataset_count !== ALLOWED_DATASETS[request.area].size ||
    !Number.isSafeInteger(fingerprint.record_count) ||
    Number(fingerprint.record_count) < 0 ||
    !Array.isArray(fingerprint.datasets) ||
    fingerprint.datasets.length !== ALLOWED_DATASETS[request.area].size ||
    (request.area === "metadata" &&
      (fingerprint.tenant_id !== scopeId ||
        String(fingerprint.metadata_change_set_id).toLowerCase() !==
          request.target.change_set_id.toLowerCase())) ||
    (request.area === "model" &&
      (fingerprint.model_id !== scopeId ||
        String(fingerprint.model_change_set_id).toLowerCase() !==
          request.target.change_set_id.toLowerCase()))
  ) {
    fail("FINGERPRINT_MISMATCH", "Server Stage fingerprint response is invalid.");
  }
  const datasets: Array<{ dataset: string; record_count: number; sha256: string }> = [];
  const names = new Set<string>();
  const expectedOrder = [...ALLOWED_DATASETS[request.area]];
  if (request.area === "model") expectedOrder.sort();
  let recordCount = 0;
  for (const [index, item] of fingerprint.datasets.entries()) {
    if (
      !isObject(item) ||
      !hasExactKeys(item, ["dataset", "record_count", "sha256"]) ||
      typeof item.dataset !== "string" ||
      !ALLOWED_DATASETS[request.area].has(item.dataset) ||
      item.dataset !== expectedOrder[index] ||
      names.has(item.dataset) ||
      !Number.isSafeInteger(item.record_count) ||
      Number(item.record_count) < 0 ||
      typeof item.sha256 !== "string" ||
      !SHA256.test(item.sha256)
    ) {
      fail("FINGERPRINT_MISMATCH", "Server Stage dataset fingerprint is invalid.");
    }
    names.add(item.dataset);
    recordCount += Number(item.record_count);
    datasets.push({
      dataset: item.dataset,
      record_count: Number(item.record_count),
      sha256: item.sha256,
    });
  }
  if (recordCount !== fingerprint.record_count) {
    fail("FINGERPRINT_MISMATCH", "Server Stage fingerprint counts are inconsistent.");
  }
  const aggregate = createHash("sha256")
    .update(
      stableStringify({
        area: request.area,
        datasets,
        fingerprint_version: "1.0",
      }),
      "utf8",
    )
    .digest("hex");
  if (aggregate !== fingerprint.fingerprint) {
    fail("FINGERPRINT_MISMATCH", "Server Stage fingerprint digest is inconsistent.");
  }
  const byDataset = new Map(datasets.map((item) => [item.dataset, item] as const));
  for (const change of changes) {
    if (byDataset.get(change.dataset)?.record_count !== change.records.length) {
      fail("FINGERPRINT_MISMATCH", "Server Stage fingerprint has an unexpected record count.");
    }
  }
  return fingerprint.fingerprint;
}

async function executeStage(
  request: StageRequest,
  mcp: McpToolClient,
  target: Record<string, unknown>,
  changes: Array<{ dataset: string; records: JsonRecord[] }>,
  isCancellationRequested?: () => boolean,
  onWriteStart?: () => void,
): Promise<number> {
  let writeStarted = false;
  const beginWrite = (): void => {
    if (writeStarted) return;
    if (isCancellationRequested?.()) {
      fail("CANCELLED", "Stage was cancelled before writing.");
    }
    onWriteStart?.();
    writeStarted = true;
  };
  const directNames = new Set(changes.map((change) => change.dataset));
  const directChanges = () => changes.filter((change) => directNames.has(change.dataset));
  while (Buffer.byteLength(stableStringify(directChanges()), "utf8") > DIRECT_STAGE_MAX_BYTES) {
    const removable = changes
      .filter((change) => directNames.has(change.dataset) && change.records.length > 0)
      .sort(
        (left, right) =>
          Buffer.byteLength(stableStringify(right.records), "utf8") -
            Buffer.byteLength(stableStringify(left.records), "utf8") ||
          left.dataset.localeCompare(right.dataset),
      );
    const selected = removable[0];
    if (selected === undefined) {
      fail("PAYLOAD_LIMIT", "Direct Stage envelope exceeds its safe byte limit.");
    }
    directNames.delete(selected.dataset);
  }

  // Validate every batch before the first write, including mixed direct/batch requests.
  const batches = changes.filter((item) => !directNames.has(item.dataset)).map((change) => {
    const maximumRecords = request.area === "metadata" ? 50_000 : 20_000;
    if (change.records.length < 1 || change.records.length > maximumRecords) {
      fail("PAYLOAD_LIMIT", `${change.dataset} exceeds the Stage record limit.`);
    }
    const recordChunkSet = transportSafeRecordChunks(
      change.records,
      request.area === "metadata"
        ? METADATA_STAGE_CHUNK_MAX_BYTES
        : MODEL_STAGE_CHUNK_MAX_BYTES,
    );
    const fragmentMode =
      recordChunkSet === null && request.area === "model" && change.dataset === "generated_code";
    if (recordChunkSet === null && !fragmentMode) {
      fail("PAYLOAD_LIMIT", `${change.dataset} cannot fit the Stage chunk limits.`);
    }
    const canonicalPayload = fragmentMode
      ? Buffer.from(stableStringify(change.records), "utf8")
      : Buffer.alloc(0);
    const fragmentBytes = fragmentMode
      ? Math.max(DIRECT_STAGE_MAX_BYTES, Math.ceil(canonicalPayload.length / MAX_STAGE_CHUNKS))
      : 0;
    if (fragmentBytes > MODEL_STAGE_CHUNK_MAX_BYTES) {
      fail("PAYLOAD_LIMIT", "generated_code exceeds the bounded fragment limit.");
    }
    const fragments: Buffer[] = [];
    if (fragmentMode) {
      for (let offset = 0; offset < canonicalPayload.length; offset += fragmentBytes) {
        fragments.push(canonicalPayload.subarray(offset, offset + fragmentBytes));
      }
    }
    const chunks = recordChunkSet ?? fragments;
    const chunkHashes = fragmentMode
      ? fragments.map((fragment) => createHash("sha256").update(fragment).digest("hex"))
      : (recordChunkSet as JsonRecord[][]).map(canonicalRecordsSha256);
    const batchSha256 = createHash("sha256")
      .update(chunkHashes.join(""), "ascii")
      .digest("hex");
    return { change, chunks, chunkHashes, fragmentMode, batchSha256, payloadBytes: canonicalPayload.length };
  });

  let revision = request.target.starting_revision;
  const direct = directChanges();
  if (direct.length > 0) {
    beginWrite();
    const response = requireObject(
      await mcp.callTool(`stage_${request.area}_change_set`, {
        ...target,
        expected_draft_revision: revision,
        changes: direct,
      }),
      "MCP_RESPONSE_INVALID",
    );
    verifyDirectStageResponse(request, target, revision, direct, response);
    revision += 1;
  }

  for (const { change, chunks, chunkHashes, fragmentMode, batchSha256, payloadBytes } of batches) {
    beginWrite();
    const begun = requireObject(
      await mcp.callTool(`begin_${request.area}_stage_batch`, {
        ...target,
        expected_draft_revision: revision,
        dataset: change.dataset,
        total_record_count: change.records.length,
        total_chunk_count: chunks.length,
        batch_sha256: batchSha256,
        ...(request.area === "model"
          ? {
              payload_mode: fragmentMode ? "json_fragments" : "records",
              ...(fragmentMode ? { total_payload_bytes: payloadBytes } : {}),
            }
          : {}),
      }),
      "MCP_RESPONSE_INVALID",
    );
    const { stageBatchId, receivedChunkCount } = verifyBeginStageResponse(
      request,
      target,
      revision,
      change,
      chunks.length,
      fragmentMode,
      payloadBytes,
      begun,
    );
    for (const [index, chunk] of chunks.entries()) {
      if (index + 1 <= receivedChunkCount) continue;
      const put = requireObject(
        await mcp.callTool(`put_${request.area}_stage_chunk`, {
          ...target,
          stage_batch_id: stageBatchId,
          dataset: change.dataset,
          chunk_index: index + 1,
          chunk_sha256: chunkHashes[index],
          ...(fragmentMode
            ? {
                payload_mode: "json_fragments",
                payload_fragment_base64: (chunk as Buffer).toString("base64"),
              }
            : {
                records: chunk,
                ...(request.area === "model" ? { payload_mode: "records" } : {}),
              }),
        }),
        "MCP_RESPONSE_INVALID",
      );
      verifyPutStageResponse(
        request,
        target,
        stageBatchId,
        change,
        index + 1,
        chunks.length,
        fragmentMode ? 0 : (chunk as JsonRecord[]).length,
        fragmentMode ? (chunk as Buffer).length : null,
        put,
      );
    }
    const committed = requireObject(
      await mcp.callTool(`commit_${request.area}_stage_batch`, {
        ...target,
        stage_batch_id: stageBatchId,
        expected_draft_revision: revision,
      }),
      "MCP_RESPONSE_INVALID",
    );
    verifyCommitStageResponse(request, target, stageBatchId, change, revision, committed);
    revision += 1;
  }
  return revision;
}

export async function stageApprovedManifest(
  input: StageApprovedManifestInput,
  dependencies: StageRunnerDependencies,
): Promise<StageReceipt> {
  const { request, changeSetDirectory } = await readRequest(
    input,
    dependencies.workspaceRoots,
  );
  const local = await readLocalDatasets(request, changeSetDirectory);
  let scopeId: number;
  if (request.area === "metadata") {
    if (typeof request.target.tenant_code !== "string" || !request.target.tenant_code.trim()) {
      fail("MANIFEST_INVALID", "Metadata Stage request has no Tenant Code.");
    }
    scopeId = await resolveMetadataTenant(dependencies.mcp, request.target.tenant_code);
  } else {
    if (
      typeof request.target.model_id !== "number" ||
      !Number.isSafeInteger(request.target.model_id) ||
      request.target.model_id < 1
    ) {
      fail("MANIFEST_INVALID", "Model Stage request has no valid Model ID.");
    }
    scopeId = request.target.model_id;
  }
  const target = stageTarget(request, scopeId);
  const summary = requireObject(
    await dependencies.mcp.callTool(`get_${request.area}_change_set`, target),
    "MCP_RESPONSE_INVALID",
  );
  verifyChangeSetReadResponse(
    request,
    target,
    request.target.starting_revision,
    null,
    summary,
  );
  const changes: Array<{ dataset: string; records: JsonRecord[] }> = [];
  for (const { definition, records } of local.values()) {
    const response = requireObject(
      await dependencies.mcp.callTool(`get_${request.area}_change_set`, {
        ...target,
        dataset: definition.dataset,
      }),
      "MCP_RESPONSE_INVALID",
    );
    const serverRecords = verifyChangeSetReadResponse(
      request,
      target,
      request.target.starting_revision,
      definition.dataset,
      response,
    );
    if (serverRecords === null) {
      fail("MCP_RESPONSE_INVALID", "Change Set dataset response omitted its records.");
    }
    changes.push({
      dataset: definition.dataset,
      records: reconcileDataset(
        request.area,
        definition,
        records,
        serverRecords,
        request.failed_retry,
      ),
    });
  }
  // Server reads/sign-in can take time; approval must still hold at the first write.
  const refreshed = await readRequest(input, dependencies.workspaceRoots);
  if (stableStringify(refreshed.request) !== stableStringify(request)) {
    fail("MANIFEST_CHANGED", "Stage request changed while preparing to write.");
  }
  const resultingRevision = await executeStage(
    request,
    dependencies.mcp,
    target,
    changes,
    dependencies.isCancellationRequested,
    dependencies.onWriteStart,
  );
  const stageFingerprint = verifyStageFingerprint(
    request,
    scopeId,
    resultingRevision,
    changes,
    await dependencies.mcp.callTool(`get_${request.area}_change_set_fingerprint`, target),
  );
  return {
    schemaVersion: "1.0",
    status: "staged",
    area: request.area,
    changeSetId: request.target.change_set_id,
    startingRevision: request.target.starting_revision,
    resultingRevision,
    acceptedDigest: request.accepted_digest,
    stageFingerprint,
    fingerprintVerified: true,
    datasets: changes.map((change) => ({
      dataset: change.dataset,
      recordCount: change.records.length,
    })),
  };
}
