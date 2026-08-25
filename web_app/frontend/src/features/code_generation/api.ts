import type { HttpRequest } from "../../core/http";
import type {
  MappingEntityType,
  MappingModeledEntity,
  MappingPhysicalObject,
  MappingSourceSystem,
} from "../mapping/api";
import type { ModelsApi } from "../models/api";
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
  workflow_run_id: number | null;
  generated_at: string;
  generated_sql_digest: string;
  artifact_is_current: boolean;
}

export interface CodeMappingSupport {
  mapping_object_id: number;
  source: MappingModeledEntity;
  source_system: MappingSourceSystem;
  dependency_order: number;
}

export interface CodeGenerationTarget {
  target: MappingPhysicalObject;
  entity_type: MappingEntityType;
  mapping_supports: CodeMappingSupport[];
  mapping_support_count: number;
  mapping_supports_truncated: boolean;
  source_systems: MappingSourceSystem[];
  source_system_count: number;
  mapping_context_digest: string;
  source_context_digest: string;
  latest_artifact: StoredSqlArtifactSummary | null;
}

export interface CodeGenerationTargetPage {
  model_id: number;
  model_revision: number;
  items: CodeGenerationTarget[];
  next_cursor: string | null;
}

export interface SqlGenerationGuideProvenance {
  sql_generation_guide_id: number;
  sql_generation_guide_code: string;
  sql_generation_guide_name: string;
  guide_is_active: boolean;
  sql_generation_guide_version_id: number;
  sql_generation_guide_version_number: number;
  sql_generation_guide_version_status: "draft" | "published" | "retired";
  sql_generation_guide_digest: string;
}

export interface SqlGeneratorProvenance {
  generator_code: string;
  generator_version: string;
  generated_by_display_name: string;
}

export interface GeneratedSqlArtifactDetail {
  generated_sql_artifact_id: number;
  model_id: number;
  target: MappingPhysicalObject;
  entity_type: MappingEntityType;
  source_systems: MappingSourceSystem[];
  source_system_count: number;
  mapping_supports: CodeMappingSupport[];
  mapping_support_count: number;
  mapping_supports_truncated: boolean;
  artifact_is_current: boolean;
  mapping_context_digest: string;
  source_context_digest: string;
  guide: SqlGenerationGuideProvenance;
  workflow_run_id: number | null;
  generator: SqlGeneratorProvenance;
  generated_at: string;
  generated_sql: string;
  generated_sql_digest: string;
  generated_sql_byte_count: number;
}

export interface CodeGenerationTransport {
  listCodeGenerationTargets: (
    tenantId: number,
    modelId: number,
    filters?: CodeGenerationTargetFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<CodeGenerationTargetPage>;
  readGeneratedSqlArtifact: (
    tenantId: number,
    modelId: number,
    generatedSqlArtifactId: number,
  ) => Promise<GeneratedSqlArtifactDetail>;
}

export type CodeGenerationApi = CodeGenerationTransport
  & Pick<ModelsApi, "listModels">
  & Pick<
    WorkflowsApi,
    "readAgentCapabilities" | "createWorkflowRun" | "executeCodeGenerationRun"
  >;

export function createCodeGenerationApi(request: HttpRequest): CodeGenerationTransport {
  return {
    listCodeGenerationTargets: (
      tenantId,
      modelId,
      filters = {},
      pageSize = 50,
      cursor,
    ) => request<CodeGenerationTargetPage>(
      codeGenerationTargetsPath(tenantId, modelId, filters, pageSize, cursor),
    ),
    readGeneratedSqlArtifact: (tenantId, modelId, generatedSqlArtifactId) =>
      request<GeneratedSqlArtifactDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/code-generation/artifacts/${generatedSqlArtifactId}`,
      ),
  };
}

export function generatedSqlArtifactDownloadPath(
  tenantId: number,
  modelId: number,
  generatedSqlArtifactId: number,
): string {
  return `/api/v1/tenants/${tenantId}/models/${modelId}/code-generation/artifacts/${generatedSqlArtifactId}/download.sql`;
}

export const codeGenerationQueryKeys = {
  models: (tenantId: number) => ["code-generation-models", tenantId] as const,
  targets: (
    tenantId: number,
    modelId: number,
    filters: CodeGenerationTargetFilters,
    cursor: string | undefined,
  ) => ["code-generation-targets", tenantId, modelId, filters, cursor] as const,
  artifact: (tenantId: number, modelId: number, artifactId: number) => (
    ["generated-sql-artifact", tenantId, modelId, artifactId] as const
  ),
};

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}

function codeGenerationTargetsPath(
  tenantId: number,
  modelId: number,
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
  return `/api/v1/tenants/${tenantId}/models/${modelId}/code-generation/targets?${query}`;
}
