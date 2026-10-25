import { createProjectTargetsApi, type ProjectTargetsTransport } from "./features/project_targets/api";
import { createMetadataEnrichmentApi, type MetadataEnrichmentTransport } from "./features/metadata_enrichment/api";
import { createProjectRecordReviewApi, type ProjectRecordEditorApi } from "./features/project_record_review/api";
import { ApiError, createHttpRequest } from "./core/http";
import {
  createAnalysisApi,
  type AnalysisTransport,
} from "./features/analysis/api";
import {
  createContextApi,
  type ContextApi,
} from "./features/context/api";
import {
  createCodeGenerationApi,
  type CodeGenerationTransport,
} from "./features/code_generation/api";
import {
  createSubjectAreaApi,
  type SubjectAreaTransport,
} from "./features/subject_areas/api";
import {
  createDimensionalApi,
  type DimensionalTransport,
} from "./features/dimensional/api";
import {
  createLogicalApi,
  type LogicalTransport,
} from "./features/logical/api";
import {
  createMappingApi,
  type MappingTransport,
} from "./features/mapping/api";
import {
  createMetadataApi,
  type MetadataApi,
} from "./features/metadata/api";
import {
  createProjectsApi,
  type ProjectsApi,
} from "./features/projects/api";
import {
  createProjectInputScopeApi,
  type ProjectInputScopeApi,
} from "./features/project_input_scope/api";
import {
  createTenantLockApi,
  type TenantLockApi,
} from "./features/tenant_locks/api";
import { createTenantsApi, type TenantsApi } from "./features/tenants/api";
import {
  createProfilingApi,
  type ProfilingTransport,
} from "./features/profiling/api";
import {
  createPromptsApi,
  type PromptsApi,
} from "./features/prompts/api";
import { createValidationApi, type ValidationTransport } from "./features/validation/api";
import {
  createWorkflowsApi,
  type WorkflowsApi,
} from "./features/workflows/api";

export { ApiError };
export { METADATA_XLSX_MEDIA_TYPE } from "./features/metadata/api";
export type {
  AnalysisEndpoint,
  AnalysisEvidence,
  AnalysisFilters,
  AnalysisFinding,
  AnalysisFindingDetail,
  AnalysisFindingPage,
  AnalysisValidationResult,
  AnalysisValidationState,
} from "./features/analysis/api";
export type {
  ContextGroup,
  ContextGroupDetail,
  ContextGroupFilters,
  ContextGroupPage,
  ContextGroupReference,
  ContextRecord,
  ContextRecordDetail,
  ContextRecordFilters,
  ContextRecordPage,
  ContextSourceSystem,
  ContextType,
} from "./features/context/api";
export type {
  CodeGenerationTarget,
  CodeGenerationTargetFilters,
  CodeGenerationTargetPage,
  CodeMappingSupport,
  GeneratedSqlArtifactDetail,
  SqlGeneratorProvenance,
  StoredSqlArtifactSummary,
} from "./features/code_generation/api";
export type {
  SaveSubjectAreaCommand,
  SaveSubjectAreaResult,
  ScopeTable,
  ScopeTablePage,
  SubjectAreaDetail,
  SubjectAreaPage,
  SubjectAreaSummary,
} from "./features/subject_areas/api";
export type {
  DimensionalContextSource,
  DimensionalAttribute,
  DimensionalAttributeContextSource,
  DimensionalAttributeDetail,
  DimensionalAttributeFilters,
  DimensionalAttributePage,
  DimensionalAttributeSource,
  DimensionalFilters,
  DimensionalObject,
  DimensionalObjectDetail,
  DimensionalObjectPage,
  DimensionalObjectSource,
  DimensionalLogicalAttributeSource,
  DimensionalLogicalEntitySource,
  DimensionalRelationship,
  DimensionalRelationshipDetail,
  DimensionalRelationshipFilters,
  DimensionalRelationshipPage,
  DimensionalSubmodelMembership,
} from "./features/dimensional/api";
export type {
  LogicalContextReference,
  LogicalContextSource,
  LogicalAttribute,
  LogicalAttributeContextSource,
  LogicalAttributeDetail,
  LogicalAttributeFilters,
  LogicalAttributePage,
  LogicalAttributePhysicalSource,
  LogicalAttributeSource,
  LogicalEntity,
  LogicalEntityDetail,
  LogicalEntityFilters,
  LogicalEntityPage,
  LogicalEntitySource,
  LogicalFilters,
  LogicalObjectSource,
  LogicalPhysicalAttributeReference,
  LogicalPhysicalObjectReference,
  LogicalRelationship,
  LogicalRelationshipDetail,
  LogicalRelationshipFilters,
  LogicalRelationshipPage,
  LogicalSubmodel,
  LogicalSubmodelDetail,
  LogicalSubmodelEntityMembership,
  LogicalSubmodelMembership,
  LogicalSubmodelPage,
} from "./features/logical/api";
export type {
  MappingAttribute,
  MappingAttributeDetail,
  MappingAttributePage,
  MappingEntityType,
  MappingFilters,
  MappingModeledAttribute,
  MappingModeledEntity,
  MappingObject,
  MappingObjectDetail,
  MappingObjectPage,
  MappingOutputTemplateProvenance,
  MappingParentObjectReference,
  MappingSourceSystem,
  MappingStatus,
  OutputTemplatePage,
  OutputTemplateSummary,
  OutputTemplateTargetType,
} from "./features/mapping/api";
export type {
  ApplyMetadataChangeSetResult,
  ArchiveMetadataChangeSetResult,
  ImportMetadataWorkbookResult,
  MetadataCellValue,
  MetadataChangeSetActionReview,
  MetadataChangeSetDatasetCount,
  MetadataChangeSetDetail,
  MetadataChangeSetStatus,
  MetadataChangeSetSummary,
  MetadataChangeSetValidationError,
  MetadataDatasetDescription,
  MetadataDatasetRegistry,
  MetadataFilters,
  MetadataRow,
  MetadataRowPage,
  MetadataSection,
  MetadataWorkbookDownload,
  StageMetadataChangeSetResult,
  ValidateMetadataChangeSetResult,
} from "./features/metadata/api";
export type {
  LedgerWorkflow,
  ProjectCollection,
  ProjectDetail,
  ProjectLedgerRecord,
  ProjectStatus,
  ProjectWorkflowOverview,
  QualityWarningCode,
  WorkflowLedgerEntry,
  WorkflowLedgerState,
} from "./features/projects/api";
export type {
  ProjectInputScopeDetail,
  ProjectInputScopeFilters,
  ProjectInputScopeObject,
  ProjectInputScopePage,
  ObjectAttribute,
  ZoneCode,
} from "./features/project_input_scope/api";
export type {
  SessionRecord,
  SystemRecord,
  TenantCollection,
  TenantHomeRecord,
  TenantRecord,
  TenantRole,
} from "./features/tenants/api";
export type {
  AttributeProfile,
  CreateProfilingRunCommand,
  ProfilingFilters,
  ProfilingObject,
  ProfilingObjectDetail,
  ProfilingObjectPage,
  ProfilingRunStart,
} from "./features/profiling/api";
export type {
  CreatePromptTemplateCommand,
  ProjectPromptAssignmentState,
  ProjectPromptAssignments,
  PromptAssignmentTarget,
  PromptOwnershipScope,
  PromptStage,
  PromptStageCatalog,
  PromptStageVariable,
  PromptTemplateDetail,
  PromptTemplateFilters,
  PromptTemplateHeader,
  PromptTemplatePage,
  PromptTemplateSummary,
  PromptTemplateVersion,
  PromptVersionStatus,
  SavePromptDraftCommand,
  SetProjectPromptAssignmentCommand,
  UpdatePromptTemplateCommand,
} from "./features/prompts/api";
export type {
  ValidationEligibleSystem,
  ValidationEligibleSystemCollection,
  ValidationLedger,
  ValidationValidationCheck,
  ValidationValidationGroup,
  ValidationValidationSeverity,
} from "./features/validation/api";
export type {
  AgentCapabilities,
  AgentRunSelection,
  CreateWorkflowRunCommand,
  ProjectWorkflow,
  WorkflowExecutionMode,
  WorkflowRunCollection,
  WorkflowRunCommandResult,
  WorkflowRunDetail,
  WorkflowRunEvent,
  WorkflowRunEventCollection,
  WorkflowRunFilterState,
  WorkflowRunRecord,
  WorkflowRunStart,
  WorkflowRunState,
} from "./features/workflows/api";
export type { JsonObject, JsonValue, ReviewStatus } from "./shared/contracts";

export interface WorkbenchApi
  extends TenantsApi,
  TenantLockApi,
  ProjectsApi,
  ProjectInputScopeApi,
  MetadataApi,
  ProjectRecordEditorApi,
  WorkflowsApi,
  ProfilingTransport,
  PromptsApi,
  AnalysisTransport,
  ContextApi,
  SubjectAreaTransport,
  LogicalTransport,
  DimensionalTransport,
  MappingTransport,
  CodeGenerationTransport,
  ValidationTransport,
  MetadataEnrichmentTransport,
  ProjectTargetsTransport {}

export function createApiClient(fetcher: typeof fetch = globalThis.fetch): WorkbenchApi {
  const request = createHttpRequest(fetcher);

  return {
    ...createTenantsApi(request),
    ...createTenantLockApi(request),
    ...createProjectsApi(request),
    ...createProjectInputScopeApi(request),
    ...createWorkflowsApi(request),
    ...createProfilingApi(request),
    ...createPromptsApi(request),
    ...createAnalysisApi(request),
    ...createContextApi(request),
    ...createSubjectAreaApi(request),
    ...createLogicalApi(request),
    ...createProjectTargetsApi(request),
    ...createDimensionalApi(request),
    ...createMappingApi(request),
    ...createCodeGenerationApi(request),
    ...createValidationApi(request),
    ...createMetadataEnrichmentApi(request),
    ...createMetadataApi(request),
    ...createProjectRecordReviewApi(request),
  };
}
