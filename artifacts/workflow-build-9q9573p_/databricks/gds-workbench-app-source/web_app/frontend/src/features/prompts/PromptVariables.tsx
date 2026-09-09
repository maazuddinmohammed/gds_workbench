import { useId, useState } from "react";

import type { PromptStageVariable } from "./api";

export function PromptVariables({
  variables,
  label = "Allowed Prompt variables",
  onInsert,
  disabled = false,
}: {
  variables: PromptStageVariable[];
  label?: string;
  onInsert?: ((name: string) => void) | undefined;
  disabled?: boolean | undefined;
}) {
  const searchId = useId();
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState("");
  const groupOf = (variable: PromptStageVariable) => variable.group
    || (variable.name.startsWith("conceptual_") ? "Conceptual results"
      : variable.name.startsWith("logical_") ? "Logical results and bindings"
        : variable.name.startsWith("dimensional_") ? "Dimensional results"
          : ["naming_instructions", "audit_columns", "technical_columns"].includes(variable.name) ? "Model settings"
            : variable.name === "modeling_assertions" ? "Modeling assertions"
              : ["source_context", "gds_context", "object_context", "object_attribute_context", "object_relationship_context", "ingestion_mapping"].includes(variable.name) ? "Physical context"
                : "Workflow context");
  const groups = [...new Set(variables.map(groupOf))];
  const filtered = variables.filter((variable) => (
    (!group || groupOf(variable) === group)
    && `${variable.name} ${variable.description} ${variable.source ?? ""}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())
  )).sort((left, right) => left.order - right.order);
  if (!variables.length) {
    return <div className="empty-state compact">This stage allows no variables.</div>;
  }
  return (
    <div className="prompt-input-reference">
      <p>
        Choose what this workflow receives. Only referenced variables are inserted into your prompts.
        Dictionaries and lists render as JSON; examples below are synthetic.
      </p>
      <div className="prompt-reference-filters">
        <label htmlFor={searchId}><span>Search variables</span><input id={searchId} type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or meaning" /></label>
        {groups.length > 1 ? <label><span>Variable group</span><select value={group} onChange={(event) => setGroup(event.target.value)}><option value="">All groups</option>{groups.map((name) => <option key={name}>{name}</option>)}</select></label> : null}
        <span role="status">{filtered.length} of {variables.length} variables</span>
      </div>
      {!filtered.length ? <div className="empty-state compact">No variables match. Change the search or group.</div> : (
      <div className="table-scroll">
        <table aria-label={label}>
          <thead><tr><th>Input</th><th>Meaning and use</th></tr></thead>
          <tbody>
            {filtered.map((variable) => (
              <tr key={variable.name}>
                <th scope="row">
                  <code>{`{{${variable.name}}}`}</code>
                  <span className="prompt-input-type">
                    {variable.data_type} · Optional inclusion
                  </span>
                  {variable.group ? <span className="prompt-input-type">{variable.group}</span> : null}
                  {onInsert ? <button className="button button-secondary button-small prompt-variable-insert" type="button" disabled={disabled} aria-label={`Insert ${variable.name}`} onClick={() => onInsert(variable.name)}>Insert variable</button> : null}
                </th>
                <td>
                  <p>{variable.description}</p>
                  {variable.source || variable.availability ? (
                    <dl className="prompt-input-facts">
                      {variable.source ? <div><dt>Source</dt><dd>{variable.source}</dd></div> : null}
                      {variable.availability ? <div><dt>Available</dt><dd>{variable.availability}</dd></div> : null}
                    </dl>
                  ) : null}
                  <details className="prompt-input-shape">
                    <summary>Shape and example for {variable.name}</summary>
                    {variable.example !== null && variable.example !== undefined ? (
                      <><h3>Synthetic example</h3><pre>{JSON.stringify(variable.example, null, 2)}</pre></>
                    ) : <p>No example registered.</p>}
                    {variable.value_schema ? (
                      <><h3>Value schema</h3><pre>{JSON.stringify(variable.value_schema, null, 2)}</pre></>
                    ) : <p>No value schema registered.</p>}
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  );
}
