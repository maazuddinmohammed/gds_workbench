import type { ModelLedgerRecord } from "./api";

export function workflowLabel(workflow: ModelLedgerRecord["latest_workflow"]): string {
  if (!workflow) return "No runs";
  if (workflow === "code_generation") return "Code generation";
  return workflow[0]?.toLocaleUpperCase() + workflow.slice(1);
}
