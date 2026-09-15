import { stableStringify, canonicalRecordsSha256, SHA256, fail, isObject, requireObject, normalizedTenantCode, recordKey,
 type Area, type StageRequestDataset, type JsonRecord, type McpToolClient,
 type StageApprovedManifestInput, type StageRunnerDependencies, type StageReceipt } from "./stage-contract.js";
import { readRequest, readLocalDatasets, saveOperation } from "./stage-request.js";
import { stageTarget, verifyChangeSetReadResponse, verifyStageFingerprint, executeStage } from "./stage-transport.js";
export { StageRunnerError, canonicalRecordsSha256, type McpToolClient, type StageApprovedManifestInput,
 type StageRunnerDependencies, type StageReceipt } from "./stage-contract.js";
export { workspaceDigest } from "./stage-request.js";
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

// Compare complete reconciled rows without persisting physical rows in operation evidence.
function recoveryHash(area: Area, definition: StageRequestDataset, records: JsonRecord[]): string {
  const keyed = records.map(record => [recordKey(area, definition, record), record] as const);
  const keys = new Set(keyed.map(([key]) => key));
  if (keys.size !== keyed.length) fail("RECOVERY_UNPROVEN", "Recovery records contain duplicate canonical keys.");
  return canonicalRecordsSha256(keyed.sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0).map(([,record])=>record));
}

export async function stageApprovedManifest(
  input: StageApprovedManifestInput,
  dependencies: StageRunnerDependencies,
): Promise<StageReceipt> {
  const approved = await readRequest(
    input,
    dependencies.workspaceRoots,
    dependencies.backend,
  );
  const { request, changeSetDirectory } = approved;
  const local = await readLocalDatasets(request, changeSetDirectory, approved.session);
  let scopeId: number;
  if (request.area === "metadata") {
    if (typeof request.target.tenant_code !== "string" || !request.target.tenant_code.trim()) {
      fail("MANIFEST_INVALID", "Metadata Stage request has no Tenant Code.");
    }
    scopeId = await resolveMetadataTenant(dependencies.mcp, request.target.tenant_code);
    if (scopeId !== request.owner.id) fail("TARGET_MISMATCH", "Resolved Tenant differs from the approved owner.");
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
  if (input.recoverOnly === true) {
    const attempt = approved.operation.stage_attempt;
    if (!isObject(attempt) || attempt.status !== "unknown" || attempt.accepted_digest !== request.accepted_digest ||
        !Array.isArray(attempt.datasets) || attempt.datasets.length !== request.datasets.length) {
      fail("RECOVERY_UNPROVEN", "Recovery needs the saved intended dataset hashes from the uncertain attempt. Nothing was replayed.");
    }
    const revision = summary.draft_revision;
    if (typeof revision !== "number" || !Number.isSafeInteger(revision) || revision <= request.target.starting_revision) {
      fail("RECOVERY_UNPROVEN", "The draft has not advanced to a provable completed Stage. Keep the uncertain attempt; inspect the server draft.");
    }
    verifyChangeSetReadResponse(request, target, revision, null, summary);
    const recovered: Array<{dataset:string;records:JsonRecord[]}> = [];
    const seen = new Set<string>();
    for (const intended of attempt.datasets) {
      if (!isObject(intended) || typeof intended.dataset !== "string" || seen.has(intended.dataset) ||
          !Number.isSafeInteger(intended.record_count) || Number(intended.record_count) < 0 ||
          typeof intended.sha256 !== "string" || !SHA256.test(intended.sha256)) fail("RECOVERY_UNPROVEN", "Saved recovery hashes are incomplete or invalid.");
      seen.add(intended.dataset);
      const definition = request.datasets.find(item => item.dataset === intended.dataset);
      if (!definition) fail("RECOVERY_UNPROVEN", "Saved recovery dataset does not belong to this operation.");
      const response = requireObject(await dependencies.mcp.callTool(`get_${request.area}_change_set`, {...target,dataset:intended.dataset}), "MCP_RESPONSE_INVALID");
      const records = verifyChangeSetReadResponse(request, target, revision, intended.dataset, response);
      if (!records || records.length !== intended.record_count || recoveryHash(request.area, definition, records) !== intended.sha256) {
        fail("RECOVERY_UNPROVEN", "Server records differ from the saved Stage intent. Keep the uncertain attempt; inspect or reconcile the draft. Nothing was replayed.");
      }
      recovered.push({dataset:intended.dataset,records});
    }
    const fingerprintResponse = requireObject(await dependencies.mcp.callTool(`get_${request.area}_change_set_fingerprint`, target), "MCP_RESPONSE_INVALID");
    const fingerprint = verifyStageFingerprint(request, scopeId, revision, recovered, fingerprintResponse);
    for (const change of recovered) {
      const bound = (fingerprintResponse.datasets as Array<Record<string,unknown>>).find(item => item.dataset === change.dataset);
      if (bound?.sha256 !== canonicalRecordsSha256(change.records)) fail("RECOVERY_UNPROVEN", "Governed fingerprint differs from the recovered records; inspect the server draft without replaying.");
    }
    const refreshed = await readRequest(input, dependencies.workspaceRoots, dependencies.backend);
    if (refreshed.operationSha256 !== approved.operationSha256 || stableStringify(refreshed.request) !== stableStringify(request)) fail("MANIFEST_CHANGED", "Approval changed during recovery.");
    const receipt: StageReceipt = {schema_version:"1.0",status:"staged",task_id:request.task,operation_id:request.operation.id,
      owner_tenant_id:request.owner.id,owner_root:request.owner.root,backend:request.backend,area:request.area,
      change_set_id:request.target.change_set_id,starting_revision:request.target.starting_revision,draft_revision:revision,
      accepted_digest:request.accepted_digest,stage_fingerprint:fingerprint,fingerprint_verified:true,
      datasets:recovered.map(change=>({dataset:change.dataset,record_count:change.records.length}))};
    await saveOperation(approved,{draft:{id:request.target.change_set_id,revision,status:"active",digest:request.accepted_digest},
      stage:{...receipt,received_at:new Date().toISOString(),recovered:true},
      stage_attempt:{...attempt,status:"verified",completed_at:new Date().toISOString()}});
    return receipt;
  }
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
  const refreshed = await readRequest(input, dependencies.workspaceRoots, dependencies.backend);
  if (stableStringify(refreshed.request) !== stableStringify(request) || refreshed.operationSha256 !== approved.operationSha256) {
    fail("MANIFEST_CHANGED", "Stage request changed while preparing to write.");
  }
  const draft_revision = await executeStage(
    request,
    dependencies.mcp,
    target,
    changes,
    dependencies.isCancellationRequested,
    async () => {
      await saveOperation(approved, { stage_attempt: { status: "unknown", started_at: new Date().toISOString(), accepted_digest: request.accepted_digest,
        datasets: changes.map(change => ({dataset:change.dataset,record_count:change.records.length,
          sha256:recoveryHash(request.area, request.datasets.find(item=>item.dataset===change.dataset)!, change.records)})) } });
      dependencies.onWriteStart?.();
    },
  );
  const stage_fingerprint = verifyStageFingerprint(
    request,
    scopeId,
    draft_revision,
    changes,
    await dependencies.mcp.callTool(`get_${request.area}_change_set_fingerprint`, target),
  );
  const receipt: StageReceipt = {
    schema_version: "1.0",
    status: "staged",
    task_id: request.task,
    operation_id: request.operation.id,
    owner_tenant_id: request.owner.id,
    owner_root: request.owner.root,
    backend: request.backend,
    area: request.area,
    change_set_id: request.target.change_set_id,
    starting_revision: request.target.starting_revision,
    draft_revision,
    accepted_digest: request.accepted_digest,
    stage_fingerprint,
    fingerprint_verified: true,
    datasets: changes.map((change) => ({
      dataset: change.dataset,
      record_count: change.records.length,
    })),
  };
  await saveOperation(approved, {
    draft: { id: request.target.change_set_id, revision: draft_revision, status: "active", digest: request.accepted_digest },
    stage: { ...receipt, received_at: new Date().toISOString() },
    stage_attempt: { status: "verified", accepted_digest: request.accepted_digest, completed_at: new Date().toISOString() } });
  return receipt;
}
