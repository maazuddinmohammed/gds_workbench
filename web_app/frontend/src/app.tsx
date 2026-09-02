import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import {
  Link,
  Outlet,
  RouterProvider,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  useNavigate,
  type RouterHistory,
} from "@tanstack/react-router";

import type { WorkbenchApi } from "./api";
import { validateProfilingRouteSearch } from "./features/profiling/api";
import { ProfilingObjectDetailPage } from "./features/profiling/ProfilingDetail";
import { ProfilingScreen } from "./features/profiling/ProfilingScreen";
import { AnalysisDetail } from "./features/analysis/AnalysisDetail";
import { AnalysisScreen } from "./features/analysis/AnalysisScreen";
import {
  AssertionDocumentDetailPage,
  AssertionRecordDetailPage,
} from "./features/assertions/AssertionDetail";
import { AssertionsScreen } from "./features/assertions/AssertionsScreen";
import {
  ConceptualObjectDetailPage,
  ConceptualRelationshipDetailPage,
} from "./features/conceptual/ConceptualDetail";
import { ConceptualScreen } from "./features/conceptual/ConceptualScreen";
import {
  LogicalAttributeDetailPage,
  LogicalEntityDetailPage,
  LogicalRelationshipDetailPage,
  LogicalSubmodelDetailPage,
} from "./features/logical/LogicalDetail";
import { LogicalScreen } from "./features/logical/LogicalScreen";
import {
  DimensionalAttributeDetailPage,
  DimensionalObjectDetailPage,
  DimensionalRelationshipDetailPage,
} from "./features/dimensional/DimensionalDetail";
import { DimensionalScreen } from "./features/dimensional/DimensionalScreen";
import { MappingModels } from "./features/mapping/MappingModels";
import { MappingScreen } from "./features/mapping/MappingScreen";
import {
  MappingAttributeDetailPage,
  MappingObjectDetailPage,
} from "./features/mapping/MappingDetail";
import { CodeGenerationModels } from "./features/code_generation/CodeGenerationModels";
import { CodeGenerationScreen } from "./features/code_generation/CodeGenerationScreen";
import { GeneratedSqlDetailPage } from "./features/code_generation/GeneratedSqlDetail";
import { ValidationModels } from "./features/validation/ValidationModels";
import { ValidationScreen } from "./features/validation/ValidationScreen";
import { ModelPromptSettings } from "./features/prompts/ModelPromptSettings";
import { PromptsScreen } from "./features/prompts/PromptsScreen";
import { PromptTemplateDetailPage } from "./features/prompts/PromptTemplateDetail";
import { MetadataScreen } from "./features/metadata/MetadataScreen";
import { TenantEntryScreen } from "./features/tenants/TenantEntryScreen";
import { TenantHomeScreen } from "./features/tenants/TenantHomeScreen";
import { ModelsLedgerScreen } from "./features/models/ModelsLedgerScreen";
import { ModelOverviewScreen } from "./features/models/ModelOverviewScreen";
import { ModelRouteFrame } from "./features/models/ModelRouteFrame";
import { ModelInputScopeScreen } from "./features/model_input_scope/ModelInputScopeScreen";
import { TenantRouteFrame } from "./app/TenantRouteFrame";
import { WorkspaceModelRouteFrame } from "./app/WorkspaceModelRouteFrame";
import { canAuthorModels } from "./features/tenants/presentation";
import {
  ErrorPage,
} from "./shared/ui";

interface RouterContext {
  api: WorkbenchApi;
  queryClient: QueryClient;
}

interface MappingRouteSearch {
  view?: "dependencies" | "objects" | "attributes";
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
  notFoundComponent: () => (
    <main className="message-page">
      <p className="eyebrow">GDS Workbench</p>
      <h1>Page not found</h1>
      <Link className="button button-primary" to="/">
        Choose a Tenant
      </Link>
    </main>
  ),
});

const tenantEntryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: TenantEntry,
});

const tenantHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId",
  component: TenantHome,
});

const tenantMetadataRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/metadata",
  component: TenantMetadata,
});

const tenantModelsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models",
  component: ModelsLedger,
});

const tenantMappingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/mapping",
  component: TenantMapping,
});

const tenantMappingModelRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/mapping/models/$modelId",
  component: TenantMappingModel,
  validateSearch: (search: Record<string, unknown>): MappingRouteSearch => (
    search.view === "objects" || search.view === "attributes" || search.view === "dependencies"
      ? { view: search.view }
      : {}
  ),
});

const tenantMappingObjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/mapping/models/$modelId/objects/$mappingObjectId",
  component: TenantMappingObject,
});

const tenantMappingAttributeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/mapping/models/$modelId/attributes/$mappingAttributeId",
  component: TenantMappingAttribute,
});

const tenantCodeGenerationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/code-generation",
  component: TenantCodeGeneration,
});

const tenantCodeGenerationModelRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/code-generation/models/$modelId",
  component: TenantCodeGenerationModel,
});

const tenantGeneratedSqlArtifactRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/code-generation/models/$modelId/artifacts/$artifactId",
  component: TenantGeneratedSqlArtifact,
});

const tenantValidationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/validation",
  component: TenantValidation,
});

const tenantValidationModelRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/validation/models/$modelId",
  component: TenantValidationModel,
});

const tenantPromptsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/prompts",
  component: TenantPrompts,
});

const tenantPromptTemplateRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/prompts/templates/$promptTemplateId",
  component: TenantPromptTemplate,
});

const tenantModelPromptSettingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/settings/prompts",
  component: TenantModelPromptSettings,
});

const tenantModelRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId",
  component: ModelOverview,
});

const tenantModelInputScopeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/input-scope",
  component: ModelInputScope,
});

const tenantModelProfilingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/profiling",
  validateSearch: validateProfilingRouteSearch,
  component: ModelProfiling,
});

const tenantModelProfilingDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/profiling/$objectId",
  validateSearch: validateProfilingRouteSearch,
  component: ModelProfilingDetail,
});

const tenantModelAnalysisRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/analysis",
  component: ModelAnalysis,
});

const tenantModelAnalysisDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/analysis/$findingId",
  component: ModelAnalysisDetail,
});

const tenantModelAssertionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/assertions",
  component: ModelAssertions,
});

const tenantModelAssertionDocumentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/assertions/documents/$documentId",
  component: ModelAssertionDocument,
});

const tenantModelAssertionRecordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/assertions/records/$recordId",
  component: ModelAssertionRecord,
});

const tenantModelConceptualRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/conceptual",
  component: ModelConceptual,
});

const tenantModelConceptualObjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/conceptual/objects/$objectId",
  component: ModelConceptualObject,
});

const tenantModelConceptualRelationshipRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/conceptual/relationships/$relationshipId",
  component: ModelConceptualRelationship,
});

const tenantModelLogicalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/logical",
  component: ModelLogical,
});

const tenantModelLogicalEntityRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/logical/entities/$entityId",
  component: ModelLogicalEntity,
});

const tenantModelLogicalAttributeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/logical/attributes/$attributeId",
  component: ModelLogicalAttribute,
});

const tenantModelLogicalRelationshipRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/logical/relationships/$relationshipId",
  component: ModelLogicalRelationship,
});

const tenantModelLogicalSubmodelRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/logical/submodels/$submodelId",
  component: ModelLogicalSubmodel,
});

const tenantModelDimensionalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/dimensional",
  component: ModelDimensional,
});

const tenantModelDimensionalObjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/dimensional/objects/$entityId",
  component: ModelDimensionalObject,
});

const tenantModelDimensionalAttributeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/dimensional/attributes/$attributeId",
  component: ModelDimensionalAttribute,
});

const tenantModelDimensionalRelationshipRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/models/$modelId/dimensional/relationships/$relationshipId",
  component: ModelDimensionalRelationship,
});

const routeTree = rootRoute.addChildren([
  tenantEntryRoute,
  tenantHomeRoute,
  tenantMetadataRoute,
  tenantModelsRoute,
  tenantMappingRoute,
  tenantMappingModelRoute,
  tenantMappingObjectRoute,
  tenantMappingAttributeRoute,
  tenantCodeGenerationRoute,
  tenantCodeGenerationModelRoute,
  tenantGeneratedSqlArtifactRoute,
  tenantValidationRoute,
  tenantValidationModelRoute,
  tenantPromptsRoute,
  tenantPromptTemplateRoute,
  tenantModelPromptSettingsRoute,
  tenantModelRoute,
  tenantModelInputScopeRoute,
  tenantModelProfilingRoute,
  tenantModelProfilingDetailRoute,
  tenantModelAnalysisRoute,
  tenantModelAnalysisDetailRoute,
  tenantModelAssertionsRoute,
  tenantModelAssertionDocumentRoute,
  tenantModelAssertionRecordRoute,
  tenantModelConceptualRoute,
  tenantModelConceptualObjectRoute,
  tenantModelConceptualRelationshipRoute,
  tenantModelLogicalRoute,
  tenantModelLogicalEntityRoute,
  tenantModelLogicalAttributeRoute,
  tenantModelLogicalRelationshipRoute,
  tenantModelLogicalSubmodelRoute,
  tenantModelDimensionalRoute,
  tenantModelDimensionalObjectRoute,
  tenantModelDimensionalAttributeRoute,
  tenantModelDimensionalRelationshipRoute,
]);

export function createWorkbenchRouter(options: {
  api: WorkbenchApi;
  history?: RouterHistory;
}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });

  return createRouter({
    routeTree,
    ...(options.history ? { history: options.history } : {}),
    context: { api: options.api, queryClient },
    defaultPreload: "intent",
    defaultPendingMs: 120,
  });
}

export type WorkbenchRouter = ReturnType<typeof createWorkbenchRouter>;

declare module "@tanstack/react-router" {
  interface Register {
    router: WorkbenchRouter;
  }
}

export function WorkbenchApp({ router }: { router: WorkbenchRouter }) {
  return (
    <QueryClientProvider client={router.options.context.queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

function TenantEntry() {
  const { api } = rootRoute.useRouteContext();
  const navigate = useNavigate({ from: "/" });
  return (
    <TenantEntryScreen
      api={api}
      onTenantEntered={async (tenantId) => {
        await navigate({
          to: "/tenants/$tenantId",
          params: { tenantId: String(tenantId) },
        });
      }}
    />
  );
}

function TenantHome() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId } = tenantHomeRoute.useParams();
  return <TenantHomeScreen api={api} tenantId={Number(tenantId)} />;
}

function TenantMetadata() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId } = tenantMetadataRoute.useParams();
  const numericTenantId = Number(tenantId);
  return (
    <TenantRouteFrame
      api={api}
      tenantId={numericTenantId}
      activeNav="metadata"
      loadingLabel="Loading Metadata"
    >
      {({ home }) => (
        <MetadataScreen
          api={api}
          tenantId={numericTenantId}
          tenantName={home.tenant.tenant_name}
          tenantLock={home.lock}
          canWriteMetadata={home.tenant.effective_role !== "viewer"}
        />
      )}
    </TenantRouteFrame>
  );
}

function ModelsLedger() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId } = tenantModelsRoute.useParams();
  return <ModelsLedgerScreen api={api} tenantId={Number(tenantId)} />;
}

function TenantMapping() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId } = tenantMappingRoute.useParams();
  const numericTenantId = Number(tenantId);
  return (
    <TenantRouteFrame
      api={api}
      tenantId={numericTenantId}
      activeNav="mapping"
      loadingLabel="Loading Mapping"
    >
      {() => (
        <main className="workspace workspace-ledger">
          <MappingModels api={api} tenantId={numericTenantId} />
        </main>
      )}
    </TenantRouteFrame>
  );
}

function TenantMappingModel() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantMappingModelRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  const { view } = tenantMappingModelRoute.useSearch();
  return (
    <WorkspaceModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeNav="mapping"
      loadingLabel="Loading Mapping"
    >
      {({ home, model }) => (
        <MappingScreen
          api={api}
          tenantId={numericTenantId}
          model={model}
          hasTenantLock={home.lock.owned_by_current_principal === true}
          hasAppPermission={canAuthorModels(home.tenant.effective_role)}
          {...(view ? { initialView: view } : {})}
        />
      )}
    </WorkspaceModelRouteFrame>
  );
}

function TenantMappingObject() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, mappingObjectId } = tenantMappingObjectRoute.useParams();
  return <TenantMappingDetail
    api={api}
    tenantId={Number(tenantId)}
    modelId={Number(modelId)}
    detailId={Number(mappingObjectId)}
    kind="object"
  />;
}

function TenantMappingAttribute() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, mappingAttributeId } = tenantMappingAttributeRoute.useParams();
  return <TenantMappingDetail
    api={api}
    tenantId={Number(tenantId)}
    modelId={Number(modelId)}
    detailId={Number(mappingAttributeId)}
    kind="attribute"
  />;
}

function TenantMappingDetail({
  api,
  tenantId,
  modelId,
  detailId,
  kind,
}: {
  api: WorkbenchApi;
  tenantId: number;
  modelId: number;
  detailId: number;
  kind: "object" | "attribute";
}) {
  if (!Number.isSafeInteger(detailId) || detailId <= 0) return <ErrorPage />;
  return (
    <WorkspaceModelRouteFrame
      api={api}
      tenantId={tenantId}
      modelId={modelId}
      activeNav="mapping"
      loadingLabel="Loading Mapping"
    >
      {() => (
        <main className="workspace mapping-workspace">
          {kind === "object" ? (
            <MappingObjectDetailPage api={api} tenantId={tenantId} modelId={modelId} mappingObjectId={detailId} />
          ) : (
            <MappingAttributeDetailPage api={api} tenantId={tenantId} modelId={modelId} mappingAttributeId={detailId} />
          )}
        </main>
      )}
    </WorkspaceModelRouteFrame>
  );
}

function TenantCodeGeneration() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId } = tenantCodeGenerationRoute.useParams();
  const numericTenantId = Number(tenantId);
  return (
    <TenantRouteFrame
      api={api}
      tenantId={numericTenantId}
      activeNav="code-generation"
      loadingLabel="Loading Code Generation"
    >
      {() => (
        <main className="workspace workspace-ledger">
          <CodeGenerationModels api={api} tenantId={numericTenantId} />
        </main>
      )}
    </TenantRouteFrame>
  );
}

function TenantCodeGenerationModel() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantCodeGenerationModelRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  return (
    <WorkspaceModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeNav="code-generation"
      loadingLabel="Loading Code Generation"
    >
      {({ home, model }) => (
        <CodeGenerationScreen
          api={api}
          tenantId={numericTenantId}
          model={model}
          hasTenantLock={home.lock.owned_by_current_principal === true}
          hasAppPermission={canAuthorModels(home.tenant.effective_role)}
        />
      )}
    </WorkspaceModelRouteFrame>
  );
}

function TenantGeneratedSqlArtifact() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, artifactId } = tenantGeneratedSqlArtifactRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  const numericArtifactId = Number(artifactId);
  if (!Number.isSafeInteger(numericArtifactId) || numericArtifactId <= 0) {
    return <ErrorPage />;
  }
  return (
    <WorkspaceModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeNav="code-generation"
      loadingLabel="Loading stored SQL"
    >
      {({ home, model }) => (
        <main className="workspace mapping-workspace code-generation-workspace">
          <GeneratedSqlDetailPage
            api={api}
            tenantId={numericTenantId}
            model={model}
            artifactId={numericArtifactId}
            hasTenantLock={home.lock.owned_by_current_principal === true}
            hasAppPermission={canAuthorModels(home.tenant.effective_role)}
          />
        </main>
      )}
    </WorkspaceModelRouteFrame>
  );
}

function TenantValidation() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId } = tenantValidationRoute.useParams();
  const numericTenantId = Number(tenantId);
  return (
    <TenantRouteFrame
      api={api}
      tenantId={numericTenantId}
      activeNav="validation"
      loadingLabel="Loading Validation"
    >
      {() => (
        <main className="workspace workspace-ledger">
          <ValidationModels api={api} tenantId={numericTenantId} />
        </main>
      )}
    </TenantRouteFrame>
  );
}

function TenantValidationModel() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantValidationModelRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  return (
    <WorkspaceModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeNav="validation"
      loadingLabel="Loading Validation"
    >
      {({ home, model }) => (
        <ValidationScreen
          api={api}
          tenantId={numericTenantId}
          model={model}
          hasTenantLock={home.lock.owned_by_current_principal === true}
          hasAppPermission={canAuthorModels(home.tenant.effective_role)}
        />
      )}
    </WorkspaceModelRouteFrame>
  );
}

function TenantPrompts() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId } = tenantPromptsRoute.useParams();
  const numericTenantId = Number(tenantId);
  return (
    <TenantRouteFrame
      api={api}
      tenantId={numericTenantId}
      activeNav="prompts"
      loadingLabel="Loading Prompt Library"
    >
      {({ home }) => (
        <PromptsScreen
          api={api}
          tenantId={numericTenantId}
          tenantName={home.tenant.tenant_name}
          canAuthorPrompts={canAuthorModels(home.tenant.effective_role)}
          isSuperAdmin={home.tenant.effective_role === "super_admin"}
          hasTenantLock={home.lock.owned_by_current_principal === true}
        />
      )}
    </TenantRouteFrame>
  );
}

function TenantPromptTemplate() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, promptTemplateId } = tenantPromptTemplateRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericPromptTemplateId = Number(promptTemplateId);
  if (!Number.isSafeInteger(numericPromptTemplateId) || numericPromptTemplateId <= 0) {
    return <ErrorPage />;
  }
  return (
    <TenantRouteFrame
      api={api}
      tenantId={numericTenantId}
      activeNav="prompts"
      loadingLabel="Loading Prompt Template"
    >
      {({ home }) => (
        <PromptTemplateDetailPage
          api={api}
          tenantId={numericTenantId}
          promptTemplateId={numericPromptTemplateId}
          canAuthorPrompts={canAuthorModels(home.tenant.effective_role)}
          isSuperAdmin={home.tenant.effective_role === "super_admin"}
          hasTenantLock={home.lock.owned_by_current_principal === true}
        />
      )}
    </TenantRouteFrame>
  );
}

function TenantModelPromptSettings() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantModelPromptSettingsRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="settings-prompts"
      loadingLabel="Loading Model Prompt Settings"
    >
      {({ home, model }) => (
        <ModelPromptSettings
          api={api}
          tenantId={numericTenantId}
          model={model}
          hasTenantLock={home.lock.owned_by_current_principal === true}
          hasAppPermission={canAuthorModels(home.tenant.effective_role)}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelOverview() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantModelRoute.useParams();
  return <ModelOverviewScreen api={api} tenantId={Number(tenantId)} modelId={Number(modelId)} />;
}

function ModelInputScope() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantModelInputScopeRoute.useParams();
  return <ModelInputScopeScreen api={api} tenantId={Number(tenantId)} modelId={Number(modelId)} />;
}

function ModelProfiling() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantModelProfilingRoute.useParams();
  const { returnObjectId, ...resultFilters } = tenantModelProfilingRoute.useSearch();
  const navigate = useNavigate({ from: "/tenants/$tenantId/models/$modelId/profiling" });
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="profiling"
      loadingLabel="Loading Profiling"
    >
      {({ home, model }) => (
        <ProfilingScreen
          api={api}
          tenantId={numericTenantId}
          model={model}
          hasTenantLock={home.lock.owned_by_current_principal === true}
          resultFilters={resultFilters}
          {...(returnObjectId === undefined ? {} : { returnObjectId })}
          onApplyResultFilters={(filters) => {
            void navigate({ search: filters, replace: true });
          }}
          onReturnFocusHandled={() => navigate({ search: resultFilters, replace: true })}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelProfilingDetail() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, objectId } = tenantModelProfilingDetailRoute.useParams();
  const returnSearch = tenantModelProfilingDetailRoute.useSearch();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  const numericObjectId = Number(objectId);
  if (!Number.isSafeInteger(numericObjectId) || numericObjectId <= 0) return <ErrorPage />;
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="profiling"
      loadingLabel="Loading profile evidence"
    >
      {() => (
        <ProfilingObjectDetailPage
          api={api}
          tenantId={numericTenantId}
          modelId={numericModelId}
          objectId={numericObjectId}
          returnSearch={returnSearch}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelAnalysis() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantModelAnalysisRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="analysis"
      loadingLabel="Loading Analysis"
    >
      {({ home, model }) => (
        <AnalysisScreen
          api={api}
          tenantId={numericTenantId}
          model={model}
          hasTenantLock={home.lock.owned_by_current_principal === true}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelAnalysisDetail() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, findingId } = tenantModelAnalysisDetailRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  const numericFindingId = Number(findingId);
  if (!Number.isSafeInteger(numericFindingId) || numericFindingId <= 0) return <ErrorPage />;
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="analysis"
      loadingLabel="Loading finding"
    >
      {() => (
        <AnalysisDetail
          api={api}
          tenantId={numericTenantId}
          modelId={numericModelId}
          findingId={numericFindingId}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelAssertions() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantModelAssertionsRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="assertions"
      loadingLabel="Loading Assertions"
    >
      {({ model }) => (
        <AssertionsScreen api={api} tenantId={numericTenantId} model={model} />
      )}
    </ModelRouteFrame>
  );
}

function ModelAssertionDocument() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, documentId } = tenantModelAssertionDocumentRoute.useParams();
  return (
    <AssertionDetailRoute
      api={api}
      tenantId={Number(tenantId)}
      modelId={Number(modelId)}
      detailId={Number(documentId)}
      kind="document"
    />
  );
}

function ModelAssertionRecord() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, recordId } = tenantModelAssertionRecordRoute.useParams();
  return (
    <AssertionDetailRoute
      api={api}
      tenantId={Number(tenantId)}
      modelId={Number(modelId)}
      detailId={Number(recordId)}
      kind="record"
    />
  );
}

function AssertionDetailRoute({
  api,
  tenantId,
  modelId,
  detailId,
  kind,
}: {
  api: WorkbenchApi;
  tenantId: number;
  modelId: number;
  detailId: number;
  kind: "document" | "record";
}) {
  if (!Number.isSafeInteger(detailId) || detailId <= 0) return <ErrorPage />;
  return (
    <ModelRouteFrame
      api={api}
      tenantId={tenantId}
      modelId={modelId}
      activeStage="assertions"
      loadingLabel="Loading Assertion"
    >
      {() => (
        kind === "document" ? (
          <AssertionDocumentDetailPage
            api={api}
            tenantId={tenantId}
            modelId={modelId}
            documentId={detailId}
          />
        ) : (
          <AssertionRecordDetailPage
            api={api}
            tenantId={tenantId}
            modelId={modelId}
            recordId={detailId}
          />
        )
      )}
    </ModelRouteFrame>
  );
}

function ModelConceptual() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantModelConceptualRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="conceptual"
      loadingLabel="Loading Conceptual"
    >
      {({ home, model }) => (
        <ConceptualScreen
          api={api}
          tenantId={numericTenantId}
          model={model}
          hasTenantLock={home.lock.owned_by_current_principal === true}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelConceptualObject() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, objectId } = tenantModelConceptualObjectRoute.useParams();
  return (
    <ConceptualDetailRoute
      api={api}
      tenantId={Number(tenantId)}
      modelId={Number(modelId)}
      detailId={Number(objectId)}
      kind="object"
    />
  );
}

function ModelConceptualRelationship() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, relationshipId } = tenantModelConceptualRelationshipRoute.useParams();
  return (
    <ConceptualDetailRoute
      api={api}
      tenantId={Number(tenantId)}
      modelId={Number(modelId)}
      detailId={Number(relationshipId)}
      kind="relationship"
    />
  );
}

function ConceptualDetailRoute({
  api,
  tenantId,
  modelId,
  detailId,
  kind,
}: {
  api: WorkbenchApi;
  tenantId: number;
  modelId: number;
  detailId: number;
  kind: "object" | "relationship";
}) {
  if (!Number.isSafeInteger(detailId) || detailId <= 0) return <ErrorPage />;
  return (
    <ModelRouteFrame
      api={api}
      tenantId={tenantId}
      modelId={modelId}
      activeStage="conceptual"
      loadingLabel="Loading Conceptual"
    >
      {() => (
        kind === "object" ? (
          <ConceptualObjectDetailPage
            api={api}
            tenantId={tenantId}
            modelId={modelId}
            objectId={detailId}
          />
        ) : (
          <ConceptualRelationshipDetailPage
            api={api}
            tenantId={tenantId}
            modelId={modelId}
            relationshipId={detailId}
          />
        )
      )}
    </ModelRouteFrame>
  );
}

function ModelLogical() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantModelLogicalRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="logical"
      loadingLabel="Loading Logical"
    >
      {({ home, model }) => (
        <LogicalScreen
          api={api}
          tenantId={numericTenantId}
          model={model}
          hasTenantLock={home.lock.owned_by_current_principal === true}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelLogicalEntity() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, entityId } = tenantModelLogicalEntityRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  const numericEntityId = Number(entityId);
  if (!Number.isSafeInteger(numericEntityId) || numericEntityId <= 0) return <ErrorPage />;
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="logical"
      loadingLabel="Loading Logical"
    >
      {() => (
        <LogicalEntityDetailPage
          api={api}
          tenantId={numericTenantId}
          modelId={numericModelId}
          entityId={numericEntityId}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelLogicalAttribute() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, attributeId } = tenantModelLogicalAttributeRoute.useParams();
  return (
    <LogicalDetailRoute
      api={api}
      tenantId={Number(tenantId)}
      modelId={Number(modelId)}
      detailId={Number(attributeId)}
      kind="attribute"
    />
  );
}

function ModelLogicalRelationship() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, relationshipId } = tenantModelLogicalRelationshipRoute.useParams();
  return (
    <LogicalDetailRoute
      api={api}
      tenantId={Number(tenantId)}
      modelId={Number(modelId)}
      detailId={Number(relationshipId)}
      kind="relationship"
    />
  );
}

function ModelLogicalSubmodel() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, submodelId } = tenantModelLogicalSubmodelRoute.useParams();
  return (
    <LogicalDetailRoute
      api={api}
      tenantId={Number(tenantId)}
      modelId={Number(modelId)}
      detailId={Number(submodelId)}
      kind="submodel"
    />
  );
}

function LogicalDetailRoute({
  api,
  tenantId,
  modelId,
  detailId,
  kind,
}: {
  api: WorkbenchApi;
  tenantId: number;
  modelId: number;
  detailId: number;
  kind: "attribute" | "relationship" | "submodel";
}) {
  if (!Number.isSafeInteger(detailId) || detailId <= 0) return <ErrorPage />;
  return (
    <ModelRouteFrame
      api={api}
      tenantId={tenantId}
      modelId={modelId}
      activeStage="logical"
      loadingLabel="Loading Logical"
    >
      {() => (
        kind === "attribute" ? (
          <LogicalAttributeDetailPage
            api={api}
            tenantId={tenantId}
            modelId={modelId}
            attributeId={detailId}
          />
        ) : kind === "relationship" ? (
          <LogicalRelationshipDetailPage
            api={api}
            tenantId={tenantId}
            modelId={modelId}
            relationshipId={detailId}
          />
        ) : (
          <LogicalSubmodelDetailPage
            api={api}
            tenantId={tenantId}
            modelId={modelId}
            submodelId={detailId}
          />
        )
      )}
    </ModelRouteFrame>
  );
}

function ModelDimensional() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId } = tenantModelDimensionalRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="dimensional"
      loadingLabel="Loading Dimensional"
    >
      {({ home, model }) => (
        <DimensionalScreen
          api={api}
          tenantId={numericTenantId}
          model={model}
          hasTenantLock={home.lock.owned_by_current_principal === true}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelDimensionalObject() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, entityId } = tenantModelDimensionalObjectRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericModelId = Number(modelId);
  const numericEntityId = Number(entityId);
  if (!Number.isSafeInteger(numericEntityId) || numericEntityId <= 0) return <ErrorPage />;
  return (
    <ModelRouteFrame
      api={api}
      tenantId={numericTenantId}
      modelId={numericModelId}
      activeStage="dimensional"
      loadingLabel="Loading Dimensional"
    >
      {() => (
        <DimensionalObjectDetailPage
          api={api}
          tenantId={numericTenantId}
          modelId={numericModelId}
          entityId={numericEntityId}
        />
      )}
    </ModelRouteFrame>
  );
}

function ModelDimensionalAttribute() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, attributeId } = tenantModelDimensionalAttributeRoute.useParams();
  return <DimensionalDetailRoute
    api={api}
    tenantId={Number(tenantId)}
    modelId={Number(modelId)}
    detailId={Number(attributeId)}
    kind="attribute"
  />;
}

function ModelDimensionalRelationship() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, modelId, relationshipId } = tenantModelDimensionalRelationshipRoute.useParams();
  return <DimensionalDetailRoute
    api={api}
    tenantId={Number(tenantId)}
    modelId={Number(modelId)}
    detailId={Number(relationshipId)}
    kind="relationship"
  />;
}

function DimensionalDetailRoute({
  api,
  tenantId,
  modelId,
  detailId,
  kind,
}: {
  api: WorkbenchApi;
  tenantId: number;
  modelId: number;
  detailId: number;
  kind: "attribute" | "relationship";
}) {
  if (!Number.isSafeInteger(detailId) || detailId <= 0) return <ErrorPage />;
  return (
    <ModelRouteFrame
      api={api}
      tenantId={tenantId}
      modelId={modelId}
      activeStage="dimensional"
      loadingLabel="Loading Dimensional"
    >
      {() => (
        kind === "attribute" ? (
          <DimensionalAttributeDetailPage
            api={api}
            tenantId={tenantId}
            modelId={modelId}
            attributeId={detailId}
          />
        ) : (
          <DimensionalRelationshipDetailPage
            api={api}
            tenantId={tenantId}
            modelId={modelId}
            relationshipId={detailId}
          />
        )
      )}
    </ModelRouteFrame>
  );
}
