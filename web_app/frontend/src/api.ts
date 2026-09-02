import { ApiError, createHttpRequest } from "./core/http";
import {
  createAnalysisApi,
  type AnalysisTransport,
} from "./features/analysis/api";
import {
  createAssertionsApi,
  type AssertionsApi,
} from "./features/assertions/api";
import {
  createCodeGenerationApi,
  type CodeGenerationTransport,
} from "./features/code_generation/api";
import {
  createConceptualApi,
  type ConceptualTransport,
} from "./features/conceptual/api";
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
  createModelsApi,
  type ModelsApi,
} from "./features/models/api";
import {
  createModelInputScopeApi,
  type ModelInputScopeApi,
} from "./features/model_input_scope/api";
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
  ApplicableLayer,
  AssertionDocument,
  AssertionDocumentDetail,
  AssertionDocumentFilters,
  AssertionDocumentPage,
  AssertionDocumentReference,
  AssertionRecord,
  AssertionRecordDetail,
  AssertionRecordFilters,
  AssertionRecordPage,
  AssertionSourceSystem,
  AssertionSourceTenant,
} from "./features/assertions/api";
export type {
  CodeGenerationTarget,
  CodeGenerationTargetFilters,
  CodeGenerationTargetPage,
  CodeMappingSupport,
  GeneratedSqlArtifactDetail,
  SqlGenerationGuideProvenance,
  SqlGeneratorProvenance,
  StoredSqlArtifactSummary,
} from "./features/code_generation/api";
export type {
  ConceptualAssertionReference,
  ConceptualAssertionSupport,
  ConceptualCardinality,
  ConceptualConfidence,
  ConceptualFilters,
  ConceptualObject,
  ConceptualObjectDetail,
  ConceptualObjectPage,
  ConceptualPhysicalObjectReference,
  ConceptualPhysicalSupport,
  ConceptualRelationship,
  ConceptualRelationshipDetail,
  ConceptualRelationshipPage,
  ConceptualStatus,
  ConceptualSupport,
} from "./features/conceptual/api";
export type {
  DimensionalAssertionSource,
  DimensionalAttribute,
  DimensionalAttributeAssertionSource,
  DimensionalAttributeDetail,
  DimensionalAttributeFilters,
  DimensionalAttributePage,
  DimensionalAttributeSource,
  DimensionalFilters,
  DimensionalObject,
  DimensionalObjectDetail,
  DimensionalObjectPage,
  DimensionalObjectSource,
  DimensionalPhysicalAttributeSource,
  DimensionalPhysicalObjectSource,
  DimensionalRelationship,
  DimensionalRelationshipDetail,
  DimensionalRelationshipFilters,
  DimensionalRelationshipPage,
  DimensionalSubmodelMembership,
} from "./features/dimensional/api";
export type {
  LogicalAssertionReference,
  LogicalAssertionSource,
  LogicalAttribute,
  LogicalAttributeAssertionSource,
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
  MappingDependency,
  MappingDependencyPage,
  MappingEntityType,
  MappingFilters,
  MappingModeledAttribute,
  MappingModeledEntity,
  MappingObject,
  MappingObjectDetail,
  MappingObjectPage,
  MappingOutputTemplateProvenance,
  MappingParentObjectReference,
  MappingPhysicalAttribute,
  MappingPhysicalObject,
  MappingSourceSystem,
  MappingStatus,
  MappingTarget,
  MappingTargetPage,
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
  MetadataDatasetDetail,
  MetadataDatasetRegistry,
  MetadataFilters,
  MetadataJsonSchemaProperty,
  MetadataRow,
  MetadataRowPage,
  MetadataRowSchema,
  MetadataSection,
  MetadataWorkbookDownload,
  StageMetadataChangeSetCommand,
  StageMetadataChangeSetResult,
  ValidateMetadataChangeSetResult,
} from "./features/metadata/api";
export type {
  LedgerWorkflow,
  ModelCollection,
  ModelDetail,
  ModelLedgerRecord,
  ModelStatus,
  ModelWorkflowOverview,
  QualityWarningCode,
  WorkflowLedgerEntry,
  WorkflowLedgerState,
} from "./features/models/api";
export type {
  ModelInputScopeDetail,
  ModelInputScopeFilters,
  ModelInputScopeObject,
  ModelInputScopePage,
  ObjectAttribute,
  ZoneCode,
} from "./features/model_input_scope/api";
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
  ModelPromptAssignmentState,
  ModelPromptAssignments,
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
  SetModelPromptAssignmentCommand,
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
  ModelWorkflow,
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
  ModelsApi,
  ModelInputScopeApi,
  MetadataApi,
  WorkflowsApi,
  ProfilingTransport,
  PromptsApi,
  AnalysisTransport,
  AssertionsApi,
  ConceptualTransport,
  LogicalTransport,
  DimensionalTransport,
  MappingTransport,
  CodeGenerationTransport,
  ValidationTransport {}

export function createApiClient(fetcher: typeof fetch = globalThis.fetch): WorkbenchApi {
  const request = createHttpRequest(fetcher);

  return {
    ...createTenantsApi(request),
    ...createTenantLockApi(request),
    ...createModelsApi(request),
    ...createModelInputScopeApi(request),
    ...createWorkflowsApi(request),
    ...createProfilingApi(request),
    ...createPromptsApi(request),
    ...createAnalysisApi(request),
    ...createAssertionsApi(request),
    ...createConceptualApi(request),
    ...createLogicalApi(request),
    ...createDimensionalApi(request),
    ...createMappingApi(request),
    ...createCodeGenerationApi(request),
    ...createValidationApi(request),
    ...createMetadataApi(request),
  };
}
