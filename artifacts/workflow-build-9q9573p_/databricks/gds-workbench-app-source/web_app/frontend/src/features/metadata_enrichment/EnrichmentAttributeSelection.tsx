import { useEffect, useMemo, useRef, useState } from "react";

import type { ModelInputScopeApi, ModelInputScopeDetail } from "../model_input_scope/api";
import type { CreateWorkflowRunCommand, WorkflowScopeObject } from "../workflows/api";

export interface EnrichmentAttributeSelectionValue {
  targets: NonNullable<CreateWorkflowRunCommand["description_targets"]>;
  ready: boolean;
}
type DetailState =
  | { status: "loading"; scopeKey: string }
  | { status: "error"; scopeKey: string }
  | { status: "ready"; scopeKey: string; value: ModelInputScopeDetail };

export function EnrichmentAttributeSelection({
  objects, tenantId, modelId, readObject, initialObject, initialSelectedIds, disabled, onChange,
}: {
  objects: WorkflowScopeObject[];
  tenantId: number;
  modelId: number;
  readObject: ModelInputScopeApi["readModelInputScopeObject"];
  initialObject?: ModelInputScopeDetail;
  initialSelectedIds: number[];
  disabled: boolean;
  onChange: (selection: EnrichmentAttributeSelectionValue) => void;
}) {
  const [scopeMode, setScopeMode] = useState<"all" | "selected">(
    !initialObject && initialSelectedIds.length ? "selected" : "all",
  );
  const [includedIds, setIncludedIds] = useState<Set<number> | null>(
    !initialObject && initialSelectedIds.length ? new Set(initialSelectedIds) : null,
  );
  const [details, setDetails] = useState<Record<number, DetailState>>({});
  const [attributeChoices, setAttributeChoices] = useState<Record<number, Set<number>>>({});
  const [viewedId, setViewedId] = useState<number | null>(initialObject?.object_id ?? null);
  const [attributePage, setAttributePage] = useState(0);
  const initialAttributes = useRef(initialObject && initialSelectedIds.length ? new Set(initialSelectedIds) : null);
  const inFlight = useRef(new Set<number>());
  const mounted = useRef(true);
  const currentObjects = useRef(objects);
  currentObjects.current = objects;
  const heading = useRef<HTMLHeadingElement>(null);
  const returnToObject = useRef<number | null>(null);
  const eligible = useMemo(() => objects.filter((object) => (
    (!initialObject || object.object_id === initialObject.object_id)
    && object.source_tenant_id === tenantId && object.is_locked === false
    && /^[0-9a-f]{64}$/.test(object.review_revision ?? "") && object.attribute_count !== 0
  )), [objects, tenantId, initialObject]);
  const chosen = useMemo(() => eligible.filter((object) => (
    scopeMode === "all" || includedIds === null || includedIds.has(object.object_id)
  )), [eligible, scopeMode, includedIds]);
  const chosenIds = useMemo(() => new Set(chosen.map((object) => object.object_id)), [chosen]);
  const duplicateScope = new Set(objects.map((object) => object.object_id)).size !== objects.length;
  const tooManyObjects = chosen.length > 200;

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (disabled || tooManyObjects || duplicateScope) return;
    const next = chosen.filter((object) => !details[object.object_id] && !inFlight.current.has(object.object_id))
      .slice(0, Math.max(0, 4 - inFlight.current.size));
    for (const object of next) {
      const id = object.object_id;
      const key = scopeIdentity(object);
      inFlight.current.add(id);
      setDetails((old) => ({ ...old, [id]: { status: "loading", scopeKey: key } }));
      void readObject(tenantId, modelId, id).then((value) => {
        // The complete response must belong to the exact requested Scope record.
        if (value.object_id !== id || value.source_tenant_id !== tenantId
          || value.system_id !== object.system_id || value.system_code !== object.system_code
          || (object.connection_id !== undefined && value.connection_id !== object.connection_id)
          || value.object_name !== object.object_name || value.object_schema !== object.object_schema
          || value.zone_code !== object.zone_code || !value.is_model_input_eligible
          || value.is_locked !== false || value.review_revision !== object.review_revision
          || !Array.isArray(value.attributes) || value.attributes.length > 2000
          || !Number.isSafeInteger(value.attribute_count) || value.attribute_count < 0
          || value.attributes.length !== value.attribute_count
          || (object.attribute_count !== undefined && value.attribute_count !== object.attribute_count)
          || !Number.isSafeInteger(value.total_attribute_count)
          || value.total_attribute_count! < value.attribute_count
          || new Set(value.attributes.map((attribute) => attribute.attribute_id)).size !== value.attributes.length
          || value.attributes.some((attribute) => !Number.isSafeInteger(attribute.attribute_id) || attribute.attribute_id <= 0
            || !attribute.attribute_name?.trim() || attribute.is_active !== true
            || typeof attribute.is_locked !== "boolean" || !/^[0-9a-f]{64}$/.test(attribute.review_revision))) {
          throw new Error("Complete Attribute selection is unavailable");
        }
        if (!mounted.current) return;
        const current = currentObjects.current.find((item) => item.object_id === id);
        if (!current || scopeIdentity(current) !== key) return;
        setAttributeChoices((old) => old[id] ? old : {
          ...old,
          [id]: new Set(value.attributes.filter((attribute) => !attribute.is_locked
            && (!initialAttributes.current || initialAttributes.current.has(attribute.attribute_id)))
            .map((attribute) => attribute.attribute_id)),
        });
        setDetails((old) => ({ ...old, [id]: { status: "ready", scopeKey: key, value } }));
      }).catch(() => {
        if (mounted.current && currentObjects.current.some((item) => item.object_id === id && scopeIdentity(item) === key)) {
          setDetails((old) => ({ ...old, [id]: { status: "error", scopeKey: key } }));
        }
      }).finally(() => {
        inFlight.current.delete(id);
        // Also release a queue slot when an obsolete response was ignored.
        if (mounted.current) setDetails((old) => ({ ...old }));
      });
    }
  }, [chosen, details, disabled, duplicateScope, modelId, readObject, tenantId, tooManyObjects]);

  const selection = useMemo(() => {
    const targets: EnrichmentAttributeSelectionValue["targets"] = [];
    let storedAttributeCount = 0;
    let complete = !duplicateScope && !tooManyObjects && inFlight.current.size === 0;
    let failed = false;
    for (const object of chosen) {
      const entry = details[object.object_id];
      if (!entry || entry.status !== "ready" || entry.scopeKey !== scopeIdentity(object)) {
        complete = false;
        failed ||= entry?.status === "error" || Boolean(entry && entry.scopeKey !== scopeIdentity(object));
        continue;
      }
      const selected = entry.value.attributes.filter((attribute) => !attribute.is_locked
        && attributeChoices[object.object_id]?.has(attribute.attribute_id));
      if (selected.length) {
        storedAttributeCount += entry.value.total_attribute_count!;
        targets.push(...selected.map((attribute) => ({ object_id: object.object_id,
          attribute_id: attribute.attribute_id, expected_revision: attribute.review_revision })));
      }
    }
    return { targets, storedAttributeCount, complete, failed,
      ready: complete && targets.length > 0 && storedAttributeCount <= 5000 };
  }, [attributeChoices, chosen, details, duplicateScope, tooManyObjects]);
  useEffect(() => { onChange({ targets: selection.targets, ready: selection.ready }); }, [onChange, selection]);
  useEffect(() => {
    setAttributePage(0);
    if (viewedId !== null) heading.current?.focus();
    else if (returnToObject.current !== null) document.getElementById(`enrichment-choose-${returnToObject.current}`)?.focus();
  }, [viewedId]);

  const viewed = objects.find((object) => object.object_id === viewedId);
  const viewedState = viewedId === null ? undefined : details[viewedId];
  const viewedDetail = viewedState?.status === "ready" && viewed
    && viewedState.scopeKey === scopeIdentity(viewed) ? viewedState.value : undefined;
  const selectedCount = viewedDetail?.attributes.filter((attribute) => !attribute.is_locked
    && attributeChoices[viewedDetail.object_id]?.has(attribute.attribute_id)).length ?? 0;
  const lockedCount = viewedDetail?.attributes.filter((attribute) => attribute.is_locked).length ?? 0;
  const targetObjectCount = new Set(selection.targets.map((target) => target.object_id)).size;

  return <fieldset className="enrichment-attribute-selection" disabled={disabled}>
    <legend className="sr-only">Attribute enrichment selection</legend>
    {!initialObject ? <fieldset className="scope-mode-options">
      <legend>Objects</legend>
      <label><input type="radio" name="attribute-object-scope" checked={scopeMode === "all"} onChange={() => setScopeMode("all")} /><span><strong>All unlocked Objects</strong></span></label>
      <label><input type="radio" name="attribute-object-scope" checked={scopeMode === "selected"} onChange={() => setScopeMode("selected")} /><span><strong>Selected Objects</strong></span></label>
    </fieldset> : null}
    <div className="enrichment-selection-summary" aria-live="polite">
      <strong>{selection.targets.length} Attributes selected across {targetObjectCount} Objects</strong>
      <span>{selection.storedAttributeCount} stored Attributes in context · limit 5,000</span>
    </div>
    {tooManyObjects ? <p className="inline-error" role="alert">Select up to 200 Objects before loading Attributes. Choose Selected Objects to narrow this run.</p> : null}
    {duplicateScope ? <p className="inline-error" role="alert">Scope contains duplicate Objects. Close this dialog and refresh.</p> : null}
    {selection.storedAttributeCount > 5000 ? <p className="inline-error" role="alert">The selected Objects contain more than 5,000 stored Attributes. Choose fewer Objects; unchecked, locked and inactive sibling Attributes still count as context.</p> : null}
    {!selection.complete && !tooManyObjects && !duplicateScope ? <p className={selection.failed ? "inline-error" : "surface-state compact"} role={selection.failed ? "alert" : "status"} aria-busy={!selection.failed}>
      {selection.failed ? "Complete Attribute selection could not be loaded. Retry failed Objects, or close and refresh if metadata changed. No partial run will be created."
        : "Loading complete Attribute selections…"}
    </p> : null}
    {selection.complete && !selection.targets.length ? <p className="surface-state compact">Select at least one unlocked Attribute to run enrichment.</p> : null}
    {viewedId === null ? <div className="workflow-table-scroll table-scroll">
      <table className="enrichment-selection-table" aria-label="Objects for Attribute enrichment">
        <thead><tr><th className="selection-cell"><span className="sr-only">Selected</span></th><th>Schema</th><th>Object</th><th>Attributes</th><th>Locks</th></tr></thead>
        <tbody>{objects.map((object) => {
          const entry = details[object.object_id];
          const detail = entry?.status === "ready" && entry.scopeKey === scopeIdentity(object) ? entry.value : undefined;
          const included = chosenIds.has(object.object_id);
          const count = included && detail ? detail.attributes.filter((attribute) => !attribute.is_locked && attributeChoices[object.object_id]?.has(attribute.attribute_id)).length : 0;
          const total = detail?.attribute_count ?? object.attribute_count ?? 0;
          const locked = object.is_locked ? total : detail?.attributes.filter((attribute) => attribute.is_locked).length;
          const available = eligible.some((item) => item.object_id === object.object_id);
          return <tr key={object.object_id}>
            <td className="selection-cell"><input type="checkbox" aria-label={`Include Object ${object.object_name}`}
              checked={included} disabled={scopeMode === "all" || !available}
              onChange={(event) => setIncludedIds((old) => {
                const next = new Set(old ?? eligible.map((item) => item.object_id));
                if (event.target.checked) next.add(object.object_id); else next.delete(object.object_id);
                return next;
              })} /></td>
            <td>{object.object_schema}</td>
            <td><button type="button" className="text-action" id={`enrichment-choose-${object.object_id}`}
              disabled={!included || !detail} aria-label={`Choose Attributes for ${object.object_name}`}
              onClick={() => { returnToObject.current = object.object_id; setViewedId(object.object_id); }}>{object.object_name}</button>
              {object.source_tenant_id !== tenantId ? <small>Managed by another Tenant</small> : null}
              {entry?.status === "error" && included ? <button type="button" className="text-action" aria-label={`Retry Attributes for ${object.object_name}`} onClick={() => setDetails((old) => {
                const next = { ...old }; delete next[object.object_id]; return next;
              })}>Retry loading</button> : null}</td>
            <td><span>{count} selected · {total - count} unselected</span>{included && !detail && !selection.failed && !tooManyObjects ? <small>Loading…</small> : null}</td>
            <td>{locked === undefined ? "Checked when selected" : `${locked} locked`}{object.is_locked ? <small>Object locked</small> : null}</td>
          </tr>;
        })}</tbody>
      </table>
      {!objects.length ? <p className="empty-state compact">No Objects are in Scope.</p> : null}
    </div> : <section aria-label="Choose Object Attributes">
      {!initialObject ? <button type="button" className="text-action" onClick={() => setViewedId(null)}>Back to Objects</button> : null}
      <header className="enrichment-selection-header"><div><small>{viewed?.object_schema}</small><h3 ref={heading} tabIndex={-1}>{viewed?.object_name ?? "Object Attributes"}</h3></div>
        <span>{selectedCount} selected · {(viewedDetail?.attribute_count ?? 0) - selectedCount} unselected · {lockedCount} locked</span>
      </header>
      {viewedDetail ? <>
        <div className="enrichment-selection-actions">
          <button type="button" className="button button-secondary button-small" disabled={!chosenIds.has(viewedDetail.object_id)} onClick={() => setAttributeChoices((old) => ({ ...old,
            [viewedDetail.object_id]: new Set(viewedDetail.attributes.filter((attribute) => !attribute.is_locked).map((attribute) => attribute.attribute_id)) }))}>Select all unlocked Attributes</button>
          <button type="button" className="button button-secondary button-small" disabled={!chosenIds.has(viewedDetail.object_id)} onClick={() => setAttributeChoices((old) => ({ ...old, [viewedDetail.object_id]: new Set() }))}>Clear Attribute selection</button>
        </div>
        <div className="workflow-table-scroll table-scroll"><table className="enrichment-selection-table" aria-label={`Choose Attributes for ${viewedDetail.object_name}`}>
          <thead><tr><th className="selection-cell"><span className="sr-only">Selected</span></th><th>Attribute</th><th>Type</th><th>Lock</th></tr></thead>
          <tbody>{viewedDetail.attributes.slice(attributePage * 50, (attributePage + 1) * 50).map((attribute) => <tr key={attribute.attribute_id}>
            <td className="selection-cell"><input type="checkbox" aria-label={`Include Attribute ${attribute.attribute_name}`}
              checked={!attribute.is_locked && Boolean(attributeChoices[viewedDetail.object_id]?.has(attribute.attribute_id))}
              disabled={attribute.is_locked || !chosenIds.has(viewedDetail.object_id)}
              onChange={(event) => setAttributeChoices((old) => {
                const next = new Set(old[viewedDetail.object_id]);
                if (event.target.checked) next.add(attribute.attribute_id); else next.delete(attribute.attribute_id);
                return { ...old, [viewedDetail.object_id]: next };
              })} /></td><td>{attribute.attribute_name}</td><td>{attribute.attribute_inferred_data_type ?? attribute.attribute_data_type}</td><td>{attribute.is_locked ? "Locked" : "Unlocked"}</td>
          </tr>)}</tbody>
        </table></div>
        {viewedDetail.attributes.length > 50 ? <div className="enrichment-pagination"><span>{attributePage * 50 + 1}–{Math.min((attributePage + 1) * 50, viewedDetail.attributes.length)} of {viewedDetail.attributes.length}</span>
          <button type="button" className="button button-secondary button-small" disabled={attributePage === 0} onClick={() => setAttributePage((page) => page - 1)}>Previous Attributes</button>
          <button type="button" className="button button-secondary button-small" disabled={(attributePage + 1) * 50 >= viewedDetail.attributes.length} onClick={() => setAttributePage((page) => page + 1)}>Next Attributes</button>
        </div> : null}
      </> : !chosenIds.has(viewedId) ? <p className="surface-state compact">This Object is not selected or has no available unlocked Attributes.</p> : viewedState?.status === "error" ? <button type="button" className="button button-secondary button-small" onClick={() => setDetails((old) => {
        const next = { ...old }; delete next[viewedId]; return next;
      })}>Retry loading Attributes</button> : <p className="surface-state compact" aria-busy="true">Loading Attributes…</p>}
    </section>}
  </fieldset>;
}

function scopeIdentity(object: WorkflowScopeObject): string {
  return JSON.stringify([object.object_id, object.source_tenant_id, object.system_id, object.system_code,
    object.connection_id, object.object_schema, object.object_name, object.zone_code, object.is_locked,
    object.review_revision, object.attribute_count]);
}
