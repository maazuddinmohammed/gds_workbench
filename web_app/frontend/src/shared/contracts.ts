export type ReviewStatus = "active" | "inactive" | "deprecated";

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject;
export type JsonObject = { [key: string]: JsonValue };

/** An active Subject Area with how many active Entities of one model layer it reaches. */
export interface ModelSubjectArea {
  subject_area_id: number;
  subject_area_name: string;
  subject_area_definition: string;
  table_count: number;
  entity_count: number;
}

export interface ModelSubjectAreaPage {
  project_id: number;
  project_revision: number;
  items: ModelSubjectArea[];
}
