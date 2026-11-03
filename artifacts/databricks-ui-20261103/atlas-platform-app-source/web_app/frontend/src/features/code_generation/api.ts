import type { ProjectRecordHistoryApi } from "../project_record_review/api";
import type { HttpRequest } from "../../core/http";
import { readArchiveDownload, type ArchiveDownload, type LayerArchiveRequest } from "../../shared/archiveDownload";
import type {
  MappingEntityType,
  MappingModeledEntity,
  MappingSourceSystem,
} from "../mapping/api";
import type { ProjectsApi } from "../projects/api";
import type { WorkflowsApi } from "../workflows/api";

export interface CodeGenerationTargetFilters {
  entityType?: MappingEntityType;
  systemId?: number;
  systemCode?: string;
  sourceSystemId?: number;
  sourceSystemCode?: string;
}

export interface StoredSqlArtifactSummary {
  generated_sql_artifact_id: number;
  artifact_name: string;
  workflow_run_id: number | null;
  generated_at: string;
  generated_code_status: "active" | "inactive" | "deprecated";
  generated_code_is_locked: boolean;
  source_system_codes: string[];
  artifact_is_current: boolean;
}

export interface CodeMappingSupport {
  mapping_object_id: number;
  source: MappingModeledEntity;
  source_system: MappingSourceSystem;
  dependency_order: number;
  object_transformation_missing?: boolean;
  unmapped_attribute_count?: number;
  unmapped_attribute_names?: string[];
}

export interface CodeGenerationTarget {
  is_locked: boolean;
  target: MappingModeledEntity;
  entity_type: MappingEntityType;
  mapping_supports: CodeMappingSupport[];
  mapping_support_count: number;
  mapping_supports_truncated: boolean;
  source_systems: MappingSourceSystem[];
  source_system_count: number;
  artifacts: StoredSqlArtifactSummary[];
  artifact_count: number;
}

export interface CodeGenerationTargetPage {
  project_id: number;
  project_revision: number;
  items: CodeGenerationTarget[];
  next_cursor: string | null;
}

export interface SqlGeneratorProvenance {
  generator_code: string;
  generator_version: string;
  generated_by_display_name: string;
}

export interface GeneratedSqlArtifactDetail {
  generated_sql_artifact_id: number;
  artifact_name: string;
  project_id: number;
  target: MappingModeledEntity;
  entity_type: MappingEntityType;
  source_systems: MappingSourceSystem[];
  source_system_count: number;
  mapping_supports: CodeMappingSupport[];
  mapping_support_count: number;
  mapping_supports_truncated: boolean;
  artifact_is_current: boolean;
  generated_code_status: "active" | "inactive" | "deprecated";
  generated_code_is_locked: boolean;
  workflow_run_id: number | null;
  generator: SqlGeneratorProvenance | null;
  generated_at: string;
  generated_sql: string;
  generated_sql_byte_count: number;
}

export interface CodeGenerationTransport {
  downloadAllGeneratedSql: (
    tenantId: number,
    projectId: number,
    command: LayerArchiveRequest,
  ) => Promise<ArchiveDownload>;
  listCodeGenerationTargets: (
    tenantId: number,
    projectId: number,
    filters?: CodeGenerationTargetFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<CodeGenerationTargetPage>;
  readGeneratedSqlArtifact: (
    tenantId: number,
    projectId: number,
    generatedSqlArtifactId: number,
  ) => Promise<GeneratedSqlArtifactDetail>;
}

export type CodeGenerationApi = CodeGenerationTransport & ProjectRecordHistoryApi
  & Pick<ProjectsApi, "listProjects">
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
  | "cancelWorkflowRun"
    | "createWorkflowRun"
    | "executeCodeGenerationRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >;

export function createCodeGenerationApi(request: HttpRequest): CodeGenerationTransport {
  return {
    downloadAllGeneratedSql: (tenantId, projectId, command) => request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/code-generation/downloads/all.zip`,
      { method: "POST", headers: { accept: "application/zip", "content-type": "application/json" }, body: JSON.stringify(command) },
      readArchiveDownload,
    ),
    listCodeGenerationTargets: (
      tenantId,
      projectId,
      filters = {},
      pageSize = 50,
      cursor,
    ) => request<CodeGenerationTargetPage>(
      codeGenerationTargetsPath(tenantId, projectId, filters, pageSize, cursor),
    ),
    readGeneratedSqlArtifact: (tenantId, projectId, generatedSqlArtifactId) =>
      request<GeneratedSqlArtifactDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/code-generation/artifacts/${generatedSqlArtifactId}`,
      ),
  };
}

export function generatedSqlArtifactDownloadPath(
  tenantId: number,
  projectId: number,
  generatedSqlArtifactId: number,
): string {
  return `/api/v1/tenants/${tenantId}/projects/${projectId}/code-generation/artifacts/${generatedSqlArtifactId}/download.sql`;
}

export const codeGenerationQueryKeys = {
  targets: (
    tenantId: number,
    projectId: number,
    filters: CodeGenerationTargetFilters,
    cursor: string | undefined,
  ) => ["code-generation-targets", tenantId, projectId, filters, cursor] as const,
  artifact: (tenantId: number, projectId: number, artifactId: number) => (
    ["generated-sql-artifact", tenantId, projectId, artifactId] as const
  ),
};

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}

function codeGenerationTargetsPath(
  tenantId: number,
  projectId: number,
  filters: CodeGenerationTargetFilters,
  pageSize: number,
  cursor: string | undefined,
): string {
  const query = new URLSearchParams();
  if (filters.entityType) query.set("entity_type", filters.entityType);
  if (filters.systemId) query.set("system_id", String(filters.systemId));
  if (filters.sourceSystemId) query.set("source_system_id", String(filters.sourceSystemId));
  const systemCode = normalizeNaturalKeyFilter(filters.systemCode);
  const sourceSystemCode = normalizeNaturalKeyFilter(filters.sourceSystemCode);
  if (systemCode) query.set("system_code", systemCode);
  if (sourceSystemCode) query.set("source_system_code", sourceSystemCode);
  query.set("page_size", String(pageSize));
  if (cursor) query.set("cursor", cursor);
  return `/api/v1/tenants/${tenantId}/projects/${projectId}/code-generation/targets?${query}`;
}

export async function loadCodeGenerationTargets(api: CodeGenerationApi, tenantId: number, projectId: number, entityType: MappingEntityType): Promise<CodeGenerationTargetPage> {
  const items: CodeGenerationTarget[] = [];
  const cursors = new Set<string>();
  let cursor: string | undefined;
  let revision: number | undefined;
  do {
    const page = await api.listCodeGenerationTargets(tenantId, projectId, { entityType }, 200, cursor);
    if (revision !== undefined && revision !== page.project_revision) throw new Error("The Project changed while loading Objects.");
    revision = page.project_revision;
    items.push(...page.items);
    cursor = page.next_cursor ?? undefined;
    if (cursor && cursors.has(cursor)) throw new Error("Object pagination did not advance.");
    if (cursor) cursors.add(cursor);
  } while (cursor);
  return { project_id: projectId, project_revision: revision!, items, next_cursor: null };
}
