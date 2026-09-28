import { useEffect, useId, useRef, useState } from "react";

export function MultiSelectField({ label, options, value, onChange, emptyLabel = "All Objects" }: {
  label: string; options: [string, string][]; value: string[];
  onChange: (value: string[]) => void; emptyLabel?: string;
}) {
  const id = useId();
  const details = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const [search, setSearch] = useState("");
  const shown = options.filter(([, text]) => text.toLowerCase().includes(search.trim().toLowerCase()));
  const selectedLabel = options.find(([key]) => key === value[0])?.[1];
  useEffect(() => {
    const dismissOutside = (event: PointerEvent) => {
      const menu = details.current;
      if (!menu?.open || !(event.target instanceof Node) || menu.contains(event.target)) return;
      // Avoid leaving focus on a checkbox after its menu becomes hidden.
      if (menu.contains(document.activeElement)) summary.current?.focus();
      menu.open = false;
    };
    document.addEventListener("pointerdown", dismissOutside);
    return () => document.removeEventListener("pointerdown", dismissOutside);
  }, []);
  return <div className="multi-select-field">
    <span id={id}>{label}</span>
    <details ref={details} onKeyDown={(event) => {
      if (event.key === "Escape" && details.current?.open) {
        event.stopPropagation(); details.current.open = false; summary.current?.focus();
      }
    }} onBlur={(event) => {
      // Clicking a label briefly blurs to null before focusing its checkbox.
      if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget) && details.current) details.current.open = false;
    }}>
      <summary ref={summary} aria-labelledby={`${id} ${id}-value`}><span id={`${id}-value`}>
        {value.length === 1 ? selectedLabel ?? value[0] : value.length ? `${value.length} selected` : emptyLabel}
      </span></summary>
      <div className="multi-select-options">
        <label className="multi-select-search"><span className="sr-only">Find {label}</span><input type="search" aria-label={`Find ${label}`} placeholder={`Find ${label.toLowerCase()}…`} value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => {
          if (event.key === "Enter") event.preventDefault();
        }} /></label>
        <div className="multi-select-actions">
          <button type="button" className="text-action" onClick={() => onChange([...new Set([...value, ...shown.map(([key]) => key)])])}>Select all shown</button>
          <button type="button" className="text-action" onClick={() => onChange([])}>Clear selection</button>
        </div>
        <div role="group" aria-label={`${label} options`}>
          {shown.map(([key, text]) => <label key={key} className={value.includes(key) ? "is-selected" : undefined}><input type="checkbox" checked={value.includes(key)} onChange={(event) => onChange(event.target.checked ? [...value, key] : value.filter((item) => item !== key))} /><span>{text}</span></label>)}
          {!shown.length ? <p>No matches.</p> : null}
        </div>
        <div className="multi-select-footer"><span>{value.length} selected</span><button type="button" className="text-action" onClick={() => {
          if (details.current) details.current.open = false;
          summary.current?.focus();
        }}>Done</button></div>
      </div>
    </details>
  </div>;
}
