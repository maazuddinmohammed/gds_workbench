import { useEffect, useRef, useState } from "react";
import type { TenantHomeRecord } from "../tenants/api";
import type { TenantLockApi } from "./api";
import { TenantLockFocus } from "./TenantLockFocus";

export function TenantLockControl({ api, home }: { api: TenantLockApi; home: TenantHomeRecord }) {
  const [open, setOpen] = useState(false);
  const label = home.lock.owned_by_current_principal ? "Tenant Lock held by you"
    : home.lock.is_locked ? `Tenant Lock held by ${home.lock.owner_display_name ?? "another Principal"}`
      : "Tenant Lock required";
  return <>
    <button type="button" className={`model-lock model-lock-control${home.lock.owned_by_current_principal ? " is-held" : ""}`}
      aria-label="Manage Tenant Lock" aria-haspopup="dialog" onClick={() => setOpen(true)}>
      <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" /></svg>
      {label}<span aria-hidden="true">⌄</span>
    </button>
    {open ? <TenantLockDialog api={api} home={home} onClose={() => setOpen(false)} /> : null}
  </>;
}

function TenantLockDialog({ api, home, onClose }: { api: TenantLockApi; home: TenantHomeRecord; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current?.showModal();
    return () => { if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, []);
  return <dialog ref={dialog} className="tenant-lock-dialog" aria-label="Manage Tenant Lock"
    onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <button className="panel-close" type="button" aria-label="Close Tenant Lock" onClick={onClose}>×</button>
    <TenantLockFocus api={api} actions={home.lock_actions} lock={home.lock}
      tenantId={home.tenant.tenant_id} tenantName={home.tenant.tenant_name} />
  </dialog>;
}
