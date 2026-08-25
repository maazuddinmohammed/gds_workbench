import { useState, type ReactNode } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import {
  acquireTenantLockErrorMessage,
  overrideTenantLockErrorMessage,
  releaseTenantLockErrorMessage,
  renewTenantLockErrorMessage,
  tenantHomeQueryKey,
  tenantLockHistoryQueryKey,
  type AcquireTenantLockCommand,
  type OverrideTenantLockCommand,
  type RenewTenantLockCommand,
  type TenantLockActions,
  type TenantLockApi,
  type TenantLockHistoryEventType,
  type TenantLockState,
} from "./api";

export function TenantLockFocus({
  actions,
  api,
  lock,
  tenantId,
  tenantName,
}: {
  actions: TenantLockActions;
  api: TenantLockApi;
  lock: TenantLockState;
  tenantId: number;
  tenantName: string;
}) {
  const queryClient = useQueryClient();
  const [releaseConfirmationOpen, setReleaseConfirmationOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const status = !lock.is_locked
    ? "Tenant is unlocked"
    : lock.owned_by_current_principal
      ? "Locked by you"
      : "Locked by another Principal";
  const acquireMutation = useMutation({
    mutationFn: (command: AcquireTenantLockCommand) => api.acquireTenantLock(tenantId, command),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tenantHomeQueryKey(tenantId) }),
  });
  const renewMutation = useMutation({
    mutationFn: (command: RenewTenantLockCommand) => api.renewTenantLock(tenantId, command),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tenantHomeQueryKey(tenantId) }),
  });
  const releaseMutation = useMutation({
    mutationFn: () => api.releaseTenantLock(tenantId),
    onSuccess: () => {
      setReleaseConfirmationOpen(false);
      return queryClient.invalidateQueries({ queryKey: tenantHomeQueryKey(tenantId) });
    },
  });
  const overrideMutation = useMutation({
    mutationFn: (command: OverrideTenantLockCommand) => api.overrideTenantLock(tenantId, command),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tenantHomeQueryKey(tenantId) }),
  });
  const historyQuery = useInfiniteQuery({
    queryKey: tenantLockHistoryQueryKey(tenantId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => api.listTenantLockHistory(tenantId, pageParam ?? undefined),
    enabled: historyOpen,
    getNextPageParam: (lastPage, _pages, _lastPageParam, pageParams) => {
      const cursor = lastPage.next_cursor;
      return cursor && !pageParams.includes(cursor) ? cursor : undefined;
    },
  });
  const acquireForm = useForm({
    defaultValues: {
      durationMinutes: "60",
      purpose: "",
    },
    onSubmit: ({ value }) => {
      acquireMutation.reset();
      acquireMutation.mutate({
        duration_minutes: Number(value.durationMinutes),
        purpose: value.purpose.trim() || null,
      });
    },
  });
  const acquireFormValues = useStore(acquireForm.store, (state) => state.values);
  const acquireDuration = Number(acquireFormValues.durationMinutes);
  const acquireFormIsValid = Number.isSafeInteger(acquireDuration)
    && acquireDuration >= 1
    && acquireDuration <= 240
    && acquireFormValues.purpose.trim().length <= 500;
  const renewForm = useForm({
    defaultValues: { durationMinutes: "60" },
    onSubmit: ({ value }) => {
      renewMutation.reset();
      renewMutation.mutate({ duration_minutes: Number(value.durationMinutes) });
    },
  });
  const renewDurationValue = useStore(renewForm.store, (state) => state.values.durationMinutes);
  const renewDuration = Number(renewDurationValue);
  const renewHelpId = `tenant-lock-renew-help-${tenantId}`;
  const renewFormIsValid = Number.isSafeInteger(renewDuration)
    && renewDuration >= 1
    && renewDuration <= 240;
  const overrideForm = useForm({
    defaultValues: { reason: "" },
    onSubmit: ({ value }) => {
      overrideMutation.reset();
      overrideMutation.mutate({ reason: value.reason.trim() });
    },
  });
  const overrideReason = useStore(overrideForm.store, (state) => state.values.reason);
  const overrideFormIsValid = overrideReason.trim().length >= 1
    && overrideReason.trim().length <= 2000;

  return (
    <section className="tenant-lock-focus" aria-labelledby="tenant-lock-heading">
      <header className="lock-heading">
        <div>
          <p className="eyebrow eyebrow-light">Governed write access</p>
          <h1 id="tenant-lock-heading">Tenant Lock</h1>
          <p>Controls protected changes for {tenantName}.</p>
        </div>
        <span className={`lock-status ${lock.is_locked ? "is-locked" : "is-open"}`}>
          {status}
        </span>
      </header>

      <div className="lock-details">
        <div className="lock-owner">
          <span className="avatar is-large">{initials(lock.owner_display_name ?? tenantName)}</span>
          <span>
            <span className="detail-label">Current owner</span>
            <strong>{lock.owner_display_name ?? "No current owner"}</strong>
            <span>{lock.is_locked ? "Governed access active" : "Available to acquire"}</span>
          </span>
        </div>
        <LockDetail label="Expires" value={formatDateTime(lock.expires_at) ?? "—"} />
        <LockDetail label="Purpose" value={lock.purpose ?? "—"} />
      </div>

      <div className="lock-actions">
        {actions.can_acquire ? (
          <>
            <form
              className="tenant-lock-form"
              onSubmit={(event) => {
                event.preventDefault();
                event.stopPropagation();
                if (acquireFormIsValid) void acquireForm.handleSubmit();
              }}
            >
              <acquireForm.Field name="durationMinutes">
                {(field) => (
                  <label>
                    <span>Duration (minutes)</span>
                    <input
                      aria-label="Duration (minutes)"
                      type="number"
                      min="1"
                      max="240"
                      step="1"
                      required
                      value={field.state.value}
                      onBlur={field.handleBlur}
                      onChange={(event) => field.handleChange(event.target.value)}
                    />
                    <small>1–240 whole minutes; the server checks this again.</small>
                  </label>
                )}
              </acquireForm.Field>
              <acquireForm.Field name="purpose">
                {(field) => (
                  <label className="tenant-lock-purpose-field">
                    <span>Purpose (optional)</span>
                    <input
                      aria-label="Purpose (optional)"
                      type="text"
                      maxLength={500}
                      value={field.state.value}
                      onBlur={field.handleBlur}
                      onChange={(event) => field.handleChange(event.target.value)}
                    />
                    <small>Up to 500 characters.</small>
                  </label>
                )}
              </acquireForm.Field>
              <button
                className="button button-primary"
                type="submit"
                disabled={!acquireFormIsValid || acquireMutation.isPending}
              >
                {acquireMutation.isPending ? "Acquiring…" : "Acquire Tenant Lock"}
              </button>
            </form>
            {acquireMutation.isError ? (
              <p className="tenant-lock-error" role="alert">
                {acquireTenantLockErrorMessage(acquireMutation.error)}
              </p>
            ) : null}
          </>
        ) : null}
        {actions.can_renew ? (
          <>
            <form
              className="tenant-lock-form tenant-lock-renew-form"
              onSubmit={(event) => {
                event.preventDefault();
                event.stopPropagation();
                if (renewFormIsValid) void renewForm.handleSubmit();
              }}
            >
              <renewForm.Field name="durationMinutes">
                {(field) => (
                  <label className="tenant-lock-renew-field">
                    <span>Extend duration (minutes)</span>
                    <input
                      aria-label="Extend duration (minutes)"
                      aria-describedby={renewHelpId}
                      type="number"
                      min="1"
                      max="240"
                      step="1"
                      required
                      value={field.state.value}
                      onBlur={field.handleBlur}
                      onChange={(event) => field.handleChange(event.target.value)}
                    />
                  </label>
                )}
              </renewForm.Field>
              <small id={renewHelpId} className="tenant-lock-renew-help">
                1–240 whole minutes from server time; the server checks this again.
              </small>
              <button
                className="button button-primary"
                type="submit"
                disabled={!renewFormIsValid || renewMutation.isPending}
              >
                {renewMutation.isPending ? "Extending…" : "Extend Tenant Lock"}
              </button>
            </form>
            {renewMutation.isError ? (
              <p className="tenant-lock-error" role="alert">
                {renewTenantLockErrorMessage(renewMutation.error)}
              </p>
            ) : null}
          </>
        ) : null}
        {actions.can_release ? (
          <div className="tenant-lock-release-action">
            {releaseConfirmationOpen ? (
              <div
                className="tenant-lock-release-confirmation"
                role="group"
                aria-label="Confirm Tenant Lock release"
              >
                <p>
                  <strong>Release your Tenant Lock?</strong>
                  <span> Protected changes will require another explicit acquisition.</span>
                </p>
                <div>
                  <button
                    className="button button-secondary"
                    type="button"
                    disabled={releaseMutation.isPending}
                    onClick={() => {
                      releaseMutation.reset();
                      setReleaseConfirmationOpen(false);
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    className="button tenant-lock-destructive-button"
                    type="button"
                    disabled={releaseMutation.isPending}
                    onClick={() => releaseMutation.mutate()}
                  >
                    {releaseMutation.isPending ? "Releasing…" : "Confirm release"}
                  </button>
                </div>
              </div>
            ) : (
              <button
                className="button button-secondary"
                type="button"
                onClick={() => {
                  releaseMutation.reset();
                  setReleaseConfirmationOpen(true);
                }}
              >
                Release Tenant Lock
              </button>
            )}
            {releaseMutation.isError ? (
              <p className="tenant-lock-error" role="alert">
                {releaseTenantLockErrorMessage(releaseMutation.error)}
              </p>
            ) : null}
          </div>
        ) : null}
        {actions.can_override ? (
          <div className="tenant-lock-override-action">
            <div
              className="tenant-lock-override-warning"
              role="note"
              aria-label="Tenant Lock override warning"
            >
              <strong>Revoke another Principal’s Tenant Lock?</strong>
              <span>
                This force-releases the lock and records your reason. It does not acquire the
                Tenant Lock for you.
              </span>
            </div>
            <form
              className="tenant-lock-form tenant-lock-override-form"
              onSubmit={(event) => {
                event.preventDefault();
                event.stopPropagation();
                if (overrideFormIsValid) void overrideForm.handleSubmit();
              }}
            >
              <overrideForm.Field name="reason">
                {(field) => (
                  <label>
                    <span>Override reason</span>
                    <textarea
                      aria-label="Override reason"
                      maxLength={2000}
                      required
                      rows={3}
                      value={field.state.value}
                      onBlur={field.handleBlur}
                      onChange={(event) => field.handleChange(event.target.value)}
                    />
                    <small>Required; up to 2,000 characters. The server checks this again.</small>
                  </label>
                )}
              </overrideForm.Field>
              <button
                className="button tenant-lock-destructive-button"
                type="submit"
                disabled={!overrideFormIsValid || overrideMutation.isPending}
              >
                {overrideMutation.isPending ? "Revoking…" : "Revoke Tenant Lock"}
              </button>
            </form>
            {overrideMutation.isError ? (
              <p className="tenant-lock-error" role="alert">
                {overrideTenantLockErrorMessage(overrideMutation.error)}
              </p>
            ) : null}
          </div>
        ) : null}
        {!actions.can_acquire
          && !actions.can_renew
          && !actions.can_release
          && !actions.can_override ? (
          <p>No Tenant Lock action is available for the current server-owned state.</p>
        ) : null}
      </div>

      <div className="tenant-lock-history-control">
        <button
          className="button button-secondary"
          type="button"
          aria-controls="tenant-lock-history"
          aria-expanded={historyOpen}
          onClick={() => setHistoryOpen((open) => !open)}
        >
          {historyOpen ? "Close history" : "View history"}
        </button>
      </div>

      {historyOpen ? (
        <section
          id="tenant-lock-history"
          className="tenant-lock-history"
          aria-labelledby="tenant-lock-history-heading"
        >
          <header>
            <div>
              <p className="eyebrow eyebrow-light">Audit trail</p>
              <h2 id="tenant-lock-history-heading">Tenant Lock history</h2>
            </div>
          </header>

          {historyQuery.isPending ? <p>Loading Tenant Lock history…</p> : null}
          {historyQuery.isError ? (
            <p className="tenant-lock-error" role="alert">
              Tenant Lock history could not be loaded. Close and try again.
            </p>
          ) : null}
          {historyQuery.data ? (
            historyQuery.data.pages.every((page) => page.items.length === 0) ? (
              <p>No Tenant Lock history events are available.</p>
            ) : (
              <ol className="tenant-lock-history-list">
                {historyQuery.data.pages.flatMap((page) => page.items).map((event) => (
                  <li key={event.event_id}>
                    <header>
                      <strong>{historyEventLabel(event.event_type)}</strong>
                    </header>
                    <dl>
                      <div><dt>Owner</dt><dd>{event.owner_display_name}</dd></div>
                      <div><dt>Actor</dt><dd>{event.actor_display_name ?? "System"}</dd></div>
                      <div><dt>Reason</dt><dd>{event.reason?.slice(0, 2000) || "—"}</dd></div>
                      <div><dt>Acquired</dt><dd>{formatDateTime(event.acquired_at) ?? "—"}</dd></div>
                      <div><dt>Expires</dt><dd>{formatDateTime(event.expires_at) ?? "—"}</dd></div>
                      <div><dt>Created</dt><dd>{formatDateTime(event.created_at) ?? "—"}</dd></div>
                    </dl>
                  </li>
                ))}
              </ol>
            )
          ) : null}

          {historyQuery.hasNextPage ? (
            <button
              className="button button-secondary"
              type="button"
              disabled={historyQuery.isFetchingNextPage}
              onClick={() => void historyQuery.fetchNextPage()}
            >
              {historyQuery.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function LockDetail({ label, value }: { label: string; value: ReactNode }) {
  return (
    <span className="lock-detail">
      <span className="detail-label">{label}</span>
      <strong>{value}</strong>
    </span>
  );
}

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase() ?? "")
    .join("") || "G";
}

function formatDateTime(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function historyEventLabel(eventType: TenantLockHistoryEventType): string {
  switch (eventType) {
    case "acquired": return "Acquired";
    case "renewed": return "Renewed";
    case "released": return "Released";
    case "force_unlocked": return "Force unlocked";
    case "expired": return "Expired";
  }
}
