import { useEffect, type KeyboardEvent, type RefObject } from "react";

export function useDialogFocus(initialFocus: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const previousFocus = document.activeElement;
    initialFocus.current?.focus();
    return () => { if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus(); };
  }, [initialFocus]);
}

export function trapDialogFocus(event: KeyboardEvent<HTMLElement>) {
  if (event.key !== "Tab") return;
  const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("*")).filter((element) => {
    if (element.tabIndex < 0 || element.matches(":disabled") || element.closest("[hidden]")) return false;
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      if (parent.matches("details:not([open])") && element !== parent.querySelector("summary")) return false;
    }
    return true;
  });
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
}
