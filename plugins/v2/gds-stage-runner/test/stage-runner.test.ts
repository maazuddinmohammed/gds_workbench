import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, rename, symlink, truncate, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, expect, test } from "vitest";

import {
  canonicalRecordsSha256,
  stageApprovedManifest,
  StageRunnerError,
  workspaceDigest,
  type McpToolClient,
} from "../src/stage-runner.js";

const CHANGE_SET_ID = "30000000-0000-4000-8000-000000000050";

// Expected digests come from the server's canonical_records_sha256 after JSON decoding.
test.each([
  [[{ value: 0.000001 }], "52423a9af622ea11ea3356dcf5e3b8954bff3797e92ee37ae78fc7da3974e68d"],
  [[{ value: 0.00001 }], "d46acfb78daa87265af33ed356292c12a7ab73593e754956ba4c0e6f41ba8589"],
  [[{ value: 0.0001 }], "78acce6cb4150d114dbcf9a0b647331536b183a386364f6a3919b760f5c2b185"],
  [[{ value: 1e-7 }], "7996b584fc4eb4a0222e35cc4c752fb999adcd53ea5725150461ceb1da5b1bb6"],
  [[{ value: 1.234567e-5 }], "4e4416939731a96642d5f7bd2f658d0383a0e700902171351ead402ec3d71fd1"],
  [[{ value: 1e21 }], "92544edd51ed35f069b10ecd00e61757e80a0dd756abffd15dbcdd7d4b929be2"],
  [[{ "\ue000": 1, "😀": 2 }], "d217a29d93fef13515f254c0c7932dcb38d341cd13f41118a44d78400a8ee939"],
] as const)("matches the Python server's record digest for %j", (records, expected) => {
  expect(canonicalRecordsSha256([...records])).toBe(expected);
});

const SNAPSHOT_IDS = {
  metadata: "10000000-0000-4000-8000-000000000001",
  model: "20000000-0000-4000-8000-000000000001",
} as const;
const METADATA_DATASETS = [
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
] as const;
const MODEL_DATASETS = [
  "analysis_result",
  "conceptual_object",
  "conceptual_relationship",
  "dimensional_attribute",
  "dimensional_entity",
  "dimensional_relationship",
  "dimensional_submodel",
  "generated_code",
  "generated_code_source_system",
  "logical_attribute",
  "logical_entity",
  "logical_relationship",
  "logical_submodel",
  "mapping_attribute",
  "mapping_dependency",
  "mapping_object",
  "model_attribute_binding",
  "model_details",
  "model_input_scope",
  "model_object_binding",
  "modeling_assertion_document",
  "modeling_assertion_record",
  "profiling_profile",
  "validation_check",
  "validation_group",
] as const;

function fingerprintResponse(
  area: "metadata" | "model",
  revision: number,
  recordsByDataset: Record<string, Array<Record<string, unknown>>>,
  hashOverrides: Record<string, string> = {},
) {
  const names = area === "metadata" ? METADATA_DATASETS : MODEL_DATASETS;
  const datasets = names.map((dataset) => {
    const records = recordsByDataset[dataset] ?? [];
    return {
      dataset,
      record_count: records.length,
      sha256: hashOverrides[dataset] ?? canonicalRecordsSha256(records),
    };
  });
  const fingerprintDocument = {
    area,
    datasets,
    fingerprint_version: "1.0",
  };
  return {
    schema_version: "1.0",
    fingerprint_version: "1.0",
    area,
    ...(area === "metadata"
      ? { tenant_id: 17, metadata_change_set_id: CHANGE_SET_ID }
      : { model_id: 42, model_change_set_id: CHANGE_SET_ID }),
    status: "active",
    draft_revision: revision,
    dataset_count: datasets.length,
    record_count: datasets.reduce((total, item) => total + item.record_count, 0),
    datasets,
    fingerprint: createHash("sha256")
      .update(JSON.stringify(fingerprintDocument))
      .digest("hex"),
    expires_at: "2026-09-05T00:00:00Z",
  };
}

function directStageResponse(
  area: "metadata" | "model",
  revision: number,
  recordsByDataset: Record<string, Array<Record<string, unknown>>>,
) {
  return {
    schema_version: "1.0",
    ...(area === "metadata"
      ? { tenant_id: 17, metadata_change_set_id: CHANGE_SET_ID }
      : { model_id: 42, model_change_set_id: CHANGE_SET_ID }),
    staged: true,
    datasets: Object.entries(recordsByDataset).map(([dataset, records]) => ({
      dataset,
      record_count: records.length,
    })),
    draft_revision: revision,
    status: "active",
    expires_at: "2026-09-05T00:00:00Z",
  };
}

function batchTarget(area: "metadata" | "model") {
  return area === "metadata"
    ? { tenant_id: 17, metadata_change_set_id: CHANGE_SET_ID }
    : { model_id: 42, model_change_set_id: CHANGE_SET_ID };
}

function beginStageResponse(
  area: "metadata" | "model",
  input: Record<string, unknown>,
  stageBatchId: string,
) {
  return {
    schema_version: "1.0",
    ...batchTarget(area),
    stage_batch_id: stageBatchId,
    dataset: input.dataset,
    created: true,
    total_record_count: input.total_record_count,
    total_chunk_count: input.total_chunk_count,
    received_chunk_count: 0,
    expected_draft_revision: input.expected_draft_revision,
    expires_at: "2026-09-05T00:00:00Z",
    ...(area === "model"
      ? {
          payload_mode: input.payload_mode,
          total_payload_bytes: input.total_payload_bytes ?? null,
        }
      : {}),
  };
}

function putStageResponse(
  area: "metadata" | "model",
  input: Record<string, unknown>,
  totalChunkCount: number,
) {
  const fragment =
    typeof input.payload_fragment_base64 === "string"
      ? Buffer.from(input.payload_fragment_base64, "base64")
      : null;
  return {
    schema_version: "1.0",
    ...batchTarget(area),
    stage_batch_id: input.stage_batch_id,
    dataset: input.dataset,
    accepted: true,
    duplicate: false,
    chunk_index: input.chunk_index,
    record_count: Array.isArray(input.records) ? input.records.length : 0,
    received_chunk_count: input.chunk_index,
    total_chunk_count: totalChunkCount,
    expires_at: "2026-09-05T00:00:00Z",
    ...(area === "model"
      ? {
          payload_mode: input.payload_mode,
          payload_byte_count: fragment?.length ?? null,
        }
      : {}),
  };
}

function commitStageResponse(
  area: "metadata" | "model",
  input: Record<string, unknown>,
  dataset: string,
  recordCount: number,
  revision: number,
) {
  return {
    schema_version: "1.0",
    ...batchTarget(area),
    stage_batch_id: input.stage_batch_id,
    dataset,
    committed: true,
    replayed: false,
    record_count: recordCount,
    draft_revision: revision,
    status: "active",
    expires_at: "2026-09-05T00:00:00Z",
  };
}

function changeSetResponse(
  area: "metadata" | "model",
  revision: number,
  dataset: unknown,
  records: Array<Record<string, unknown>> = [],
) {
  const selectedDataset = typeof dataset === "string" ? dataset : null;
  return {
    schema_version: "1.0",
    ...batchTarget(area),
    status: "active",
    draft_revision: revision,
    candidate_digest: null,
    validation_outcome: null,
    dataset_counts: [],
    dataset: selectedDataset,
    records: selectedDataset === null ? null : records,
    created_at: "2026-09-04T00:00:00Z",
    last_activity_at: "2026-09-04T00:00:00Z",
    expires_at: "2026-09-05T00:00:00Z",
    validated_at: null,
    applied_at: null,
    terminal_at: null,
  };
}

function tenantListResponse(
  tenants: Array<{ tenant_id: number; tenant_code: string }> = [
    { tenant_id: 17, tenant_code: "DEMO" },
  ],
  nextCursor: string | null = null,
) {
  return {
    schema_version: "1.0",
    tenants: tenants.map((tenant) => ({
      ...tenant,
      tenant_name: tenant.tenant_code,
      tenant_description: null,
      tenant_visibility: "private",
      effective_role: "developer",
    })),
    next_cursor: nextCursor,
  };
}

async function bindSession(
  session: string,
  area: "metadata" | "model",
  acceptedDigest: string,
  dataset: string,
  canonicalKey: string[],
  startingRevision: number,
) {
  const snapshotId = SNAPSHOT_IDS[area];
  const snapshotDirectory = join(session, area);
  const tasksDirectory = join(session, "tasks");
  await mkdir(snapshotDirectory, { recursive: true });
  await mkdir(tasksDirectory, { recursive: true });
  const catalog = {
    snapshot_kind: area,
    ...(area === "model"
      ? { model: { model_id: 42, model_name: "Customer Model", model_revision: 8 } }
      : {}),
    sections: [{ name: "test", datasets: [{ name: dataset, canonical_key: canonicalKey }] }],
  };
  const catalogBytes = `${JSON.stringify(catalog)}\n`;
  await writeFile(join(snapshotDirectory, "catalog.json"), catalogBytes, { mode: 0o600 });
  const catalogSha256 = createHash("sha256").update(catalogBytes).digest("hex");
  const manifest = {
    schema_version: "2.0",
    snapshot_kind: area,
    snapshot_id: snapshotId,
    ...(area === "metadata"
      ? { tenant_code: "DEMO" }
      : { model_id: 42, model_name: "Customer Model", model_revision: 8 }),
    catalog: { path: "catalog.json", sha256: catalogSha256 },
    members: [
      {
        path: "catalog.json",
        size_bytes: Buffer.byteLength(catalogBytes),
        sha256: catalogSha256,
      },
    ],
  };
  const manifestBytes = `${JSON.stringify(manifest)}\n`;
  await writeFile(join(snapshotDirectory, "manifest.json"), manifestBytes, { mode: 0o600 });
  const manifestSha256 = createHash("sha256").update(manifestBytes).digest("hex");
  await writeFile(
    join(session, "session.json"),
    `${JSON.stringify({
      current: "01",
      tasks: [["01", area, "Stage test", "ready"]],
      ...(area === "model" ? { model: [42, "Customer Model"] } : {}),
      cs: {
        [area]: [CHANGE_SET_ID, startingRevision, "active", "01", acceptedDigest],
      },
    })}\n`,
    { mode: 0o600 },
  );
  const acceptance: unknown[] = [acceptedDigest, "valid", snapshotId, area === "model" ? 8 : null];
  if (area === "model") {
    // Transport tests trust a helper report; modeling semantics have their own fixture suite.
    const decisions = JSON.stringify({schema_version: "1.0", entities: [], relationships: []});
    await writeFile(join(tasksDirectory, "01.modeling-decisions.json"), decisions);
    const report = JSON.stringify({schema_version: "1.0", task: "01", draft_digest: acceptedDigest,
      files: [
        {path: "model/manifest.json", sha256: manifestSha256},
        {path: "tasks/01.modeling-decisions.json", sha256: createHash("sha256").update(decisions).digest("hex")},
      ],
      quality: {required: true, status: "evidence_present", errors: []},
    });
    await writeFile(join(tasksDirectory, "01.modeling-quality.json"), report);
    acceptance.push({modeling_quality: {report_sha256: createHash("sha256").update(report).digest("hex")}});
  }
  await writeFile(
    join(tasksDirectory, "01.accept.json"),
    `${JSON.stringify(acceptance)}\n`,
    { mode: 0o600 },
  );
  return { manifestSha256, snapshotId };
}

async function metadataRequest(records: Array<Record<string, unknown>>) {
  const workspace = await mkdtemp(join(tmpdir(), "gds-stage-runner-"));
  const session = join(workspace, "GDS", "DEMO", "01");
  const changeSetDirectory = join(session, "metadata-change-set");
  const tasksDirectory = join(session, "tasks");
  await mkdir(changeSetDirectory, { recursive: true });
  await mkdir(tasksDirectory, { recursive: true });
  const payloadPath = join(changeSetDirectory, "source_object.json");
  const payload = `${JSON.stringify(records)}\n`;
  await writeFile(payloadPath, payload, { mode: 0o600 });
  const acceptedDigest = await workspaceDigest(changeSetDirectory);
  const { manifestSha256 } = await bindSession(
    session,
    "metadata",
    acceptedDigest,
    "source_object",
    ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"],
    1,
  );
  const manifestPath = join(tasksDirectory, "01.stage-request.json");
  await writeFile(
    manifestPath,
    `${JSON.stringify({
      schema_version: "2.0",
      kind: "gds-stage-request",
      area: "metadata",
      task: "01",
      accepted_digest: acceptedDigest,
      failed_retry: false,
      snapshot: {
        snapshot_id: SNAPSHOT_IDS.metadata,
        manifest_sha256: manifestSha256,
      },
      target: {
        tenant_code: "DEMO",
        change_set_id: CHANGE_SET_ID,
        starting_revision: 1,
      },
      datasets: [
        {
          dataset: "source_object",
          canonical_key: [
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
          ],
          record_count: records.length,
          payload_file: payloadPath,
          sha256: createHash("sha256").update(payload).digest("hex"),
        },
      ],
    })}\n`,
    { mode: 0o600 },
  );
  return { workspace, session, manifestPath, acceptedDigest };
}

async function modelRequest(
  dataset: string,
  canonicalKey: string[],
  records: Array<Record<string, unknown>>,
) {
  const workspace = await mkdtemp(join(tmpdir(), "gds-stage-runner-model-"));
  const session = join(workspace, "GDS", "DEMO", "01");
  const changeSetDirectory = join(session, "model-change-set");
  const tasksDirectory = join(session, "tasks");
  await mkdir(changeSetDirectory, { recursive: true });
  await mkdir(tasksDirectory, { recursive: true });
  const payloadPath = join(changeSetDirectory, `${dataset}.json`);
  const payload = `${JSON.stringify(records)}\n`;
  await writeFile(payloadPath, payload, { mode: 0o600 });
  const acceptedDigest = await workspaceDigest(changeSetDirectory);
  const { manifestSha256 } = await bindSession(
    session,
    "model",
    acceptedDigest,
    dataset,
    canonicalKey,
    3,
  );
  const manifestPath = join(tasksDirectory, "01.stage-request.json");
  await writeFile(
    manifestPath,
    `${JSON.stringify({
      schema_version: "2.0",
      kind: "gds-stage-request",
      area: "model",
      task: "01",
      accepted_digest: acceptedDigest,
      failed_retry: false,
      snapshot: { snapshot_id: SNAPSHOT_IDS.model, manifest_sha256: manifestSha256 },
      target: {
        model_id: 42,
        model_name: "Customer Model",
        model_revision: 8,
        change_set_id: CHANGE_SET_ID,
        starting_revision: 3,
      },
      datasets: [
        {
          dataset,
          canonical_key: canonicalKey,
          record_count: records.length,
          payload_file: payloadPath,
          sha256: createHash("sha256").update(payload).digest("hex"),
        },
      ],
    })}\n`,
    { mode: 0o600 },
  );
  return { workspace, session, manifestPath, acceptedDigest };
}

async function markFailedRetry(session: string, manifestPath: string): Promise<void> {
  const statePath = join(session, "session.json");
  const state = JSON.parse(await readFile(statePath, "utf8")) as {
    cs: { metadata?: unknown[]; model?: unknown[] };
  };
  const request = JSON.parse(await readFile(manifestPath, "utf8")) as {
    area: "metadata" | "model";
    failed_retry: boolean;
  };
  const draft = state.cs[request.area];
  if (!draft) throw new Error("Fixture has no cached draft");
  draft[4] = "0".repeat(64);
  draft.push("validation_failed");
  request.failed_retry = true;
  await writeFile(statePath, `${JSON.stringify(state)}\n`, { mode: 0o600 });
  await writeFile(manifestPath, `${JSON.stringify(request)}\n`, { mode: 0o600 });
}

async function addMetadataDataset(
  session: string,
  manifestPath: string,
  dataset: string,
  canonicalKey: string[],
  records: Array<Record<string, unknown>>,
): Promise<string> {
  const changeSetDirectory = join(session, "metadata-change-set");
  const payloadPath = join(changeSetDirectory, `${dataset}.json`);
  const payload = `${JSON.stringify(records)}\n`;
  await writeFile(payloadPath, payload, { mode: 0o600 });

  const snapshotDirectory = join(session, "metadata");
  const catalogPath = join(snapshotDirectory, "catalog.json");
  const catalog = JSON.parse(await readFile(catalogPath, "utf8")) as {
    sections: Array<{ datasets: Array<Record<string, unknown>> }>;
  };
  catalog.sections[0]!.datasets.push({ name: dataset, canonical_key: canonicalKey });
  const catalogBytes = `${JSON.stringify(catalog)}\n`;
  await writeFile(catalogPath, catalogBytes, { mode: 0o600 });
  const catalogSha256 = createHash("sha256").update(catalogBytes).digest("hex");

  const snapshotManifestPath = join(snapshotDirectory, "manifest.json");
  const snapshotManifest = JSON.parse(await readFile(snapshotManifestPath, "utf8")) as {
    catalog: { sha256: string };
    members: Array<{ path: string; size_bytes: number; sha256: string }>;
  };
  snapshotManifest.catalog.sha256 = catalogSha256;
  const catalogMember = snapshotManifest.members.find((member) => member.path === "catalog.json");
  if (!catalogMember) throw new Error("Fixture has no catalog member");
  catalogMember.size_bytes = Buffer.byteLength(catalogBytes);
  catalogMember.sha256 = catalogSha256;
  const snapshotManifestBytes = `${JSON.stringify(snapshotManifest)}\n`;
  await writeFile(snapshotManifestPath, snapshotManifestBytes, { mode: 0o600 });

  const acceptedDigest = await workspaceDigest(changeSetDirectory);
  const statePath = join(session, "session.json");
  const state = JSON.parse(await readFile(statePath, "utf8")) as {
    cs: { metadata: unknown[] };
  };
  state.cs.metadata[4] = acceptedDigest;
  await writeFile(statePath, `${JSON.stringify(state)}\n`, { mode: 0o600 });
  const acceptancePath = join(session, "tasks", "01.accept.json");
  const acceptance = JSON.parse(await readFile(acceptancePath, "utf8")) as unknown[];
  acceptance[0] = acceptedDigest;
  await writeFile(acceptancePath, `${JSON.stringify(acceptance)}\n`, { mode: 0o600 });

  const request = JSON.parse(await readFile(manifestPath, "utf8")) as {
    accepted_digest: string;
    snapshot: { manifest_sha256: string };
    datasets: Array<Record<string, unknown>>;
  };
  request.accepted_digest = acceptedDigest;
  request.snapshot.manifest_sha256 = createHash("sha256")
    .update(snapshotManifestBytes)
    .digest("hex");
  request.datasets.push({
    dataset,
    canonical_key: canonicalKey,
    record_count: records.length,
    payload_file: payloadPath,
    sha256: createHash("sha256").update(payload).digest("hex"),
  });
  request.datasets.sort((left, right) =>
    String(left.dataset).localeCompare(String(right.dataset)),
  );
  await writeFile(manifestPath, `${JSON.stringify(request)}\n`, { mode: 0o600 });
  return acceptedDigest;
}

describe("stageApprovedManifest", () => {
  test.each(["missing_acceptance", "changed_decisions", "stale_metadata"])(
    "rejects %s modeling evidence before MCP", async (scenario) => {
      const {workspace, session, manifestPath, acceptedDigest} = await modelRequest(
        "logical_entity", ["logical_entity_name"], [{logical_entity_name: "Customer"}],
      );
      if (scenario === "missing_acceptance") {
        const acceptance = JSON.parse(await readFile(join(session, "tasks/01.accept.json"), "utf8"));
        acceptance.pop();
        await writeFile(join(session, "tasks/01.accept.json"), JSON.stringify(acceptance));
      } else if (scenario === "changed_decisions") {
        await writeFile(join(session, "tasks/01.modeling-decisions.json"), "{}");
      } else {
        const state = JSON.parse(await readFile(join(session, "session.json"), "utf8"));
        state.stale = ["metadata"];
        await writeFile(join(session, "session.json"), JSON.stringify(state));
      }
      let calls = 0;
      await expect(stageApprovedManifest({manifestPath, expectedDigest: acceptedDigest}, {
        workspaceRoots: [workspace], mcp: {async callTool() { calls++; return {}; }},
      })).rejects.toMatchObject({code: "MODELING_EVIDENCE_CHANGED"});
      expect(calls).toBe(0);
    },
  );

  test("rechecks modeling evidence after remote reads and before the first write", async () => {
    const {workspace, session, manifestPath, acceptedDigest} = await modelRequest(
      "logical_entity", ["logical_entity_name"], [{logical_entity_name: "Customer"}],
    );
    let writes = 0;
    const mcp: McpToolClient = {async callTool(name, input) {
      if (name === "get_model_change_set") {
        if (input.dataset) await writeFile(join(session, "tasks/01.modeling-decisions.json"), "{}");
        return changeSetResponse("model", 3, input.dataset);
      }
      writes++;
      return {};
    }};
    await expect(stageApprovedManifest({manifestPath, expectedDigest: acceptedDigest}, {
      workspaceRoots: [workspace], mcp,
    })).rejects.toMatchObject({code: "MODELING_EVIDENCE_CHANGED"});
    expect(writes).toBe(0);
  });

  test("rejects an oversized payload before hashing or contacting MCP", async () => {
    const { workspace, session, manifestPath, acceptedDigest } = await metadataRequest([]);
    await truncate(join(session, "metadata-change-set", "source_object.json"), 64 * 450 * 1024 + 1025);
    let calls = 0;
    await expect(stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { workspaceRoots: [workspace], mcp: { async callTool() { calls += 1; return {}; } } },
    )).rejects.toMatchObject({ code: "PAYLOAD_LIMIT" });
    expect(calls).toBe(0);
  });

  test.each([
    ["acceptance", "LOCAL_STATE_MISMATCH"],
    ["payload", "DIGEST_MISMATCH"],
    ["manifest", "MANIFEST_CHANGED"],
  ])("rechecks changed %s after server reads and before writing", async (changed, code) => {
    const { workspace, session, manifestPath, acceptedDigest } = await metadataRequest([]);
    let writes = 0;
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") return tenantListResponse();
        if (name === "get_metadata_change_set") {
          if (input.dataset !== undefined) {
            if (changed === "acceptance") await writeFile(join(session, "tasks", "01.accept.json"), "[]");
            if (changed === "payload") await writeFile(join(session, "metadata-change-set", "source_object.json"), "[]  ");
            if (changed === "manifest") {
              const request = JSON.parse(await readFile(manifestPath, "utf8"));
              request.datasets[0].sha256 = "0".repeat(64);
              await writeFile(manifestPath, JSON.stringify(request));
            }
          }
          return changeSetResponse("metadata", 1, input.dataset);
        }
        if (name === "stage_metadata_change_set") {
          writes += 1;
          return directStageResponse("metadata", 2, { source_object: [] });
        }
        return fingerprintResponse("metadata", 2, { source_object: [] });
      },
    };

    await expect(stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest }, { mcp, workspaceRoots: [workspace] },
    )).rejects.toMatchObject({ code });
    expect(writes).toBe(0);
  });

  test("rejects a linked Change Set directory outside the workspace before MCP", async () => {
    const { workspace, session, manifestPath, acceptedDigest } = await metadataRequest([]);
    const directory = join(session, "metadata-change-set");
    const outside = await mkdtemp(join(tmpdir(), "gds-stage-outside-"));
    await rename(directory, join(outside, "payloads"));
    await symlink(join(outside, "payloads"), directory, "junction");
    let callCount = 0;

    await expect(stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { workspaceRoots: [workspace], mcp: { async callTool() { callCount += 1; return {}; } } },
    )).rejects.toMatchObject({ code: "LOCAL_CHANGE_SET_INVALID" });
    expect(callCount).toBe(0);
  });

  test("rejects a changed Snapshot manifest before any MCP call", async () => {
    const { workspace, session, manifestPath, acceptedDigest } = await metadataRequest([]);
    await writeFile(join(session, "metadata", "manifest.json"), "{}\n", { mode: 0o600 });
    let callCount = 0;
    const mcp: McpToolClient = {
      async callTool() {
        callCount += 1;
        throw new Error("MCP must not be called");
      },
    };

    const operation = stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    await expect(operation).rejects.toMatchObject({
      code: "SNAPSHOT_MISMATCH",
    });
    expect(callCount).toBe(0);
  });

  test("rejects a Stage request whose cached draft binding changed", async () => {
    const { workspace, session, manifestPath, acceptedDigest } = await metadataRequest([]);
    await writeFile(
      join(session, "session.json"),
      `${JSON.stringify({
        current: "01",
        tasks: [["01", "metadata", "Stage test", "ready"]],
        cs: {
          metadata: [
            "50000000-0000-4000-8000-000000000050",
            1,
            "active",
            "01",
            acceptedDigest,
          ],
        },
      })}\n`,
      { mode: 0o600 },
    );
    let callCount = 0;
    const mcp: McpToolClient = {
      async callTool() {
        callCount += 1;
        throw new Error("MCP must not be called");
      },
    };

    const operation = stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    await expect(operation).rejects.toMatchObject({
      code: "LOCAL_STATE_MISMATCH",
    });
    expect(callCount).toBe(0);
  });

  test("rejects a canonical key that differs from the bound Snapshot", async () => {
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([]);
    const request = JSON.parse(await readFile(manifestPath, "utf8")) as {
      datasets: Array<{ canonical_key: string[] }>;
    };
    request.datasets[0]!.canonical_key = ["object_name"];
    await writeFile(manifestPath, `${JSON.stringify(request)}\n`, { mode: 0o600 });
    let callCount = 0;
    const mcp: McpToolClient = {
      async callTool() {
        callCount += 1;
        throw new Error("MCP must not be called");
      },
    };

    const operation = stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    await expect(operation).rejects.toMatchObject({
      code: "SNAPSHOT_MISMATCH",
    });
    expect(callCount).toBe(0);
  });

  test("rejects a symbolic-link Stage request before any MCP call", async () => {
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([]);
    const targetPath = `${manifestPath}.real`;
    await rename(manifestPath, targetPath);
    await symlink(targetPath, manifestPath);
    let callCount = 0;
    const mcp: McpToolClient = {
      async callTool() {
        callCount += 1;
        throw new Error("MCP must not be called");
      },
    };

    const operation = stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    await expect(operation).rejects.toMatchObject({
      code: "MANIFEST_INVALID",
    });
    expect(callCount).toBe(0);
  });

  test("rejects unknown manifest fields before any MCP call", async () => {
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([]);
    const request = JSON.parse(await readFile(manifestPath, "utf8")) as Record<string, unknown>;
    request.command = "anything";
    await writeFile(manifestPath, `${JSON.stringify(request)}\n`, { mode: 0o600 });
    let callCount = 0;
    const mcp: McpToolClient = {
      async callTool() {
        callCount += 1;
        throw new Error("MCP must not be called");
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "MANIFEST_INVALID" });
    expect(callCount).toBe(0);
  });

  test("rejects malformed IDs and area-specific target fields before MCP", async () => {
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([]);
    const request = JSON.parse(await readFile(manifestPath, "utf8")) as {
      snapshot: { snapshot_id: string };
      target: Record<string, unknown>;
    };
    request.snapshot.snapshot_id = "not-a-uuid";
    request.target.model_id = 42;
    await writeFile(manifestPath, `${JSON.stringify(request)}\n`, { mode: 0o600 });
    let callCount = 0;
    const mcp: McpToolClient = {
      async callTool() {
        callCount += 1;
        throw new Error("MCP must not be called");
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "MANIFEST_INVALID" });
    expect(callCount).toBe(0);
  });

  test("rejects a renamed request before MCP", async () => {
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([]);
    const renamedPath = join(dirname(manifestPath), "other.json");
    await rename(manifestPath, renamedPath);
    let callCount = 0;
    const mcp: McpToolClient = {
      async callTool() {
        callCount += 1;
        throw new Error("MCP must not be called");
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath: renamedPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "MANIFEST_INVALID" });
    expect(callCount).toBe(0);
  });

  test("rejects an excessive dataset record count before MCP", async () => {
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([]);
    const request = JSON.parse(await readFile(manifestPath, "utf8")) as {
      datasets: Array<{ record_count: number }>;
    };
    request.datasets[0]!.record_count = 50_001;
    await writeFile(manifestPath, `${JSON.stringify(request)}\n`, { mode: 0o600 });
    let callCount = 0;
    const mcp: McpToolClient = {
      async callTool() {
        callCount += 1;
        throw new Error("MCP must not be called");
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "MANIFEST_INVALID" });
    expect(callCount).toBe(0);
  });

  test("rejects an oversized Stage request manifest before MCP", async () => {
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([]);
    await writeFile(manifestPath, " ".repeat(128 * 1024 + 1), { mode: 0o600 });
    let callCount = 0;
    const mcp: McpToolClient = {
      async callTool() {
        callCount += 1;
        throw new Error("MCP must not be called");
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "MANIFEST_LIMIT" });
    expect(callCount).toBe(0);
  });

  test("merges non-overlapping server records before replacement Stage", async () => {
    const localRecord = {
      tenant_code: "DEMO",
      system_code: "CRM",
      connection_code: "MAIN",
      object_schema: "sales",
      object_name: "Customer",
    };
    const serverRecord = {
      tenant_code: "DEMO",
      system_code: "ERP",
      connection_code: "MAIN",
      object_schema: "sales",
      object_name: "Order",
    };
    const expected = [localRecord, serverRecord];
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([localRecord]);
    let staged: unknown;
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset, [serverRecord]);
        }
        if (name === "stage_metadata_change_set") {
          staged = input.changes;
          return directStageResponse("metadata", 2, { source_object: expected });
        }
        if (name === "get_metadata_change_set_fingerprint") {
          return fingerprintResponse("metadata", 2, { source_object: expected });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    await stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    expect(staged).toEqual([{ dataset: "source_object", records: expected }]);
  });

  test("honors cancellation at the final pre-write boundary", async () => {
    const records = [
      {
        tenant_code: "DEMO",
        system_code: "CRM",
        connection_code: "MAIN",
        object_schema: "sales",
        object_name: "Customer",
      },
    ];
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest(records);
    let writeCount = 0;
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") return tenantListResponse();
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset);
        }
        writeCount += 1;
        throw new Error(`Unexpected write: ${name}`);
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        {
          mcp,
          workspaceRoots: [workspace],
          isCancellationRequested: () => true,
        },
      ),
    ).rejects.toMatchObject({ code: "CANCELLED" });
    expect(writeCount).toBe(0);
  });

  test("rejects a differing record at the same canonical key before writing", async () => {
    const localRecord = {
      tenant_code: "DEMO",
      system_code: "CRM",
      connection_code: "MAIN",
      object_schema: "sales",
      object_name: "Customer",
      is_active: true,
    };
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([localRecord]);
    let writeCount = 0;
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset, [
            { ...localRecord, is_active: false },
          ]);
        }
        writeCount += 1;
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "RECONCILIATION_CONFLICT" });
    expect(writeCount).toBe(0);
  });

  test("rejects an ordinary explicit clear when server pending records exist", async () => {
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([]);
    let writeCount = 0;
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset, [{ object_name: "Server" }]);
        }
        writeCount += 1;
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "RECONCILIATION_CONFLICT" });
    expect(writeCount).toBe(0);
  });

  test("failed-draft retry replaces server pending records, including explicit clear", async () => {
    const { workspace, session, manifestPath, acceptedDigest } = await metadataRequest([]);
    await markFailedRetry(session, manifestPath);
    let staged: unknown;
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset, [{ object_name: "Stale" }]);
        }
        if (name === "stage_metadata_change_set") {
          staged = input.changes;
          return directStageResponse("metadata", 2, { source_object: [] });
        }
        if (name === "get_metadata_change_set_fingerprint") {
          return fingerprintResponse("metadata", 2, { source_object: [] });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    const receipt = await stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    expect(staged).toEqual([{ dataset: "source_object", records: [] }]);
    expect(receipt.datasets).toEqual([{ dataset: "source_object", recordCount: 0 }]);
  });

  test("stages one approved Metadata request without returning payload records", async () => {
    const records = [
      {
        tenant_code: "DEMO",
        system_code: "CRM",
        connection_code: "MAIN",
        object_schema: "sales",
        object_name: "Customer",
        is_active: true,
      },
    ];
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest(records);
    const expectedFingerprint = fingerprintResponse("metadata", 2, { source_object: records });

    const calls: Array<[string, Record<string, unknown>]> = [];
    const mcp: McpToolClient = {
      async callTool(name, input) {
        calls.push([name, input]);
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset);
        }
        if (name === "stage_metadata_change_set") {
          expect(input).toEqual({
            tenant_id: 17,
            metadata_change_set_id: CHANGE_SET_ID,
            expected_draft_revision: 1,
            changes: [{ dataset: "source_object", records }],
          });
          return directStageResponse("metadata", 2, { source_object: records });
        }
        if (name === "get_metadata_change_set_fingerprint") {
          return expectedFingerprint;
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    const receipt = await stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    expect(receipt).toEqual({
      schemaVersion: "1.0",
      status: "staged",
      area: "metadata",
      changeSetId: CHANGE_SET_ID,
      startingRevision: 1,
      resultingRevision: 2,
      acceptedDigest,
      stageFingerprint: expectedFingerprint.fingerprint,
      fingerprintVerified: true,
      datasets: [{ dataset: "source_object", recordCount: 1 }],
    });
    expect(JSON.stringify(receipt)).not.toContain("Customer");
    expect(calls.map(([name]) => name)).toEqual([
      "list_tenants",
      "get_metadata_change_set",
      "get_metadata_change_set",
      "stage_metadata_change_set",
      "get_metadata_change_set_fingerprint",
    ]);
  });

  test.each([1, undefined])("rejects a different acknowledged dataset with count %s", async (count) => {
    const records = [
      {
        tenant_code: "DEMO",
        system_code: "CRM",
        connection_code: "MAIN",
        object_schema: "sales",
        object_name: "Customer",
      },
    ];
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest(records);
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset);
        }
        if (name === "stage_metadata_change_set") {
          return {
            schema_version: "1.0",
            tenant_id: 17,
            metadata_change_set_id: CHANGE_SET_ID,
            staged: true,
            datasets: [{ dataset: "source_attribute", record_count: count }],
            status: "active",
            draft_revision: 2,
          };
        }
        if (name === "get_metadata_change_set_fingerprint") {
          return fingerprintResponse("metadata", 2, { source_object: records });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "MCP_RESPONSE_INVALID" });
  });

  test("rejects a Change Set read response for a different target before writing", async () => {
    const records = [
      {
        tenant_code: "DEMO",
        system_code: "CRM",
        connection_code: "MAIN",
        object_schema: "sales",
        object_name: "Customer",
      },
    ];
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest(records);
    let writeCount = 0;
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return { ...changeSetResponse("metadata", 1, input.dataset), tenant_id: 18 };
        }
        writeCount += 1;
        return directStageResponse("metadata", 2, { source_object: records });
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "MCP_RESPONSE_INVALID" });
    expect(writeCount).toBe(0);
  });

  test("requires the Metadata Tenant Code to resolve uniquely across all pages", async () => {
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest([]);
    let listCalls = 0;
    const mcp: McpToolClient = {
      async callTool(name) {
        if (name !== "list_tenants") throw new Error(`Unexpected tool: ${name}`);
        listCalls += 1;
        return listCalls === 1
          ? tenantListResponse([{ tenant_id: 17, tenant_code: "DEMO" }], "page-2")
          : tenantListResponse([{ tenant_id: 18, tenant_code: "demo" }]);
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "TARGET_MISMATCH" });
    expect(listCalls).toBe(2);
  });

  test.each(["x", "é", "😀"])("batches a Metadata dataset with %s beyond the direct transport limit", async (character) => {
    const records = [0, 1].map((index) => ({
      tenant_code: "DEMO",
      system_code: "CRM",
      connection_code: "MAIN",
      object_schema: "sales",
      object_name: `Customer${index}_${character.repeat(40_000)}`,
      is_active: true,
    }));
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest(records);
    const calls: Array<[string, Record<string, unknown>]> = [];
    const stageBatchId = "40000000-0000-4000-8000-000000000050";
    const mcp: McpToolClient = {
      async callTool(name, input) {
        calls.push([name, input]);
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset);
        }
        if (name === "begin_metadata_stage_batch") {
          expect(input.total_record_count).toBe(2);
          expect(input.total_chunk_count).toBe(2);
          expect(input.dataset).toBe("source_object");
          return beginStageResponse("metadata", input, stageBatchId);
        }
        if (name === "put_metadata_stage_chunk") {
          expect(Array.isArray(input.records)).toBe(true);
          expect(input.records).toHaveLength(1);
          return putStageResponse("metadata", input, 2);
        }
        if (name === "commit_metadata_stage_batch") {
          return commitStageResponse("metadata", input, "source_object", 2, 2);
        }
        if (name === "get_metadata_change_set_fingerprint") {
          return fingerprintResponse("metadata", 2, { source_object: records });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    const receipt = await stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    expect(receipt.resultingRevision).toBe(2);
    expect(calls.map(([name]) => name)).toEqual([
      "list_tenants",
      "get_metadata_change_set",
      "get_metadata_change_set",
      "begin_metadata_stage_batch",
      "put_metadata_stage_chunk",
      "put_metadata_stage_chunk",
      "commit_metadata_stage_batch",
      "get_metadata_change_set_fingerprint",
    ]);
  });

  test("resumes an identical incomplete Stage batch from its received chunk count", async () => {
    const records = [0, 1].map((index) => ({
      tenant_code: "DEMO",
      system_code: "CRM",
      connection_code: "MAIN",
      object_schema: "sales",
      object_name: `Customer${index}_${"x".repeat(40_000)}`,
      is_active: true,
    }));
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest(records);
    const stageBatchId = "40000000-0000-4000-8000-000000000050";
    const putIndexes: unknown[] = [];
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") return tenantListResponse();
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset);
        }
        if (name === "begin_metadata_stage_batch") {
          return {
            ...beginStageResponse("metadata", input, stageBatchId),
            created: false,
            received_chunk_count: 1,
          };
        }
        if (name === "put_metadata_stage_chunk") {
          putIndexes.push(input.chunk_index);
          return putStageResponse("metadata", input, 2);
        }
        if (name === "commit_metadata_stage_batch") {
          return commitStageResponse("metadata", input, "source_object", 2, 2);
        }
        if (name === "get_metadata_change_set_fingerprint") {
          return fingerprintResponse("metadata", 2, { source_object: records });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    await stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    expect(putIndexes).toEqual([2]);
  });

  test("fails closed when a batch acknowledgement names a different dataset", async () => {
    const records = [0, 1].map((index) => ({
      tenant_code: "DEMO",
      system_code: "CRM",
      connection_code: "MAIN",
      object_schema: "sales",
      object_name: `Customer${index}_${"x".repeat(40_000)}`,
    }));
    const { workspace, manifestPath, acceptedDigest } = await metadataRequest(records);
    const stageBatchId = "40000000-0000-4000-8000-000000000050";
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset);
        }
        if (name === "begin_metadata_stage_batch") {
          return beginStageResponse("metadata", input, stageBatchId);
        }
        if (name === "put_metadata_stage_chunk") {
          return putStageResponse("metadata", input, 2);
        }
        if (name === "commit_metadata_stage_batch") {
          return {
            schema_version: "1.0",
            tenant_id: 17,
            metadata_change_set_id: CHANGE_SET_ID,
            stage_batch_id: stageBatchId,
            dataset: "source_attribute",
            committed: true,
            replayed: false,
            record_count: records.length,
            draft_revision: 2,
            status: "active",
          };
        }
        if (name === "get_metadata_change_set_fingerprint") {
          return fingerprintResponse("metadata", 2, { source_object: records });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "MCP_RESPONSE_INVALID" });
  });

  test("carries each returned revision through a mixed direct and batch Stage", async () => {
    const largeRecords = [0, 1].map((index) => ({
      tenant_code: "DEMO",
      system_code: "CRM",
      connection_code: "MAIN",
      object_schema: "sales",
      object_name: `Customer${index}_${"x".repeat(40_000)}`,
    }));
    const prepared = await metadataRequest(largeRecords);
    const acceptedDigest = await addMetadataDataset(
      prepared.session,
      prepared.manifestPath,
      "source_attribute",
      [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
        "attribute_name",
      ],
      [],
    );
    const calls: Array<[string, Record<string, unknown>]> = [];
    const stageBatchId = "40000000-0000-4000-8000-000000000051";
    const mcp: McpToolClient = {
      async callTool(name, input) {
        calls.push([name, input]);
        if (name === "list_tenants") {
          return tenantListResponse();
        }
        if (name === "get_metadata_change_set") {
          return changeSetResponse("metadata", 1, input.dataset);
        }
        if (name === "stage_metadata_change_set") {
          expect(input.expected_draft_revision).toBe(1);
          expect(input.changes).toEqual([{ dataset: "source_attribute", records: [] }]);
          return directStageResponse("metadata", 2, { source_attribute: [] });
        }
        if (name === "begin_metadata_stage_batch") {
          expect(input.expected_draft_revision).toBe(2);
          return beginStageResponse("metadata", input, stageBatchId);
        }
        if (name === "put_metadata_stage_chunk") {
          return putStageResponse("metadata", input, 2);
        }
        if (name === "commit_metadata_stage_batch") {
          expect(input.expected_draft_revision).toBe(2);
          return commitStageResponse("metadata", input, "source_object", 2, 3);
        }
        if (name === "get_metadata_change_set_fingerprint") {
          return fingerprintResponse("metadata", 3, {
            source_attribute: [],
            source_object: largeRecords,
          });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    const receipt = await stageApprovedManifest(
      { manifestPath: prepared.manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [prepared.workspace] },
    );

    expect(receipt.resultingRevision).toBe(3);
    expect(calls.filter(([name]) => name === "stage_metadata_change_set")).toHaveLength(1);
    expect(calls.filter(([name]) => name === "commit_metadata_stage_batch")).toHaveLength(1);
  });

  test("rejects an unstageable batch before writing another dataset", async () => {
    const prepared = await metadataRequest([{
      tenant_code: "DEMO", system_code: "CRM", connection_code: "MAIN",
      object_schema: "sales", object_name: "Customer", description: "x".repeat(450 * 1024),
    }]);
    const acceptedDigest = await addMetadataDataset(
      prepared.session, prepared.manifestPath, "source_attribute", ["attribute_name"], [],
    );
    let writeStarted = false;
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "list_tenants") return tenantListResponse();
        if (name === "get_metadata_change_set") return changeSetResponse("metadata", 1, input.dataset);
        if (name === "stage_metadata_change_set") {
          return directStageResponse("metadata", 2, { source_attribute: [] });
        }
        throw new Error("Unexpected tool");
      },
    };

    await expect(stageApprovedManifest(
      { manifestPath: prepared.manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [prepared.workspace], onWriteStart: () => { writeStarted = true; } },
    )).rejects.toMatchObject({ code: "PAYLOAD_LIMIT" });
    expect(writeStarted).toBe(false);
  });

  test("derives the Model target from the approved request without a Tenant lookup", async () => {
    const workspace = await mkdtemp(join(tmpdir(), "gds-stage-runner-model-"));
    const session = join(workspace, "GDS", "DEMO", "01");
    const changeSetDirectory = join(session, "model-change-set");
    const tasksDirectory = join(session, "tasks");
    await mkdir(changeSetDirectory, { recursive: true });
    await mkdir(tasksDirectory, { recursive: true });
    const records = [{ logical_entity_name: "Customer" }];
    const payloadPath = join(changeSetDirectory, "logical_entity.json");
    const payload = `${JSON.stringify(records)}\n`;
    await writeFile(payloadPath, payload, { mode: 0o600 });
    const acceptedDigest = await workspaceDigest(changeSetDirectory);
    const { manifestSha256 } = await bindSession(
      session,
      "model",
      acceptedDigest,
      "logical_entity",
      ["logical_entity_name"],
      3,
    );
    const manifestPath = join(tasksDirectory, "01.stage-request.json");
    await writeFile(
      manifestPath,
      `${JSON.stringify({
        schema_version: "2.0",
        kind: "gds-stage-request",
        area: "model",
        task: "01",
        accepted_digest: acceptedDigest,
        failed_retry: false,
        snapshot: {
          snapshot_id: SNAPSHOT_IDS.model,
          manifest_sha256: manifestSha256,
        },
        target: {
          model_id: 42,
          model_name: "Customer Model",
          model_revision: 8,
          change_set_id: CHANGE_SET_ID,
          starting_revision: 3,
        },
        datasets: [
          {
            dataset: "logical_entity",
            canonical_key: ["logical_entity_name"],
            record_count: 1,
            payload_file: payloadPath,
            sha256: createHash("sha256").update(payload).digest("hex"),
          },
        ],
      })}\n`,
      { mode: 0o600 },
    );
    const calls: Array<[string, Record<string, unknown>]> = [];
    const mcp: McpToolClient = {
      async callTool(name, input) {
        calls.push([name, input]);
        if (name === "get_model_change_set") {
          return changeSetResponse("model", 3, input.dataset);
        }
        if (name === "stage_model_change_set") {
          expect(input).toEqual({
            model_id: 42,
            model_change_set_id: CHANGE_SET_ID,
            expected_draft_revision: 3,
            changes: [{ dataset: "logical_entity", records }],
          });
          return directStageResponse("model", 4, { logical_entity: records });
        }
        if (name === "get_model_change_set_fingerprint") {
          return fingerprintResponse("model", 4, { logical_entity: records });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    const receipt = await stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    expect(receipt.area).toBe("model");
    expect(receipt.resultingRevision).toBe(4);
    expect(calls.map(([name]) => name).includes("list_tenants")).toBe(false);
  });

  test("stages the singleton model_details dataset with its empty canonical key", async () => {
    const records = [{ model_name: "Customer Model", model_description: "Customers" }];
    const { workspace, manifestPath, acceptedDigest } = await modelRequest(
      "model_details",
      [],
      records,
    );
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "get_model_change_set") {
          return changeSetResponse("model", 3, input.dataset);
        }
        if (name === "stage_model_change_set") {
          return directStageResponse("model", 4, { model_details: records });
        }
        if (name === "get_model_change_set_fingerprint") {
          return fingerprintResponse("model", 4, { model_details: records });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    const receipt = await stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    expect(receipt.datasets).toEqual([{ dataset: "model_details", recordCount: 1 }]);
  });

  test("binds the local digest to the authoritative fingerprint after server normalization", async () => {
    const records = [{ logical_entity_name: "Customer" }];
    const { workspace, manifestPath, acceptedDigest } = await modelRequest(
      "logical_entity",
      ["logical_entity_name"],
      records,
    );
    const normalizedFingerprint = fingerprintResponse(
      "model",
      4,
      { logical_entity: records },
      { logical_entity: "7".repeat(64) },
    );
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "get_model_change_set") {
          return changeSetResponse("model", 3, input.dataset);
        }
        if (name === "stage_model_change_set") {
          return directStageResponse("model", 4, { logical_entity: records });
        }
        if (name === "get_model_change_set_fingerprint") {
          return normalizedFingerprint;
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    const receipt = await stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    expect(receipt.acceptedDigest).toBe(acceptedDigest);
    expect(receipt.stageFingerprint).toBe(normalizedFingerprint.fingerprint);
    expect(receipt.fingerprintVerified).toBe(true);
  });

  test("rejects a self-consistent fingerprint with a noncanonical dataset order", async () => {
    const records = [{ logical_entity_name: "Customer" }];
    const { workspace, manifestPath, acceptedDigest } = await modelRequest(
      "logical_entity",
      ["logical_entity_name"],
      records,
    );
    const fingerprint = fingerprintResponse("model", 4, { logical_entity: records });
    fingerprint.datasets = [...fingerprint.datasets].reverse();
    fingerprint.fingerprint = createHash("sha256")
      .update(
        JSON.stringify({
          area: "model",
          datasets: fingerprint.datasets,
          fingerprint_version: "1.0",
        }),
      )
      .digest("hex");
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "get_model_change_set") {
          return changeSetResponse("model", 3, input.dataset);
        }
        if (name === "stage_model_change_set") {
          return directStageResponse("model", 4, { logical_entity: records });
        }
        if (name === "get_model_change_set_fingerprint") return fingerprint;
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "FINGERPRINT_MISMATCH" });
  });

  test("rejects a tampered aggregate fingerprint", async () => {
    const records = [{ logical_entity_name: "Customer" }];
    const { workspace, manifestPath, acceptedDigest } = await modelRequest(
      "logical_entity",
      ["logical_entity_name"],
      records,
    );
    const fingerprint = fingerprintResponse("model", 4, { logical_entity: records });
    fingerprint.fingerprint = "f".repeat(64);
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "get_model_change_set") {
          return changeSetResponse("model", 3, input.dataset);
        }
        if (name === "stage_model_change_set") {
          return directStageResponse("model", 4, { logical_entity: records });
        }
        if (name === "get_model_change_set_fingerprint") return fingerprint;
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    await expect(
      stageApprovedManifest(
        { manifestPath, expectedDigest: acceptedDigest },
        { mcp, workspaceRoots: [workspace] },
      ),
    ).rejects.toMatchObject({ code: "FINGERPRINT_MISMATCH" });
  });

  test("rejects duplicate server Model keys using Unicode casefolding", async () => {
    const records = [{ logical_entity_name: "Other" }];
    const { workspace, manifestPath, acceptedDigest } = await modelRequest(
      "logical_entity",
      ["logical_entity_name"],
      records,
    );
    let writeCount = 0;
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "get_model_change_set") {
          return changeSetResponse("model", 3, input.dataset, [
            { logical_entity_name: "Straße" },
            { logical_entity_name: "STRASSE" },
          ]);
        }
        writeCount += 1;
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    const operation = stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    await expect(operation).rejects.toMatchObject({
      code: "MCP_RESPONSE_INVALID",
    });
    expect(writeCount).toBe(0);
  });

  test("uses bounded JSON fragments only for oversized generated code", async () => {
    const workspace = await mkdtemp(join(tmpdir(), "gds-stage-runner-code-"));
    const session = join(workspace, "GDS", "DEMO", "01");
    const changeSetDirectory = join(session, "model-change-set");
    const tasksDirectory = join(session, "tasks");
    await mkdir(changeSetDirectory, { recursive: true });
    await mkdir(tasksDirectory, { recursive: true });
    const records = [{ artifact_name: "customers.sql", sql: "x".repeat(1_200_000) }];
    const payloadPath = join(changeSetDirectory, "generated_code.json");
    const payload = `${JSON.stringify(records)}\n`;
    await writeFile(payloadPath, payload, { mode: 0o600 });
    const acceptedDigest = await workspaceDigest(changeSetDirectory);
    const { manifestSha256 } = await bindSession(
      session,
      "model",
      acceptedDigest,
      "generated_code",
      ["artifact_name"],
      3,
    );
    const manifestPath = join(tasksDirectory, "01.stage-request.json");
    await writeFile(
      manifestPath,
      `${JSON.stringify({
        schema_version: "2.0",
        kind: "gds-stage-request",
        area: "model",
        task: "01",
        accepted_digest: acceptedDigest,
        failed_retry: false,
        snapshot: {
          snapshot_id: SNAPSHOT_IDS.model,
          manifest_sha256: manifestSha256,
        },
        target: {
          model_id: 42,
          model_name: "Customer Model",
          model_revision: 8,
          change_set_id: CHANGE_SET_ID,
          starting_revision: 3,
        },
        datasets: [
          {
            dataset: "generated_code",
            canonical_key: ["artifact_name"],
            record_count: 1,
            payload_file: payloadPath,
            sha256: createHash("sha256").update(payload).digest("hex"),
          },
        ],
      })}\n`,
      { mode: 0o600 },
    );
    const fragments: Buffer[] = [];
    let totalChunkCount = 0;
    const stageBatchId = "40000000-0000-4000-8000-000000000050";
    const mcp: McpToolClient = {
      async callTool(name, input) {
        if (name === "get_model_change_set") {
          return changeSetResponse("model", 3, input.dataset);
        }
        if (name === "begin_model_stage_batch") {
          expect(input.payload_mode).toBe("json_fragments");
          expect(input.total_payload_bytes).toBeGreaterThan(1_000_000);
          expect(input.total_chunk_count).toBeLessThanOrEqual(64);
          totalChunkCount = Number(input.total_chunk_count);
          return beginStageResponse("model", input, stageBatchId);
        }
        if (name === "put_model_stage_chunk") {
          expect(input.payload_mode).toBe("json_fragments");
          expect(input.records).toBeUndefined();
          const fragment = Buffer.from(String(input.payload_fragment_base64), "base64");
          expect(fragment.length).toBeLessThanOrEqual(1024 * 1024);
          fragments.push(fragment);
          return putStageResponse("model", input, totalChunkCount);
        }
        if (name === "commit_model_stage_batch") {
          return commitStageResponse("model", input, "generated_code", 1, 4);
        }
        if (name === "get_model_change_set_fingerprint") {
          return fingerprintResponse("model", 4, { generated_code: records });
        }
        throw new Error(`Unexpected tool: ${name}`);
      },
    };

    const receipt = await stageApprovedManifest(
      { manifestPath, expectedDigest: acceptedDigest },
      { mcp, workspaceRoots: [workspace] },
    );

    expect(receipt.resultingRevision).toBe(4);
    expect(JSON.parse(Buffer.concat(fragments).toString("utf8"))).toEqual(records);
    const receiptBytes = Buffer.byteLength(JSON.stringify(receipt), "utf8");
    expect(Buffer.byteLength(payload, "utf8")).toBeGreaterThan(1_000_000);
    expect(receiptBytes).toBeLessThan(2_048);
    expect(Buffer.byteLength(payload, "utf8") / receiptBytes).toBeGreaterThan(500);
    expect(JSON.stringify(receipt)).not.toContain("x".repeat(100));
  });
});
