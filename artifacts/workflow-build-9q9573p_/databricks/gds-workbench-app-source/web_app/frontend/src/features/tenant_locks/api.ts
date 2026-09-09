import type { HttpRequest } from "../../core/http";

export interface TenantLockState {
  is_locked: boolean;
  owner_display_name: string | null;
  owned_by_current_principal: boolean | null;
  purpose: string | null;
  acquired_at: string | null;
  expires_at: string | null;
}

export interface TenantLockActions {
  can_acquire: boolean;
  can_renew: boolean;
  can_release: boolean;
  can_override: boolean;
}

export interface AcquireTenantLockCommand {
  duration_minutes: number;
  purpose: string | null;
}

export interface AcquiredTenantLock {
  owner_display_name: string;
  owned_by_current_principal: true;
  purpose: string | null;
  acquired_at: string;
  expires_at: string;
}

export interface AcquireTenantLockResult {
  tenant_id: number;
  action: "acquired";
  lock: AcquiredTenantLock;
  previous_lock: null;
}

export interface RenewTenantLockCommand {
  duration_minutes: number;
}

export interface RenewTenantLockResult {
  tenant_id: number;
  action: "renewed";
  lock: AcquiredTenantLock;
  previous_lock: null;
}

export interface ReleaseTenantLockResult {
  tenant_id: number;
  action: "released";
  lock: null;
  previous_lock: null;
}

export interface OverrideTenantLockCommand {
  reason: string;
}

export interface OverriddenTenantLock {
  owner_display_name: string;
  owned_by_current_principal: false;
  purpose: string | null;
  acquired_at: string;
  expires_at: string;
}

export interface OverrideTenantLockResult {
  tenant_id: number;
  action: "overridden";
  lock: null;
  previous_lock: OverriddenTenantLock;
}

export type TenantLockHistoryEventType =
  | "acquired"
  | "renewed"
  | "released"
  | "force_unlocked"
  | "expired";

export interface TenantLockHistoryEvent {
  event_id: number;
  event_type: TenantLockHistoryEventType;
  owner_display_name: string;
  actor_display_name: string | null;
  reason: string | null;
  acquired_at: string;
  expires_at: string;
  created_at: string;
}

export interface TenantLockHistoryPage {
  tenant_id: number;
  items: TenantLockHistoryEvent[];
  next_cursor: string | null;
}

export interface TenantLockApi {
  acquireTenantLock: (
    tenantId: number,
    command: AcquireTenantLockCommand,
  ) => Promise<AcquireTenantLockResult>;
  renewTenantLock: (
    tenantId: number,
    command: RenewTenantLockCommand,
  ) => Promise<RenewTenantLockResult>;
  releaseTenantLock: (tenantId: number) => Promise<ReleaseTenantLockResult>;
  overrideTenantLock: (
    tenantId: number,
    command: OverrideTenantLockCommand,
  ) => Promise<OverrideTenantLockResult>;
  listTenantLockHistory: (
    tenantId: number,
    cursor?: string,
  ) => Promise<TenantLockHistoryPage>;
}

export function createTenantLockApi(request: HttpRequest): TenantLockApi {
  return {
    acquireTenantLock: (tenantId, command) =>
      request<AcquireTenantLockResult>(`/api/v1/tenants/${tenantId}/lock/acquire`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(command),
      }),
    renewTenantLock: (tenantId, command) =>
      request<RenewTenantLockResult>(`/api/v1/tenants/${tenantId}/lock/renew`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(command),
      }),
    releaseTenantLock: (tenantId) =>
      request<ReleaseTenantLockResult>(`/api/v1/tenants/${tenantId}/lock/release`, {
        method: "POST",
      }),
    overrideTenantLock: (tenantId, command) =>
      request<OverrideTenantLockResult>(`/api/v1/tenants/${tenantId}/lock/override`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(command),
      }),
    listTenantLockHistory: (tenantId, cursor) => {
      const query = new URLSearchParams({ page_size: "50" });
      if (cursor) query.set("cursor", cursor);
      return request<TenantLockHistoryPage>(
        `/api/v1/tenants/${tenantId}/lock/history?${query}`,
      );
    },
  };
}

const ACQUIRE_ERROR_MESSAGES: Readonly<Record<string, string>> = {
  authorization_denied: "You are not authorized to acquire this Tenant Lock.",
  dependency_unavailable: "Tenant Lock service is temporarily unavailable. Try again later.",
  invalid_request: "Tenant Lock request is invalid. Review the duration and purpose.",
  tenant_locked: "Another Principal currently owns this Tenant Lock. Refresh for current state.",
  tenant_not_found: "This Tenant is no longer available. Return to Tenant selection.",
};

const RENEW_ERROR_MESSAGES: Readonly<Record<string, string>> = {
  authorization_denied: "You are not authorized to extend this Tenant Lock.",
  dependency_unavailable: "Tenant Lock service is temporarily unavailable. Try again later.",
  invalid_request: "Tenant Lock extension is invalid. Review the duration and try again.",
  tenant_locked: "Another Principal currently owns this Tenant Lock. Refresh for current state.",
  tenant_lock_required: "Your active Tenant Lock is no longer available. Refresh for current state.",
  tenant_not_found: "This Tenant is no longer available. Return to Tenant selection.",
};

const RELEASE_ERROR_MESSAGES: Readonly<Record<string, string>> = {
  authorization_denied: "You are not authorized to release this Tenant Lock.",
  dependency_unavailable: "Tenant Lock service is temporarily unavailable. Try again later.",
  tenant_locked: "Another Principal currently owns this Tenant Lock. Refresh for current state.",
  tenant_lock_required: "Your active Tenant Lock is no longer available. Refresh for current state.",
  tenant_not_found: "This Tenant is no longer available. Return to Tenant selection.",
};

const OVERRIDE_ERROR_MESSAGES: Readonly<Record<string, string>> = {
  authorization_denied: "You are not authorized to revoke this Tenant Lock.",
  dependency_unavailable: "Tenant Lock service is temporarily unavailable. Try again later.",
  invalid_request: "Tenant Lock state changed or the override reason is invalid. Refresh and try again.",
  tenant_locked: "Tenant Lock ownership changed. Refresh for current state.",
  tenant_lock_required: "The Tenant Lock is no longer active. Refresh for current state.",
  tenant_not_found: "This Tenant is no longer available. Return to Tenant selection.",
};

export function acquireTenantLockErrorMessage(error: unknown): string {
  const code = errorCode(error);
  return (code ? ACQUIRE_ERROR_MESSAGES[code] : undefined)
    ?? "Tenant Lock could not be acquired. Refresh and try again.";
}

export function renewTenantLockErrorMessage(error: unknown): string {
  const code = errorCode(error);
  return (code ? RENEW_ERROR_MESSAGES[code] : undefined)
    ?? "Tenant Lock could not be extended. Refresh and try again.";
}

export function releaseTenantLockErrorMessage(error: unknown): string {
  const code = errorCode(error);
  return (code ? RELEASE_ERROR_MESSAGES[code] : undefined)
    ?? "Tenant Lock could not be released. Refresh and try again.";
}

export function overrideTenantLockErrorMessage(error: unknown): string {
  const code = errorCode(error);
  return (code ? OVERRIDE_ERROR_MESSAGES[code] : undefined)
    ?? "Tenant Lock could not be revoked. Refresh and try again.";
}

function errorCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("code" in error)) return null;
  return typeof error.code === "string" ? error.code : null;
}

export function tenantHomeQueryKey(tenantId: number) {
  return ["tenant-home", tenantId] as const;
}

export function tenantLockHistoryQueryKey(tenantId: number) {
  return ["tenant-lock-history", tenantId] as const;
}
