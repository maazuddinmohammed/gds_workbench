import { useQuery } from "@tanstack/react-query";
import { loadWorkflowScope } from "../workflows/api";
import type { ModelInputScopeApi } from "./api";

export const scopeFilterChoicesKey = (tenantId: number, modelId: number) =>
  ["model-scope-filter-choices", tenantId, modelId] as const;

export function sourceCodes(values: string[]): string[] {
  return [...new Map(values.map((value) => [value.trim().toLowerCase(), value])).values()]
    .sort((left, right) => left.localeCompare(right));
}

export interface ScopeFilterChoices {
  tenantCodes: string[];
  systemCodes: string[];
  isLoading: boolean;
  isUnavailable: boolean;
}

export function useScopeFilterChoices(
  api: Pick<ModelInputScopeApi, "listModelInputScope">,
  tenantId: number,
  modelId: number,
  modelRevision: number | undefined,
) {
  const query = useQuery({
    queryKey: scopeFilterChoicesKey(tenantId, modelId),
    queryFn: () => loadWorkflowScope(api, tenantId, modelId, "enrichment"),
    enabled: modelRevision !== undefined,
  });
  const isUnavailable = query.isError || (query.data !== undefined
    && query.data.modelRevision !== modelRevision);
  const rows = isUnavailable ? [] : query.data?.items ?? [];
  return {
    tenantCodes: sourceCodes(rows.map((row) => row.source_tenant_code)),
    systemCodes: sourceCodes(rows.map((row) => row.system_code)),
    isLoading: query.isPending,
    isUnavailable,
    refetch: query.refetch,
  };
}

export function SourceCodeFilter({ label, value, codes, isLoading, isUnavailable, onChange }: {
  label: string; value: string; codes: string[]; isLoading: boolean; isUnavailable: boolean;
  onChange: (value: string) => void;
}) {
  const selected = codes.find((code) => code.toLowerCase() === value.trim().toLowerCase()) ?? value;
  return <label><span>{label}</span><select aria-label={label} value={selected}
    disabled={isLoading || isUnavailable} onChange={(event) => onChange(event.target.value)}>
    <option value="">{isLoading ? "Loading choices…" : isUnavailable ? "Choices unavailable" : "All"}</option>
    {selected && !codes.includes(selected) ? <option value={selected} disabled>{selected} (unavailable)</option> : null}
    {codes.map((code) => <option key={code} value={code}>{code}</option>)}
  </select></label>;
}

export function SourceFilterNotice({ unavailable }: { unavailable: boolean }) {
  return unavailable ? <p className="inline-error" role="status">Source filter choices could not be loaded at the current Model revision. Refresh to retry.</p> : null;
}
