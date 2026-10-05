import { useEffect, useId, useRef, useState } from "react";

import { trapDialogFocus } from "../../shared/dialog";

export function PromptTextEditor({
  label, value, readOnly = false, disabled = false, onChange, onBlur, onFocus, editorRef,
}: {
  label: string;
  value: string;
  readOnly?: boolean;
  disabled?: boolean;
  onChange?: (value: string) => void;
  onBlur?: () => void;
  onFocus?: () => void;
  editorRef?: (element: HTMLTextAreaElement) => void;
}) {
  const id = useId();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (!expanded) return;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    textarea.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, [expanded]);

  return (
    <>
      {expanded ? <div className="prompt-editor-backdrop" aria-hidden="true" /> : null}
      <section
        className={`prompt-text-editor${expanded ? " is-expanded" : ""}`}
        role={expanded ? "dialog" : undefined}
        aria-modal={expanded ? true : undefined}
        aria-label={expanded ? `Expanded ${label}` : undefined}
        onKeyDown={(event) => {
          if (!expanded) return;
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            setExpanded(false);
          }
          trapDialogFocus(event);
        }}
      >
        <header>
          <label htmlFor={id}>{label}</label>
          <button
            type="button"
            className="text-action"
            aria-label={`${expanded ? "Collapse" : "Expand"} ${label}`}
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "Done" : "Expand"}
          </button>
        </header>
        <textarea
          id={id}
          aria-label={readOnly ? `${label} immutable` : label}
          ref={(element) => {
            textarea.current = element;
            if (element) editorRef?.(element);
          }}
          value={value}
          readOnly={readOnly}
          disabled={disabled}
          spellCheck={false}
          autoComplete="off"
          onChange={(event) => onChange?.(event.target.value)}
          onBlur={onBlur}
          onFocus={onFocus}
        />
      </section>
    </>
  );
}
