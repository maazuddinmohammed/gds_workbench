// THROWAWAY prototype helpers: the Cards / Current table switch and card count wording.
import { useSyncExternalStore } from "react";

type Layout = "cards" | "table";

const storageKey = "atlas-prototype-subject-area-layout";
const listeners = new Set<() => void>();
let layout: Layout = readLayout();

function readLayout(): Layout {
  try {
    return localStorage.getItem(storageKey) === "table" ? "table" : "cards";
  } catch {
    return "cards";
  }
}

function setLayout(next: Layout) {
  layout = next;
  try {
    localStorage.setItem(storageKey, next);
  } catch {
    // The choice still applies until the page reloads.
  }
  listeners.forEach((listener) => listener());
}

export function useSubjectAreaLayout(): Layout {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, () => layout);
}

export function LayoutSwitch() {
  const current = useSubjectAreaLayout();
  return <div className="prototype-switch" role="group" aria-label="Prototype: how Subject Areas are shown">
    {(["cards", "table"] as const).map((value) => <button key={value} type="button" aria-pressed={current === value}
      className={current === value ? "is-active" : ""} onClick={() => setLayout(value)}>
      {value === "cards" ? "Cards" : "Current table"}
    </button>)}
  </div>;
}

export function countLabel(value: number, one: string, many: string): string {
  return `${value.toLocaleString()} ${value === 1 ? one : many}`;
}
