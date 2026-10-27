export type ReviewStatus = "active" | "inactive" | "deprecated";

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject;
export type JsonObject = { [key: string]: JsonValue };

export type SubjectAreaBuildState = "not_built" | "running" | "draft_waiting" | "applied" | "failed";

/**
 * A Subject Area's newest Build in one model layer that decides its state; the backend skips
 * cancelled Builds and discarded, superseded or expired drafts.
 */
export interface SubjectAreaBuild {
  state: SubjectAreaBuildState;
  workflow_run_id: number | null;
  /** When the Build started, its draft was validated or applied, or it failed. */
  at: string | null;
}

/** An active Subject Area with how much of it one model layer models, and its last Build. */
export interface ModelSubjectArea {
  subject_area_id: number;
  subject_area_name: string;
  subject_area_definition: string;
  table_count: number;
  /** Member Objects that are also members of another active area. */
  shared_table_count: number;
  /** Member Objects that reach an active Entity of this layer. */
  modeled_table_count: number;
  entity_count: number;
  build: SubjectAreaBuild;
}

export interface ModelSubjectAreaPage {
  project_id: number;
  project_revision: number;
  items: ModelSubjectArea[];
  /** The layer's newest Build or Optimize draft still waiting for Apply. */
  waiting_draft: { workflow_run_id: number; workflow_operation: "build" | "optimize" } | null;
}
