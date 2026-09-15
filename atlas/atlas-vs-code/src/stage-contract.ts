import { createHash } from "node:crypto";
import { unicodeCasefold, unicodeLower } from "./unicode.js";
// @ts-expect-error Shared Workbench serialization intentionally has no declaration file.
import workbenchCore from "../../atlas-plugin/workbench/core.js";
export const stableStringify = workbenchCore.stableStringify as (value: unknown) => string;
export const SHA256 = /^[0-9a-f]{64}$/;
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export const MAX_MANIFEST_BYTES = 128 * 1024;
export const MAX_PATH_CHARACTERS = 4_096;
export const DIRECT_STAGE_MAX_BYTES = 64 * 1024;
export const MAX_STAGE_CHUNKS = 64;
export const MAX_STAGE_CHUNK_RECORDS = 5_000;
export const METADATA_STAGE_CHUNK_MAX_BYTES = 450 * 1024;
export const MODEL_STAGE_CHUNK_MAX_BYTES = 1024 * 1024;
export const MAX_LOCAL_PAYLOAD_BYTES: Record<Area, number> = {
  metadata: MAX_STAGE_CHUNKS * METADATA_STAGE_CHUNK_MAX_BYTES + 1024,
  model: MAX_STAGE_CHUNKS * MODEL_STAGE_CHUNK_MAX_BYTES + 1024,
};
export const ALLOWED_DATASETS: Record<Area, ReadonlySet<string>> = {
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

export type Area = "metadata" | "model";
export type JsonRecord = Record<string, unknown>;

export interface StageRequestDataset {
  dataset: string;
  canonical_key: string[];
  record_count: number;
  payload_file: string;
  sha256: string;
}

export interface StageRequest {
  schema_version: "1.0";
  kind: "atlas-stage-request";
  area: Area;
  task: string;
  operation: { id: string; path: string };
  owner: { id: number; code: string; root: string };
  backend: BackendIdentity;
  accepted_digest: string;
  failed_retry: boolean;
  snapshot: {
    manifest_path: string;
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
  recoverOnly?: boolean;
}

export interface BackendIdentity {
  profile: "production" | "local" | "azureLocalTest";
  endpoint_sha256: string;
}

export interface StageRunnerDependencies {
  mcp: McpToolClient;
  workspaceRoots: string[];
  backend: BackendIdentity;
  isCancellationRequested?: () => boolean;
  onWriteStart?: () => void;
}

export interface StageReceipt {
  schemaVersion: "1.0";
  status: "staged";
  taskId: string;
  operationId: string;
  ownerTenantId: number;
  ownerRoot: string;
  backend: BackendIdentity;
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

export function fail(code: string, message: string): never {
  throw new StageRunnerError(code, message);
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const required = [...expected].sort();
  return actual.length === required.length && actual.every((key, index) => key === required[index]);
}

export function canonicalRecordsSha256(records: JsonRecord[]): string {
  return createHash("sha256").update(stableStringify(records), "utf8").digest("hex");
}

export function normalizedKeyValue(area: Area, field: string, value: unknown): unknown {
  if (typeof value !== "string") return value;
  if (area === "model") return unicodeCasefold(value.replace(/^ +| +$/g, ""));
  return /(_code|_name|_schema)$/.test(field)
    ? unicodeLower(value.replace(/^ +| +$/g, ""))
    : value;
}

export function normalizedTenantCode(value: unknown): unknown {
  return normalizedKeyValue("metadata", "tenant_code", value);
}

export function recordKey(area: Area, dataset: StageRequestDataset, record: JsonRecord): string {
  return stableStringify(
    dataset.canonical_key.map((field) => {
      if (!Object.hasOwn(record, field)) {
        fail("LOCAL_CHANGE_SET_INVALID", `${dataset.dataset} has an invalid canonical key.`);
      }
      return normalizedKeyValue(area, field, record[field]);
    }),
  );
}


export function requireObject(value: unknown, code: string): Record<string, unknown> {
  if (!isObject(value)) fail(code, "Stage Runner received an unexpected MCP response.");
  return value;
}
