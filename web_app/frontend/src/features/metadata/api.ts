import { ApiError, type HttpRequest } from "../../core/http";

export type MetadataSection = "reference" | "foundational" | "operational";
export type MetadataCellValue = string | number | boolean | null;
export type MetadataRow = Record<string, MetadataCellValue>;
export type MetadataFilters = Record<string, MetadataCellValue>;
export const METADATA_XLSX_MEDIA_TYPE =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export interface MetadataDatasetDescription {
  dataset: string;
  label: string;
  section: MetadataSection;
  change_set_eligible: boolean;
  read_only: boolean;
  columns: string[];
  natural_key: string[];
  filter_fields: string[];
}

export interface MetadataDatasetRegistry {
  schema_version: "1.0";
  tenant_id: number;
  datasets: MetadataDatasetDescription[];
}

export interface MetadataJsonSchemaProperty {
  title?: string;
  type?: "string" | "integer" | "number" | "boolean" | "null";
  format?: string;
  enum?: MetadataCellValue[];
  anyOf?: MetadataJsonSchemaProperty[];
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
}

export interface MetadataRowSchema {
  title?: string;
  type?: "object";
  additionalProperties?: boolean;
  properties: Record<string, MetadataJsonSchemaProperty>;
  required?: string[];
}

export interface MetadataDatasetDetail extends MetadataDatasetDescription {
  schema_version: "1.0";
  tenant_id: number;
  row_schema: MetadataRowSchema;
  fixed_values: MetadataRow;
}

export interface MetadataRowPage {
  schema_version: "1.0";
  tenant_id: number;
  dataset: string;
  items: MetadataRow[];
  next_cursor: string | null;
}

export interface MetadataWorkbookDownload {
  blob: Blob;
  filename: string;
  sheetCount: number | null;
}

export type MetadataChangeSetStatus =
  | "active"
  | "validated"
  | "applied"
  | "expired"
  | "archived"
  | "superseded";

export interface MetadataChangeSetDatasetCount {
  dataset: string;
  record_count: number;
}

export interface MetadataChangeSetSummary {
  schema_version: "1.0";
  tenant_id: number;
  metadata_change_set_id: string;
  created: boolean;
  status: "active" | "validated";
  draft_revision: number;
  created_at: string;
  expires_at: string;
}

export interface MetadataChangeSetDetail {
  schema_version: "1.0";
  tenant_id: number;
  metadata_change_set_id: string;
  status: MetadataChangeSetStatus;
  draft_revision: number;
  candidate_digest: string | null;
  validation_outcome: Record<string, unknown> | null;
  dataset_counts: MetadataChangeSetDatasetCount[];
  dataset: string | null;
  records: MetadataRow[] | null;
  created_at: string;
  last_activity_at: string;
  expires_at: string;
  validated_at: string | null;
  applied_at: string | null;
  terminal_at: string | null;
}

export interface StageMetadataChangeSetCommand {
  schema_version: "1.0";
  expected_draft_revision: number;
  changes: Array<{ dataset: string; records: MetadataRow[] }>;
}

export interface StageMetadataChangeSetResult {
  schema_version: "1.0";
  tenant_id: number;
  metadata_change_set_id: string;
  staged: true;
  datasets: MetadataChangeSetDatasetCount[];
  draft_revision: number;
  status: "active";
  expires_at: string;
}

export interface MetadataChangeSetValidationError {
  code: string;
  dataset: string;
  record_number: number | null;
  fields: string[];
  message: string;
}

export interface MetadataChangeSetActionReview {
  dataset: string;
  insert_count: number;
  update_count: number;
  deactivate_count: number;
  reactivate_count: number;
  no_change_count: number;
  keys: Array<{
    action: "insert" | "update" | "deactivate" | "reactivate" | "no_change";
    natural_key: MetadataRow;
  }>;
  keys_truncated: boolean;
}

export interface ValidateMetadataChangeSetResult {
  schema_version: "1.0";
  tenant_id: number;
  metadata_change_set_id: string;
  valid: boolean;
  phase: string;
  status: "active" | "validated";
  draft_revision: number;
  candidate_digest: string | null;
  staged_record_count: number;
  error_count: number;
  errors: MetadataChangeSetValidationError[];
  action_review: MetadataChangeSetActionReview[];
  validated_at: string | null;
  expires_at: string;
}

export interface ApplyMetadataChangeSetResult {
  schema_version: "1.0";
  tenant_id: number;
  metadata_change_set_id: string;
  valid: boolean;
  applied: boolean;
  phase: string;
  status: "active" | "applied";
  draft_revision: number;
  candidate_digest: string | null;
  staged_record_count: number;
  action_count: number;
  error_count: number;
  errors: MetadataChangeSetValidationError[];
  action_review: MetadataChangeSetActionReview[];
  applied_at: string | null;
}

export interface ArchiveMetadataChangeSetResult {
  schema_version: "1.0";
  tenant_id: number;
  metadata_change_set_id: string;
  archived: true;
  status: "archived";
  draft_revision: number;
  archived_at: string;
}

export interface ImportMetadataWorkbookResult {
  schema_version: "1.0";
  tenant_id: number;
  metadata_change_set_id: string;
  imported_sheet_count: number;
  staged: StageMetadataChangeSetResult;
  validation: ValidateMetadataChangeSetResult;
}

export interface MetadataApi {
  listMetadataDatasets: (tenantId: number) => Promise<MetadataDatasetRegistry>;
  describeMetadataDataset: (
    tenantId: number,
    dataset: string,
  ) => Promise<MetadataDatasetDetail>;
  listMetadataRows: (
    tenantId: number,
    dataset: string,
    filters?: MetadataFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<MetadataRowPage>;
  exportMetadataWorkbook: (
    tenantId: number,
    sheetCodes: "all" | string[],
  ) => Promise<MetadataWorkbookDownload>;
  createMetadataChangeSet: (
    tenantId: number,
    idempotencyKey: string,
  ) => Promise<MetadataChangeSetSummary>;
  readMetadataChangeSet: (
    tenantId: number,
    changeSetId: string,
    dataset?: string,
  ) => Promise<MetadataChangeSetDetail>;
  stageMetadataChangeSet: (
    tenantId: number,
    changeSetId: string,
    command: StageMetadataChangeSetCommand,
    idempotencyKey: string,
  ) => Promise<StageMetadataChangeSetResult>;
  validateMetadataChangeSet: (
    tenantId: number,
    changeSetId: string,
    expectedDraftRevision: number,
  ) => Promise<ValidateMetadataChangeSetResult>;
  applyMetadataChangeSet: (
    tenantId: number,
    changeSetId: string,
    expectedDraftRevision: number,
    idempotencyKey: string,
  ) => Promise<ApplyMetadataChangeSetResult>;
  archiveMetadataChangeSet: (
    tenantId: number,
    changeSetId: string,
    expectedDraftRevision: number,
    idempotencyKey: string,
  ) => Promise<ArchiveMetadataChangeSetResult>;
  importMetadataWorkbook: (
    tenantId: number,
    changeSetId: string,
    expectedDraftRevision: number,
    file: Blob,
    idempotencyKey: string,
  ) => Promise<ImportMetadataWorkbookResult>;
}

export function createMetadataApi(request: HttpRequest): MetadataApi {
  return {
    listMetadataDatasets: (tenantId) =>
      request<MetadataDatasetRegistry>(`/api/v1/tenants/${tenantId}/metadata/datasets`),
    describeMetadataDataset: (tenantId, dataset) =>
      request<MetadataDatasetDetail>(
        `/api/v1/tenants/${tenantId}/metadata/datasets/${encodeURIComponent(dataset)}`,
      ),
    listMetadataRows: (tenantId, dataset, filters = {}, pageSize = 50, cursor) => {
      const query = new URLSearchParams();
      const normalizedFilters = Object.fromEntries(
        Object.entries(filters).sort(([left], [right]) => left.localeCompare(right)),
      );
      if (Object.keys(normalizedFilters).length > 0) {
        query.set("filters", JSON.stringify(normalizedFilters));
      }
      query.set("page_size", String(pageSize));
      if (cursor) query.set("cursor", cursor);
      return request<MetadataRowPage>(
        `/api/v1/tenants/${tenantId}/metadata/datasets/${encodeURIComponent(dataset)}/rows?${query}`,
      );
    },
    exportMetadataWorkbook: (tenantId, sheetCodes) =>
      request<MetadataWorkbookDownload>(
        `/api/v1/tenants/${tenantId}/metadata/exports/xlsx`,
        {
          method: "POST",
          headers: {
            accept: METADATA_XLSX_MEDIA_TYPE,
            "content-type": "application/json",
          },
          body: JSON.stringify({ schema_version: "1.0", sheet_codes: sheetCodes }),
        },
        async (response) => {
          if (response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase()
            !== METADATA_XLSX_MEDIA_TYPE) {
            throw new ApiError(502, "invalid_response", null);
          }
          const disposition = response.headers.get("content-disposition") ?? "";
          const filenameMatch = /(?:^|;)\s*filename="([A-Za-z0-9._-]{1,180}\.xlsx)"\s*(?:;|$)/i.exec(
            disposition,
          );
          const rawSheetCount = response.headers.get("x-gds-sheet-count");
          const sheetCount = rawSheetCount && /^(?:[1-9]|1[0-6])$/.test(rawSheetCount)
            ? Number(rawSheetCount)
            : null;
          return {
            blob: await response.blob(),
            filename: filenameMatch?.[1]
              ?? `gds_operational_metadata__tenant_${tenantId}.xlsx`,
            sheetCount,
          };
        },
      ),
    createMetadataChangeSet: (tenantId, idempotencyKey) =>
      request<MetadataChangeSetSummary>(
        `/api/v1/tenants/${tenantId}/metadata-change-sets`,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify({ schema_version: "1.0" }),
        },
      ),
    readMetadataChangeSet: (tenantId, changeSetId, dataset) => {
      const query = new URLSearchParams();
      if (dataset) query.set("dataset", dataset);
      const suffix = query.size ? `?${query}` : "";
      return request<MetadataChangeSetDetail>(
        `/api/v1/tenants/${tenantId}/metadata-change-sets/${changeSetId}${suffix}`,
      );
    },
    stageMetadataChangeSet: (
      tenantId,
      changeSetId,
      command,
      idempotencyKey,
    ) => request<StageMetadataChangeSetResult>(
      `/api/v1/tenants/${tenantId}/metadata-change-sets/${changeSetId}/stage`,
      {
        method: "PUT",
        headers: {
          "content-type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify(command),
      },
    ),
    validateMetadataChangeSet: (tenantId, changeSetId, expectedDraftRevision) =>
      request<ValidateMetadataChangeSetResult>(
        `/api/v1/tenants/${tenantId}/metadata-change-sets/${changeSetId}/validate`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            schema_version: "1.0",
            expected_draft_revision: expectedDraftRevision,
          }),
        },
      ),
    applyMetadataChangeSet: (
      tenantId,
      changeSetId,
      expectedDraftRevision,
      idempotencyKey,
    ) => request<ApplyMetadataChangeSetResult>(
      `/api/v1/tenants/${tenantId}/metadata-change-sets/${changeSetId}/apply`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({
          schema_version: "1.0",
          expected_draft_revision: expectedDraftRevision,
        }),
      },
    ),
    archiveMetadataChangeSet: (
      tenantId,
      changeSetId,
      expectedDraftRevision,
      idempotencyKey,
    ) => request<ArchiveMetadataChangeSetResult>(
      `/api/v1/tenants/${tenantId}/metadata-change-sets/${changeSetId}/archive`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({
          schema_version: "1.0",
          expected_draft_revision: expectedDraftRevision,
        }),
      },
    ),
    importMetadataWorkbook: (
      tenantId,
      changeSetId,
      expectedDraftRevision,
      file,
      idempotencyKey,
    ) => request<ImportMetadataWorkbookResult>(
      `/api/v1/tenants/${tenantId}/metadata-change-sets/${changeSetId}/imports/xlsx`,
      {
        method: "POST",
        headers: {
          accept: "application/json",
          "content-type": METADATA_XLSX_MEDIA_TYPE,
          "If-Match": String(expectedDraftRevision),
          "Idempotency-Key": idempotencyKey,
        },
        body: file,
      },
    ),
  };
}

export const metadataQueryKeys = {
  registry: (tenantId: number) => ["metadata-registry", tenantId] as const,
  dataset: (tenantId: number, dataset: string) => (
    ["metadata-dataset", tenantId, dataset] as const
  ),
  rows: (
    tenantId: number,
    dataset: string,
    filters: MetadataFilters,
    cursor: string | undefined,
  ) => ["metadata-rows", tenantId, dataset, filters, cursor] as const,
  changeSet: (tenantId: number, changeSetId: string, dataset: string | undefined) => (
    ["metadata-change-set", tenantId, changeSetId, dataset] as const
  ),
};

export function metadataFieldLabel(field: string): string {
  const domainLabels: Record<string, string> = {
    scope_tenant_code: "Assigned Tenant",
    connection_tenant_code: "GDS Connection Owner",
  };
  if (domainLabels[field]) return domainLabels[field];
  return field
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function metadataValueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function metadataRowKey(row: MetadataRow, naturalKey: string[]): string {
  return JSON.stringify(naturalKey.map((field) => row[field] ?? null));
}

export function metadataPropertySchema(
  property: MetadataJsonSchemaProperty,
): MetadataJsonSchemaProperty {
  return property.anyOf?.find((option) => option.type !== "null") ?? property;
}

export function metadataPropertyIsNullable(property: MetadataJsonSchemaProperty): boolean {
  return property.type === "null" || Boolean(
    property.anyOf?.some((option) => option.type === "null"),
  );
}

export function mergeStagedRecord(
  stagedRecords: MetadataRow[],
  record: MetadataRow,
  naturalKey: string[],
  previousKey?: string,
): MetadataRow[] {
  const matchKey = previousKey ?? metadataRowKey(record, naturalKey);
  const next = stagedRecords.filter((candidate) => (
    metadataRowKey(candidate, naturalKey) !== matchKey
  ));
  next.push(record);
  return next;
}

export interface MetadataValidationReview {
  valid: boolean;
  phase: string;
  staged_record_count: number;
  error_count: number;
  errors: MetadataChangeSetValidationError[];
  action_review: MetadataChangeSetActionReview[];
}

export function validationReviewFromResult(
  result: ValidateMetadataChangeSetResult,
): MetadataValidationReview {
  return result;
}

export function validationReviewFromOutcome(
  outcome: Record<string, unknown> | null,
): MetadataValidationReview | null {
  if (!outcome || typeof outcome.valid !== "boolean" || typeof outcome.phase !== "string") {
    return null;
  }
  if (
    typeof outcome.staged_record_count !== "number"
    || typeof outcome.error_count !== "number"
    || !Array.isArray(outcome.errors)
    || !Array.isArray(outcome.action_review)
  ) {
    return null;
  }
  return outcome as unknown as MetadataValidationReview;
}
