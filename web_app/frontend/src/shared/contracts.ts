export type ReviewStatus = "active" | "needs_review" | "inactive" | "deprecated";

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject;
export type JsonObject = { [key: string]: JsonValue };

export type ModelingConfidence = "low" | "medium" | "high";
export type ModelingCardinality =
  | "one_to_one"
  | "one_to_many"
  | "many_to_one"
  | "many_to_many"
  | "unknown";
