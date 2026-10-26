import { ProjectRecordTools } from "./features/project_record_review/ProjectRecordEditor";
import { projectLayerSearch } from "./shared/ProjectLayerTabs";
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
  redirect,
  useNavigate,
  useParams,
  useSearch,
  type RouterHistory,
} from "@tanstack/react-router";

import type { WorkbenchApi } from "./api";
import { validateProfilingRouteSearch } from "./features/profiling/api";
import { ProfilingObjectDetailPage } from "./features/profiling/ProfilingDetail";
import { ProfilingScreen } from "./features/profiling/ProfilingScreen";
import { AnalysisScreen } from "./features/analysis/AnalysisScreen";
import {
  ContextGroupDetailPage,
  ContextRecordDetailPage,
} from "./features/context/ContextDetail";
import { ContextScreen } from "./features/context/ContextScreen";
import { MetadataEnrichmentScreen } from "./features/metadata_enrichment/MetadataEnrichmentScreen";
import { SubjectAreaDetailPage } from "./features/subject_areas/SubjectAreaDetail";
import { SubjectAreasScreen } from "./features/subject_areas/SubjectAreasScreen";
import {
  LogicalAttributeDetailPage,
  LogicalEntityDetailPage,
  LogicalRelationshipDetailPage,
  LogicalSubjectAreaPage,
} from "./features/logical/LogicalDetail";
import { LogicalScreen } from "./features/logical/LogicalScreen";
import {
  DimensionalAttributeDetailPage,
  DimensionalObjectDetailPage,
  DimensionalRelationshipDetailPage,
  DimensionalSubjectAreaPage,
} from "./features/dimensional/DimensionalDetail";
import { DimensionalScreen } from "./features/dimensional/DimensionalScreen";
import { MappingScreen } from "./features/mapping/MappingScreen";
import {
  MappingAttributeDetailPage,
  MappingObjectDetailPage,
} from "./features/mapping/MappingDetail";
import { CodeGenerationScreen } from "./features/code_generation/CodeGenerationScreen";
import { GeneratedSqlDetailPage } from "./features/code_generation/GeneratedSqlDetail";
import { ValidationScreen } from "./features/validation/ValidationScreen";
import { ProjectPromptSettings } from "./features/prompts/ProjectPromptSettings";
import { PromptsScreen } from "./features/prompts/PromptsScreen";
import { PromptTemplateDetailPage } from "./features/prompts/PromptTemplateDetail";
import { MetadataScreen, type MetadataCategory } from "./features/metadata/MetadataScreen";
import { PhysicalMetadataScreen } from "./features/metadata/PhysicalMetadataScreen";
import { TenantEntryScreen } from "./features/tenants/TenantEntryScreen";
import { TenantHomeScreen } from "./features/tenants/TenantHomeScreen";
import { WorkflowProjects } from "./features/projects/WorkflowProjects";
import { ProjectsLedgerScreen } from "./features/projects/ProjectsLedgerScreen";
import { ProjectOverviewScreen } from "./features/projects/ProjectOverviewScreen";
import { ProjectSettingsScreen } from "./features/projects/ProjectSettingsScreen";
import { ProjectRouteFrame } from "./features/projects/ProjectRouteFrame";
import { ProjectInputScopeScreen } from "./features/project_input_scope/ProjectInputScopeScreen";
import { TenantRouteFrame } from "./app/TenantRouteFrame";
import { canAuthorProjects } from "./features/tenants/presentation";
import {
  ErrorPage,
} from "./shared/ui";

interface RouterContext {
  api: WorkbenchApi;
  queryClient: QueryClient;
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
  notFoundComponent: () => (
    <main className="message-page">
      <p className="eyebrow">Atlas</p>
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
  validateSearch: (search: Record<string, unknown>): { section?: MetadataCategory; objectId?: number } => {
    const section = ["reference", "foundational", "objects", "operational"].includes(String(search.section))
      ? search.section as MetadataCategory : undefined;
    const objectId = Number(search.objectId);
    return { ...(section ? { section } : {}),
      ...(section === "objects" && Number.isSafeInteger(objectId) && objectId > 0 ? { objectId } : {}) };
  },
  component: TenantMetadata,
});

const tenantMetadataObjectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/metadata/objects",
  validateSearch: (search: Record<string, unknown>): { objectId?: number } => {
    const objectId = Number(search.objectId);
    return Number.isSafeInteger(objectId) && objectId > 0 ? { objectId } : {};
  },
  component: TenantMetadataObjects,
});

const tenantProjectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects",
  component: ProjectsLedger,
});

const tenantMappingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/mapping",
  component: TenantMapping,
});

const tenantMappingProjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/mapping/projects/$projectId",
  validateSearch: projectLayerSearch,
  component: TenantMappingProject,
});

const tenantMappingObjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/mapping/projects/$projectId/objects/$mappingObjectId",
  validateSearch: projectLayerSearch,
  component: TenantMappingObject,
});

const tenantMappingAttributeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/mapping/projects/$projectId/attributes/$mappingAttributeId",
  validateSearch: projectLayerSearch,
  component: TenantMappingAttribute,
});

const tenantCodeGenerationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/code-generation",
  component: TenantCodeGeneration,
});

const tenantCodeGenerationProjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/code-generation/projects/$projectId",
  validateSearch: projectLayerSearch,
  component: TenantCodeGenerationProject,
});

const tenantGeneratedSqlArtifactRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/code-generation/projects/$projectId/artifacts/$artifactId",
  validateSearch: projectLayerSearch,
  component: TenantGeneratedSqlArtifact,
});

const tenantValidationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/validation",
  component: TenantValidation,
});

const tenantValidationProjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/validation/projects/$projectId",
  component: TenantValidationProject,
  validateSearch: projectLayerSearch,
});

const tenantValidationGroupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/validation/projects/$projectId/groups/$groupId",
  component: TenantValidationProject,
  validateSearch: projectLayerSearch,
});

const tenantValidationCheckRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/validation/projects/$projectId/groups/$groupId/checks/$checkId",
  component: TenantValidationProject,
  validateSearch: projectLayerSearch,
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

const tenantProjectSettingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/settings",
  validateSearch: projectLayerSearch,
  component: TenantProjectSettings,
});

const tenantProjectPromptSettingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/settings/prompts",
  validateSearch: projectLayerSearch,
  component: TenantProjectPromptSettings,
});

const tenantProjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId",
  validateSearch: projectLayerSearch,
  component: ProjectOverview,
});

const tenantProjectInputScopeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/input-scope",
  validateSearch: projectLayerSearch,
  component: ProjectInputScope,
});

const tenantProjectProfilingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/profiling",
  validateSearch: (search) => ({ ...validateProfilingRouteSearch(search), ...projectLayerSearch(search) }),
  component: ProjectProfiling,
});

const tenantProjectProfilingDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/profiling/$objectId",
  validateSearch: (search) => ({ ...validateProfilingRouteSearch(search), ...projectLayerSearch(search) }),
  component: ProjectProfilingDetail,
});

const tenantProjectAnalysisRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/analysis",
  validateSearch: projectLayerSearch,
  component: ProjectAnalysis,
});

const tenantProjectAnalysisDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/analysis/$findingId",
  validateSearch: projectLayerSearch,
  beforeLoad: ({ params, search }) => {
    throw redirect({
      to: "/tenants/$tenantId/projects/$projectId/analysis",
      params: { tenantId: params.tenantId, projectId: params.projectId },
      search,
      replace: true,
    });
  },
});

const tenantProjectContextRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/context",
  validateSearch: projectLayerSearch,
  component: ProjectContext,
});

const tenantProjectContextGroupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/context/groups/$groupId",
  validateSearch: projectLayerSearch,
  component: ProjectContextGroup,
});

const tenantProjectContextRecordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/context/records/$recordId",
  validateSearch: projectLayerSearch,
  component: ProjectContextRecord,
});

const tenantProjectMetadataEnrichmentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/metadata-enrichment",
  validateSearch: projectLayerSearch,
  component: ProjectMetadataEnrichment,
});

const tenantProjectSubjectAreasRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/subject-areas",
  validateSearch: projectLayerSearch,
  component: ProjectSubjectAreas,
});

const tenantProjectSubjectAreaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/subject-areas/$subjectAreaId",
  validateSearch: projectLayerSearch,
  component: ProjectSubjectArea,
});

// Logical and Dimensional open a tab by name, so a Subject Area page can link back to its tab.
type ModelView = "subject_areas" | "entities" | "relationships";
const modelViewSearch = (search: Record<string, unknown>): { view?: ModelView } => (
  search.view === "subject_areas" || search.view === "entities" || search.view === "relationships"
    ? { view: search.view } : {}
);

const tenantProjectLogicalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/logical",
  validateSearch: modelViewSearch,
  component: ProjectLogical,
});

const tenantProjectLogicalSubjectAreaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/logical/subject-areas/$subjectAreaId",
  component: ProjectLogicalSubjectArea,
});

const tenantProjectLogicalEntityRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/logical/entities/$entityId",
  validateSearch: projectLayerSearch,
  component: ProjectLogicalEntity,
});

const tenantProjectLogicalAttributeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/logical/attributes/$attributeId",
  validateSearch: projectLayerSearch,
  component: ProjectLogicalAttribute,
});

const tenantProjectLogicalRelationshipRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/logical/relationships/$relationshipId",
  validateSearch: projectLayerSearch,
  component: ProjectLogicalRelationship,
});

const tenantProjectDimensionalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/dimensional",
  validateSearch: modelViewSearch,
  component: ProjectDimensional,
});

const tenantProjectDimensionalSubjectAreaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/dimensional/subject-areas/$subjectAreaId",
  component: ProjectDimensionalSubjectArea,
});

const tenantProjectDimensionalObjectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/dimensional/objects/$entityId",
  validateSearch: projectLayerSearch,
  component: ProjectDimensionalObject,
});

const tenantProjectDimensionalAttributeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/dimensional/attributes/$attributeId",
  validateSearch: projectLayerSearch,
  component: ProjectDimensionalAttribute,
});

const tenantProjectDimensionalRelationshipRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tenants/$tenantId/projects/$projectId/dimensional/relationships/$relationshipId",
  validateSearch: projectLayerSearch,
  component: ProjectDimensionalRelationship,
});

const routeTree = rootRoute.addChildren([
  tenantEntryRoute,
  tenantHomeRoute,
  tenantMetadataRoute,
  tenantMetadataObjectsRoute,
  tenantProjectsRoute,
  tenantMappingRoute,
  tenantMappingProjectRoute,
  tenantMappingObjectRoute,
  tenantMappingAttributeRoute,
  tenantCodeGenerationRoute,
  tenantCodeGenerationProjectRoute,
  tenantGeneratedSqlArtifactRoute,
  tenantValidationRoute,
  tenantValidationProjectRoute,
  tenantValidationGroupRoute,
  tenantValidationCheckRoute,
  tenantPromptsRoute,
  tenantPromptTemplateRoute,
  tenantProjectSettingsRoute,
  tenantProjectPromptSettingsRoute,
  tenantProjectRoute,
  tenantProjectInputScopeRoute,
  tenantProjectProfilingRoute,
  tenantProjectProfilingDetailRoute,
  tenantProjectAnalysisRoute,
  tenantProjectAnalysisDetailRoute,
  tenantProjectContextRoute,
  tenantProjectContextGroupRoute,
  tenantProjectContextRecordRoute,
  tenantProjectMetadataEnrichmentRoute,
  tenantProjectSubjectAreasRoute,
  tenantProjectSubjectAreaRoute,
  tenantProjectLogicalRoute,
  tenantProjectLogicalSubjectAreaRoute,
  tenantProjectLogicalEntityRoute,
  tenantProjectLogicalAttributeRoute,
  tenantProjectLogicalRelationshipRoute,
  tenantProjectDimensionalRoute,
  tenantProjectDimensionalSubjectAreaRoute,
  tenantProjectDimensionalObjectRoute,
  tenantProjectDimensionalAttributeRoute,
  tenantProjectDimensionalRelationshipRoute,
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
        refetchOnReconnect: false,
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
  const { section, objectId } = tenantMetadataRoute.useSearch();
  const navigate = useNavigate({ from: tenantMetadataRoute.fullPath });
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
          tenantLock={home.lock}
          canWriteMetadata={home.tenant.effective_role !== "viewer"}
          section={section ?? "reference"}
          objectId={objectId ?? null}
          onSectionChange={(next) => { void navigate({ search: { section: next } }); }}
          onObjectChange={(id) => { void navigate({ search: { section: "objects", ...(id === null ? {} : { objectId: id }) } }); }}
        />
      )}
    </TenantRouteFrame>
  );
}

function TenantMetadataObjects() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId } = tenantMetadataObjectsRoute.useParams();
  const { objectId } = tenantMetadataObjectsRoute.useSearch();
  const navigate = useNavigate({ from: tenantMetadataObjectsRoute.fullPath });
  return <TenantRouteFrame api={api} tenantId={Number(tenantId)} activeNav="metadata" loadingLabel="Loading physical metadata">
    {() => <PhysicalMetadataScreen key={tenantId} api={api} tenantId={Number(tenantId)} objectId={objectId ?? null} onObjectChange={(id) => { void navigate({ search: id === null ? {} : { objectId: id } }); }} />}
  </TenantRouteFrame>;
}

function ProjectsLedger() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId } = tenantProjectsRoute.useParams();
  return <ProjectsLedgerScreen api={api} tenantId={Number(tenantId)} />;
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
          <WorkflowProjects api={api} tenantId={numericTenantId} workflow="mapping" />
        </main>
      )}
    </TenantRouteFrame>
  );
}

function TenantMappingProject() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantMappingProjectRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  const { layer = "logical" } = tenantMappingProjectRoute.useSearch();
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="mapping"
      loadingLabel="Loading Mapping"
    >
      {({ home, project }) => (
        <MappingScreen
          key={`${numericTenantId}:${numericProjectId}:${layer}`}
          layer={layer}
          api={api}
          tenantId={numericTenantId}
          project={project}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
          hasAppPermission={canAuthorProjects(home.tenant.effective_role)}
        />
      )}
    </ProjectRouteFrame>
  );
}

function TenantMappingObject() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, mappingObjectId } = tenantMappingObjectRoute.useParams();
  return <TenantMappingDetail
    api={api}
    tenantId={Number(tenantId)}
    projectId={Number(projectId)}
    detailId={Number(mappingObjectId)}
    kind="object"
  />;
}

function TenantMappingAttribute() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, mappingAttributeId } = tenantMappingAttributeRoute.useParams();
  return <TenantMappingDetail
    api={api}
    tenantId={Number(tenantId)}
    projectId={Number(projectId)}
    detailId={Number(mappingAttributeId)}
    kind="attribute"
  />;
}

function TenantMappingDetail({
  api,
  tenantId,
  projectId,
  detailId,
  kind,
}: {
  api: WorkbenchApi;
  tenantId: number;
  projectId: number;
  detailId: number;
  kind: "object" | "attribute";
}) {
  if (!Number.isSafeInteger(detailId) || detailId <= 0) return <ErrorPage />;
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={tenantId}
      projectId={projectId}
      activeStage="mapping"
      loadingLabel="Loading Mapping"
    >
      {({ home, project }) => (
        <div className="mapping-workspace">
          {kind === "object" ? (
            <MappingObjectDetailPage api={api} tenantId={tenantId} projectId={projectId} mappingObjectId={detailId}
              projectRevision={project.project_revision}
              hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true && canAuthorProjects(home.tenant.effective_role)}
            />
          ) : (
            <MappingAttributeDetailPage api={api} tenantId={tenantId} projectId={projectId} mappingAttributeId={detailId} />
          )}
        </div>
      )}
    </ProjectRouteFrame>
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
          <WorkflowProjects api={api} tenantId={numericTenantId} workflow="code_generation" />
        </main>
      )}
    </TenantRouteFrame>
  );
}

function TenantCodeGenerationProject() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantCodeGenerationProjectRoute.useParams();
  const { layer = "logical" } = tenantCodeGenerationProjectRoute.useSearch();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="code-generation"
      loadingLabel="Loading Code Generation"
    >
      {({ home, project }) => (
        <CodeGenerationScreen
          key={`${tenantId}/${projectId}/${layer}`}
          layer={layer}
          api={api}
          tenantId={numericTenantId}
          project={project}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
          hasAppPermission={canAuthorProjects(home.tenant.effective_role)}
        />
      )}
    </ProjectRouteFrame>
  );
}

function TenantGeneratedSqlArtifact() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, artifactId } = tenantGeneratedSqlArtifactRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  const numericArtifactId = Number(artifactId);
  if (!Number.isSafeInteger(numericArtifactId) || numericArtifactId <= 0) {
    return <ErrorPage />;
  }
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="code-generation"
      loadingLabel="Loading stored SQL"
    >
      {({ home, project }) => (
        <div className="mapping-workspace code-generation-workspace">
          <GeneratedSqlDetailPage
            api={api}
            tenantId={numericTenantId}
            project={project}
            artifactId={numericArtifactId}
            hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
            hasAppPermission={canAuthorProjects(home.tenant.effective_role)}
          />
        </div>
      )}
    </ProjectRouteFrame>
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
          <WorkflowProjects api={api} tenantId={numericTenantId} workflow="validation" />
        </main>
      )}
    </TenantRouteFrame>
  );
}

function TenantValidationProject() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, groupId, checkId } = useParams({ strict: false });
  const { layer = "logical" } = useSearch({ strict: false });
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="validation"
      loadingLabel="Loading Validation"
    >
      {({ home, project }) => (
        <ValidationScreen
          key={`${tenantId}/${projectId}/${layer}/${groupId ?? ""}/${checkId ?? ""}`}
          layer={layer}
          api={api}
          tenantId={numericTenantId}
          project={project}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
          hasAppPermission={canAuthorProjects(home.tenant.effective_role)}
          groupId={groupId === undefined ? undefined : Number(groupId)}
          checkId={checkId === undefined ? undefined : Number(checkId)}
        />
      )}
    </ProjectRouteFrame>
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
          canAuthorPrompts={canAuthorProjects(home.tenant.effective_role)}
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
          canAuthorPrompts={canAuthorProjects(home.tenant.effective_role)}
          isSuperAdmin={home.tenant.effective_role === "super_admin"}
          hasTenantLock={home.lock.owned_by_current_principal === true}
        />
      )}
    </TenantRouteFrame>
  );
}

function TenantProjectSettings() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectSettingsRoute.useParams();
  return <ProjectRouteFrame tenantLockApi={api} api={api} tenantId={Number(tenantId)} projectId={Number(projectId)}
    activeStage="settings" loadingLabel="Loading Project Settings">
    {({ home, project }) => <ProjectSettingsScreen key={`${tenantId}:${projectId}`} api={api} home={home} project={project} />}
  </ProjectRouteFrame>;
}

function TenantProjectPromptSettings() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectPromptSettingsRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="settings-prompts"
      loadingLabel="Loading Project Prompt Settings"
    >
      {({ home, project }) => (
        <ProjectPromptSettings
          api={api}
          tenantId={numericTenantId}
          project={project}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
          hasAppPermission={canAuthorProjects(home.tenant.effective_role)}
        />
      )}
    </ProjectRouteFrame>
  );
}

function ProjectOverview() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectRoute.useParams();
  return <ProjectOverviewScreen api={api} tenantId={Number(tenantId)} projectId={Number(projectId)} />;
}

function ProjectInputScope() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectInputScopeRoute.useParams();
  return <ProjectInputScopeScreen api={api} tenantId={Number(tenantId)} projectId={Number(projectId)} />;
}

function ProjectProfiling() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectProfilingRoute.useParams();
  const { returnObjectId, ...resultFilters } = tenantProjectProfilingRoute.useSearch();
  const navigate = useNavigate({ from: "/tenants/$tenantId/projects/$projectId/profiling" });
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="profiling"
      loadingLabel="Loading Profiling"
    >
      {({ home, project }) => (
        <ProfilingScreen
          api={api}
          tenantId={numericTenantId}
          project={project}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
          resultFilters={resultFilters}
          {...(returnObjectId === undefined ? {} : { returnObjectId })}
          onApplyResultFilters={(filters) => {
            void navigate({ search: filters, replace: true });
          }}
          onReturnFocusHandled={() => navigate({ search: resultFilters, replace: true })}
        />
      )}
    </ProjectRouteFrame>
  );
}

function ProjectProfilingDetail() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, objectId } = tenantProjectProfilingDetailRoute.useParams();
  const returnSearch = tenantProjectProfilingDetailRoute.useSearch();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  const numericObjectId = Number(objectId);
  if (!Number.isSafeInteger(numericObjectId) || numericObjectId <= 0) return <ErrorPage />;
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="profiling"
      loadingLabel="Loading profile evidence"
    >
      {() => (
        <ProfilingObjectDetailPage
          api={api}
          tenantId={numericTenantId}
          projectId={numericProjectId}
          objectId={numericObjectId}
          returnSearch={returnSearch}
        />
      )}
    </ProjectRouteFrame>
  );
}

function ProjectAnalysis() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectAnalysisRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="analysis"
      loadingLabel="Loading Analysis"
    >
      {({ home, project }) => (
        <AnalysisScreen
          api={api}
          tenantId={numericTenantId}
          project={project}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
        />
      )}
    </ProjectRouteFrame>
  );
}

function ProjectContext() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectContextRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="context"
      loadingLabel="Loading Context"
    >
      {({ home, project }) => (
        <ContextScreen api={api} tenantId={numericTenantId} project={project} hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true && canAuthorProjects(home.tenant.effective_role)} authoringDisabledReason={!canAuthorProjects(home.tenant.effective_role) ? "Your role can view Context but cannot change it." : project.is_locked ? "Unlock this Project from the Projects list before changing Context." : !home.lock.owned_by_current_principal ? "Acquire the Tenant Lock before changing Context." : undefined} />
      )}
    </ProjectRouteFrame>
  );
}

function ProjectContextGroup() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, groupId } = tenantProjectContextGroupRoute.useParams();
  const numericGroupId = Number(groupId);
  if (!Number.isSafeInteger(numericGroupId) || numericGroupId <= 0) return <ErrorPage />;
  return <ProjectRouteFrame tenantLockApi={api} api={api} tenantId={Number(tenantId)} projectId={Number(projectId)} activeStage="context" loadingLabel="Loading Context group">
    {({ home, project }) => <ContextGroupDetailPage api={api} tenantId={Number(tenantId)} projectId={Number(projectId)} groupId={numericGroupId} key={groupId} projectRevision={project.project_revision} hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true && canAuthorProjects(home.tenant.effective_role)} authoringDisabledReason={!canAuthorProjects(home.tenant.effective_role) ? "Your role can view Context but cannot change it." : project.is_locked ? "Unlock this Project from the Projects list before changing Context." : !home.lock.owned_by_current_principal ? "Acquire the Tenant Lock before changing Context." : undefined} />}
  </ProjectRouteFrame>;
}

function ProjectContextRecord() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, recordId } = tenantProjectContextRecordRoute.useParams();
  const canonicalRecordId = recordId.toLowerCase();
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(canonicalRecordId)) return <ErrorPage />;
  return <ProjectRouteFrame tenantLockApi={api} api={api} tenantId={Number(tenantId)} projectId={Number(projectId)} activeStage="context" loadingLabel="Loading Context record">
    {({ home, project }) => <ContextRecordDetailPage api={api} tenantId={Number(tenantId)} projectId={Number(projectId)} recordId={canonicalRecordId} key={canonicalRecordId} projectRevision={project.project_revision} hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true && canAuthorProjects(home.tenant.effective_role)} authoringDisabledReason={!canAuthorProjects(home.tenant.effective_role) ? "Your role can view Context but cannot change it." : project.is_locked ? "Unlock this Project from the Projects list before changing Context." : !home.lock.owned_by_current_principal ? "Acquire the Tenant Lock before changing Context." : undefined} />}
  </ProjectRouteFrame>;
}

function ProjectMetadataEnrichment() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectMetadataEnrichmentRoute.useParams();
  return (
    <ProjectRouteFrame tenantLockApi={api} api={api} tenantId={Number(tenantId)} projectId={Number(projectId)}
      activeStage="metadata-enrichment" loadingLabel="Loading Metadata enrichment">
      {({ home, project }) => (
        <MetadataEnrichmentScreen api={api} tenantId={Number(tenantId)} project={project}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true} />
      )}
    </ProjectRouteFrame>
  );
}

function ProjectSubjectAreas() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectSubjectAreasRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="subject-area"
      loadingLabel="Loading Subject Areas"
    >
      {({ home, project }) => (
        <SubjectAreasScreen
          api={api}
          tenantId={numericTenantId}
          project={project}
          canDelete={home.tenant.effective_role === "super_admin" || home.tenant.effective_role === "tenant_admin"}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
        />
      )}
    </ProjectRouteFrame>
  );
}

function ProjectSubjectArea() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, subjectAreaId } = tenantProjectSubjectAreaRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  const numericSubjectAreaId = Number(subjectAreaId);
  if (!Number.isSafeInteger(numericSubjectAreaId) || numericSubjectAreaId <= 0) return <ErrorPage />;
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="subject-area"
      loadingLabel="Loading Subject Area"
    >
      {({ home, project }) => (
        <SubjectAreaDetailPage
          key={numericSubjectAreaId}
          api={api}
          tenantId={numericTenantId}
          project={project}
          subjectAreaId={numericSubjectAreaId}
          canDelete={home.tenant.effective_role === "super_admin" || home.tenant.effective_role === "tenant_admin"}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
        />
      )}
    </ProjectRouteFrame>
  );
}


function ProjectLogical() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectLogicalRoute.useParams();
  const { view } = tenantProjectLogicalRoute.useSearch();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="logical"
      loadingLabel="Loading Logical"
    >
      {({ home, project }) => (
        <LogicalScreen
          api={api}
          tenantId={numericTenantId}
          project={project}
          initialView={view}
          canDelete={home.tenant.effective_role === "super_admin" || home.tenant.effective_role === "tenant_admin"}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
        />
      )}
    </ProjectRouteFrame>
  );
}

function ProjectLogicalSubjectArea() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, subjectAreaId } = tenantProjectLogicalSubjectAreaRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  const numericSubjectAreaId = Number(subjectAreaId);
  if (!Number.isSafeInteger(numericSubjectAreaId) || numericSubjectAreaId <= 0) return <ErrorPage />;
  return (
    <ProjectRouteFrame tenantLockApi={api} api={api} tenantId={numericTenantId} projectId={numericProjectId}
      activeStage="logical" loadingLabel="Loading Logical">
      {({ project }) => <LogicalSubjectAreaPage api={api} tenantId={numericTenantId} projectId={numericProjectId}
        projectRevision={project.project_revision} subjectAreaId={numericSubjectAreaId} />}
    </ProjectRouteFrame>
  );
}

function ProjectLogicalEntity() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, entityId } = tenantProjectLogicalEntityRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  const numericEntityId = Number(entityId);
  if (!Number.isSafeInteger(numericEntityId) || numericEntityId <= 0) return <ErrorPage />;
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="logical"
      loadingLabel="Loading Logical"
    >
      {({ home, project }) => {
        const actions = <ProjectRecordTools canDelete={home.tenant.effective_role === "super_admin" || home.tenant.effective_role === "tenant_admin"} api={api} tenantId={numericTenantId} projectId={numericProjectId} projectRevision={project.project_revision}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true} dataset="logical_entity" recordId={numericEntityId} />;
        return (
          <LogicalEntityDetailPage
            actions={actions}
            api={api}
            tenantId={numericTenantId}
            projectId={numericProjectId}
            entityId={numericEntityId}
            projectRevision={project.project_revision}
            hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
          />
        );
      }}
    </ProjectRouteFrame>
  );
}

function ProjectLogicalAttribute() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, attributeId } = tenantProjectLogicalAttributeRoute.useParams();
  return (
    <LogicalDetailRoute
      api={api}
      tenantId={Number(tenantId)}
      projectId={Number(projectId)}
      detailId={Number(attributeId)}
      kind="attribute"
    />
  );
}

function ProjectLogicalRelationship() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, relationshipId } = tenantProjectLogicalRelationshipRoute.useParams();
  return (
    <LogicalDetailRoute
      api={api}
      tenantId={Number(tenantId)}
      projectId={Number(projectId)}
      detailId={Number(relationshipId)}
      kind="relationship"
    />
  );
}

function LogicalDetailRoute({
  api,
  tenantId,
  projectId,
  detailId,
  kind,
}: {
  api: WorkbenchApi;
  tenantId: number;
  projectId: number;
  detailId: number;
  kind: "attribute" | "relationship";
}) {
  if (!Number.isSafeInteger(detailId) || detailId <= 0) return <ErrorPage />;
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={tenantId}
      projectId={projectId}
      activeStage="logical"
      loadingLabel="Loading Logical"
    >
      {({ home, project }) => {
        const actions = <ProjectRecordTools canDelete={home.tenant.effective_role === "super_admin" || home.tenant.effective_role === "tenant_admin"} api={api} tenantId={tenantId} projectId={projectId} projectRevision={project.project_revision}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true} dataset={`logical_${kind}`} recordId={detailId} />;
        return (
          kind === "attribute" ? (
            <LogicalAttributeDetailPage
              actions={actions}
              api={api}
              tenantId={tenantId}
              projectId={projectId}
              attributeId={detailId}
            />
          ) : (
            <LogicalRelationshipDetailPage
              actions={actions}
              api={api}
              tenantId={tenantId}
              projectId={projectId}
              relationshipId={detailId}
            />
          )
        );
      }}
    </ProjectRouteFrame>
  );
}

function ProjectDimensional() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId } = tenantProjectDimensionalRoute.useParams();
  const { view } = tenantProjectDimensionalRoute.useSearch();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="dimensional"
      loadingLabel="Loading Dimensional"
    >
      {({ home, project }) => (
        <DimensionalScreen
          api={api}
          tenantId={numericTenantId}
          project={project}
          initialView={view}
          canDelete={home.tenant.effective_role === "super_admin" || home.tenant.effective_role === "tenant_admin"}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
        />
      )}
    </ProjectRouteFrame>
  );
}

function ProjectDimensionalSubjectArea() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, subjectAreaId } = tenantProjectDimensionalSubjectAreaRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  const numericSubjectAreaId = Number(subjectAreaId);
  if (!Number.isSafeInteger(numericSubjectAreaId) || numericSubjectAreaId <= 0) return <ErrorPage />;
  return (
    <ProjectRouteFrame tenantLockApi={api} api={api} tenantId={numericTenantId} projectId={numericProjectId}
      activeStage="dimensional" loadingLabel="Loading Dimensional">
      {({ project }) => <DimensionalSubjectAreaPage api={api} tenantId={numericTenantId} projectId={numericProjectId}
        projectRevision={project.project_revision} subjectAreaId={numericSubjectAreaId} />}
    </ProjectRouteFrame>
  );
}

function ProjectDimensionalObject() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, entityId } = tenantProjectDimensionalObjectRoute.useParams();
  const numericTenantId = Number(tenantId);
  const numericProjectId = Number(projectId);
  const numericEntityId = Number(entityId);
  if (!Number.isSafeInteger(numericEntityId) || numericEntityId <= 0) return <ErrorPage />;
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={numericTenantId}
      projectId={numericProjectId}
      activeStage="dimensional"
      loadingLabel="Loading Dimensional"
    >
      {({ home, project }) => {
        const actions = <ProjectRecordTools canDelete={home.tenant.effective_role === "super_admin" || home.tenant.effective_role === "tenant_admin"} api={api} tenantId={numericTenantId} projectId={numericProjectId} projectRevision={project.project_revision}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true} dataset="dimensional_entity" recordId={numericEntityId} />;
        return (
          <DimensionalObjectDetailPage
            actions={actions}
            api={api}
            tenantId={numericTenantId}
            projectId={numericProjectId}
            entityId={numericEntityId}
            projectRevision={project.project_revision}
            hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true}
          />
        );
      }}
    </ProjectRouteFrame>
  );
}

function ProjectDimensionalAttribute() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, attributeId } = tenantProjectDimensionalAttributeRoute.useParams();
  return <DimensionalDetailRoute
    api={api}
    tenantId={Number(tenantId)}
    projectId={Number(projectId)}
    detailId={Number(attributeId)}
    kind="attribute"
  />;
}

function ProjectDimensionalRelationship() {
  const { api } = rootRoute.useRouteContext();
  const { tenantId, projectId, relationshipId } = tenantProjectDimensionalRelationshipRoute.useParams();
  return <DimensionalDetailRoute
    api={api}
    tenantId={Number(tenantId)}
    projectId={Number(projectId)}
    detailId={Number(relationshipId)}
    kind="relationship"
  />;
}

function DimensionalDetailRoute({
  api,
  tenantId,
  projectId,
  detailId,
  kind,
}: {
  api: WorkbenchApi;
  tenantId: number;
  projectId: number;
  detailId: number;
  kind: "attribute" | "relationship";
}) {
  if (!Number.isSafeInteger(detailId) || detailId <= 0) return <ErrorPage />;
  return (
    <ProjectRouteFrame
      tenantLockApi={api}
      api={api}
      tenantId={tenantId}
      projectId={projectId}
      activeStage="dimensional"
      loadingLabel="Loading Dimensional"
    >
      {({ home, project }) => {
        const actions = <ProjectRecordTools canDelete={home.tenant.effective_role === "super_admin" || home.tenant.effective_role === "tenant_admin"} api={api} tenantId={tenantId} projectId={projectId} projectRevision={project.project_revision}
          hasTenantLock={!project.is_locked && home.lock.owned_by_current_principal === true} dataset={`dimensional_${kind}`} recordId={detailId} />;
        return (
          kind === "attribute" ? (
            <DimensionalAttributeDetailPage
              actions={actions}
              api={api}
              tenantId={tenantId}
              projectId={projectId}
              attributeId={detailId}
            />
          ) : (
            <DimensionalRelationshipDetailPage
              actions={actions}
              api={api}
              tenantId={tenantId}
              projectId={projectId}
              relationshipId={detailId}
            />
          )
        );
      }}
    </ProjectRouteFrame>
  );
}
