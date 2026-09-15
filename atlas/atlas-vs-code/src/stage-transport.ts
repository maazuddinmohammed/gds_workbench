import { createHash } from "node:crypto";
import { stableStringify, UUID, SHA256, DIRECT_STAGE_MAX_BYTES, MAX_STAGE_CHUNKS,
 MAX_STAGE_CHUNK_RECORDS, METADATA_STAGE_CHUNK_MAX_BYTES, MODEL_STAGE_CHUNK_MAX_BYTES,
 ALLOWED_DATASETS, fail, isObject, hasExactKeys, requireObject, canonicalRecordsSha256,
 type StageRequest, type JsonRecord, type McpToolClient } from "./stage-contract.js";
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

export function stageTarget(request: StageRequest, scopeId: number): Record<string, unknown> {
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

export function verifyChangeSetReadResponse(
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

export function verifyStageFingerprint(
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

export async function executeStage(
  request: StageRequest,
  mcp: McpToolClient,
  target: Record<string, unknown>,
  changes: Array<{ dataset: string; records: JsonRecord[] }>,
  isCancellationRequested?: () => boolean,
  onWriteStart?: () => void | Promise<void>,
): Promise<number> {
  let writeStarted = false;
  const beginWrite = async (): Promise<void> => {
    if (writeStarted) return;
    if (isCancellationRequested?.()) {
      fail("CANCELLED", "Stage was cancelled before writing.");
    }
    await onWriteStart?.();
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
    await beginWrite();
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
    await beginWrite();
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

