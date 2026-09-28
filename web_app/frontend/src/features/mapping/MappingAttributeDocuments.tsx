import { useId, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import type { JsonValue } from "../../shared/contracts";
import { mappingQueryKeys, type MappingApi, type MappingAttribute, type MappingAttributeDetail } from "./api";
import { MappingDocumentValue } from "./MappingDocumentView";

// Ledger pages contain up to 200 rows. Keep detail reads bounded, including
// queued reads cancelled when a filter, Entity or Model changes.
export function createMappingDetailReader() {
  let active = 0;
  const waiting: (() => void)[] = [];
  return async <T,>(read: () => Promise<T>): Promise<T> => {
    if (active < 4) active += 1;
    else await new Promise<void>((resolve) => waiting.push(resolve));
    try { return await read(); }
    finally {
      const next = waiting.shift();
      if (next) next();
      else active -= 1;
    }
  };
}
const readDetail = createMappingDetailReader();

interface AttributeDocument {
  item: MappingAttribute;
  detail: MappingAttributeDetail | undefined;
  state: "loading" | "error" | "changed" | "ready";
  denied: boolean;
  retry: () => void;
}

export function useMappingAttributeDocuments({ api, tenantId, modelId, items, enabled }: {
  api: Pick<MappingApi, "readMappingAttribute">;
  tenantId: number; modelId: number; items: MappingAttribute[]; enabled: boolean;
}) {
  const visibleItems = enabled ? items.filter((item): item is MappingAttribute & { mapping_attribute_id: number } =>
    item.mapping_attribute_id !== null) : [];
  const queries = useQueries({ queries: visibleItems.map((item) => ({
    queryKey: mappingQueryKeys.attribute(tenantId, modelId, item.mapping_attribute_id),
    queryFn: ({ signal }: { signal: AbortSignal }) => readDetail(() => {
      signal.throwIfAborted();
      return api.readMappingAttribute(tenantId, modelId, item.mapping_attribute_id);
    }),
  })) });
  const documents = new Map<number, AttributeDocument>();
  for (const [index, item] of visibleItems.entries()) {
    const query = queries[index];
    if (!query) continue;
    const detail = query.data;
    const entity = item.target.entity;
    const detailEntity = detail?.target.entity;
    const matches = detail && detail.updated_at === item.updated_at
      && detail.mapping_attribute_id === item.mapping_attribute_id
      && detail.mapping_object_id === item.mapping_object_id
      && detail.source_system.system_id === item.source_system.system_id
      && detailEntity?.entity_id === entity.entity_id && detailEntity.entity_type === entity.entity_type
      && detailEntity.entity_schema_name === entity.entity_schema_name && detailEntity.entity_name === entity.entity_name
      && detail.target.attribute_id === item.target.attribute_id && detail.target.attribute_name === item.target.attribute_name
      && detail.target.data_type === item.target.data_type && detail.target.ordinal_position === item.target.ordinal_position;
    documents.set(item.mapping_attribute_id, {
      item, detail: matches && !query.isError ? detail : undefined,
      state: query.isPending ? "loading" : query.isError ? "error" : matches ? "ready" : "changed",
      denied: query.error instanceof ApiError && query.error.status === 403,
      retry: () => { void query.refetch(); },
    });
  }
  // Discover fields in ledger order, never request-completion order. Stale or
  // denied documents cannot contribute values or column names.
  const ready = [...documents.values()].flatMap(({ detail }) => detail ? [detail] : []);
  const fields = [...new Set(ready.flatMap((detail) => Object.keys(detail.mapping_document ?? {})))];
  const repeatedTarget = fields.indexOf("target_attribute_name");
  if (repeatedTarget >= 0 && ready.every((detail) => !detail.mapping_document
    || !Object.hasOwn(detail.mapping_document, "target_attribute_name")
    || detail.mapping_document.target_attribute_name === detail.target.attribute_name)) fields.splice(repeatedTarget, 1);
  const primary = ["transformation", "steps", "transformation_steps"];
  fields.sort((left, right) => {
    const a = primary.indexOf(left), b = primary.indexOf(right);
    return (a < 0 ? primary.length : a) - (b < 0 ? primary.length : b);
  });
  return { documents, fields };
}

export function MappingTransformationValue({ value, label, ordered = false }: {
  value: JsonValue; label: string; ordered?: boolean;
}) {
  const id = useId();
  const [expanded, setExpanded] = useState(false);
  const canExpand = JSON.stringify(value).length > 320;
  return <div className="mapping-transformation-cell mapping-logic-document">
    <div id={id} className={`mapping-cell-document${expanded ? " is-expanded" : ""}`}
      role="region" aria-label={label} tabIndex={0}>
      <MappingDocumentValue value={value} path={label} tabular={!ordered} />
    </div>
    {canExpand ? <button type="button" className="text-action mapping-cell-expand"
      aria-controls={id} aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      {expanded ? "Collapse transformation" : "Expand transformation"}
    </button> : null}
  </div>;
}
