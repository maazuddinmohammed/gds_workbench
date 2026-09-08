import { useId, useState } from "react";

import type { PromptTool } from "./api";

export function PromptTools({ tools, selected, disabled, onChange }: {
  tools: PromptTool[];
  selected: string[];
  disabled: boolean;
  onChange: (names: string[]) => void;
}) {
  const searchId = useId();
  const [search, setSearch] = useState("");
  const filtered = tools.filter((tool) => `${tool.name} ${tool.description}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const unavailable = selected.filter((name) => !tools.some((tool) => tool.name === name));

  return (
    <fieldset className="prompt-tool-catalog" disabled={disabled}>
      <legend>Enabled tools</legend>
      <p className="prompt-editor-note">Select the tools available to this Template. The agent chooses whether to call them. Tool choices are saved with this version.</p>
      {unavailable.length ? <p className="prompt-validation-note" role="status">Previously selected tools are unavailable for this workflow: {unavailable.join(", ")}. Clear tools and select from the current list before saving.</p> : null}
      <div className="prompt-reference-filters">
        <label htmlFor={searchId}><span>Search tools</span><input id={searchId} type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or purpose" /></label>
        <span role="status">{selected.length} of {tools.length} enabled</span>
        <button className="text-action" type="button" onClick={() => onChange(tools.map((tool) => tool.name))}>Enable all</button>
        <button className="text-action" type="button" onClick={() => onChange([])}>Clear tools</button>
      </div>
      {filtered.length ? <div className="prompt-tool-list">
        {filtered.map((tool) => (
          <div className="prompt-tool-row" key={tool.name}>
            <label>
              <input type="checkbox" checked={selected.includes(tool.name)} onChange={(event) => onChange(event.target.checked ? [...selected, tool.name].sort() : selected.filter((name) => name !== tool.name))} />
              <span><strong>{tool.name}</strong><small>{tool.description}</small></span>
            </label>
            <details className="prompt-input-shape">
              <summary>Inputs and result for {tool.name}</summary>
              {tool.default_behavior ? <p>{tool.default_behavior}</p> : null}
              <h3>Inputs</h3><pre>{JSON.stringify(tool.input_schema, null, 2)}</pre>
              {tool.result_schema ? <><h3>Result schema</h3><pre>{JSON.stringify(tool.result_schema, null, 2)}</pre></> : null}
              {tool.example !== undefined ? <><h3>Synthetic result example</h3><pre>{JSON.stringify(tool.example, null, 2)}</pre></> : null}
            </details>
          </div>
        ))}
      </div> : <div className="empty-state compact">No tools match this search.</div>}
      {selected.length === 0 ? <p className="prompt-editor-note">No tools enabled. Include the context needed through variables in your prompts.</p> : null}
    </fieldset>
  );
}
