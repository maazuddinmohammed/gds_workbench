import type { TenantRole } from "./api";

export function roleLabel(role: TenantRole): string {
  const labels: Record<TenantRole, string> = {
    viewer: "Viewer",
    developer: "Developer",
    architect: "Architect",
    tenant_admin: "Tenant Admin",
    super_admin: "Super Admin",
  };
  return labels[role];
}

export function canAuthorModels(role: TenantRole): boolean {
  return role === "architect" || role === "tenant_admin" || role === "super_admin";
}
