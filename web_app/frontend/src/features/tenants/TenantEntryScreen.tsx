import { useEffect, useMemo, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery } from "@tanstack/react-query";

import { shortCode } from "../../shared/presentation";
import { Avatar, Brand, ErrorPage, LoadingPage, SearchIcon } from "../../shared/ui";
import type { TenantsApi } from "./api";
import { roleLabel } from "./presentation";

type TenantEntryApi = Pick<
  TenantsApi,
  "listTenants" | "readSession" | "selectTenant"
>;

export function TenantEntryScreen({
  api,
  onTenantEntered,
}: {
  api: TenantEntryApi;
  onTenantEntered: (tenantId: number) => Promise<void>;
}) {
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(null);
  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: api.readSession,
  });
  const tenantsQuery = useQuery({
    queryKey: ["tenants"],
    queryFn: api.listTenants,
  });
  const searchForm = useForm({ defaultValues: { search: "" } });
  const search = useStore(searchForm.store, (state) => state.values.search);
  const selectMutation = useMutation({
    mutationFn: api.selectTenant,
    onSuccess: async ({ tenant_id }) => onTenantEntered(tenant_id),
  });

  const tenants = tenantsQuery.data?.items;
  useEffect(() => {
    if (!tenants?.length) {
      setSelectedTenantId(null);
      return;
    }

    setSelectedTenantId((current) => {
      if (current && tenants.some((tenant) => tenant.tenant_id === current)) return current;
      const lastTenantId = sessionQuery.data?.last_tenant_id;
      return tenants.find((tenant) => tenant.tenant_id === lastTenantId)?.tenant_id
        ?? tenants[0]?.tenant_id
        ?? null;
    });
  }, [sessionQuery.data?.last_tenant_id, tenants]);

  const filteredTenants = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    if (!term) return tenants ?? [];
    return (tenants ?? []).filter((tenant) =>
      `${tenant.tenant_name} ${tenant.tenant_code} ${tenant.tenant_description ?? ""}`
        .toLocaleLowerCase()
        .includes(term),
    );
  }, [search, tenants]);

  useEffect(() => {
    if (!search.trim()) return;
    if (filteredTenants.some((tenant) => tenant.tenant_id === selectedTenantId)) return;
    setSelectedTenantId(filteredTenants[0]?.tenant_id ?? null);
  }, [filteredTenants, search, selectedTenantId]);

  const selectedTenant = tenants?.find((tenant) => tenant.tenant_id === selectedTenantId);

  if (sessionQuery.isPending || tenantsQuery.isPending) {
    return <LoadingPage label="Loading available workspaces" />;
  }
  if (sessionQuery.isError || tenantsQuery.isError) {
    return <ErrorPage />;
  }

  return (
    <div className="entry-shell page-enter">
      <header className="entry-topbar">
        <Brand />
        <div className="signed-in">
          <span>Signed in as</span>
          <strong>{sessionQuery.data.display_name}</strong>
          <Avatar name={sessionQuery.data.display_name} />
        </div>
      </header>

      <main className="tenant-entry">
        <section className="tenant-entry-heading" aria-labelledby="tenant-entry-title">
          <p className="eyebrow">Available workspaces</p>
          <h1 id="tenant-entry-title">Choose a Tenant</h1>
        </section>

        <div className="tenant-search-row">
          <searchForm.Field name="search">
            {(field) => (
              <label className="search-field">
                <span className="sr-only">Search Tenants</span>
                <SearchIcon />
                <input
                  aria-label="Search Tenants"
                  type="search"
                  placeholder="Search Tenants by name or code"
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
              </label>
            )}
          </searchForm.Field>
          <span className="result-count">{filteredTenants.length} available</span>
        </div>

        {filteredTenants.length ? (
          <section className="tenant-grid" aria-label="Available Tenants">
            {filteredTenants.map((tenant) => (
              <button
                className="tenant-card"
                key={tenant.tenant_id}
                type="button"
                aria-pressed={selectedTenantId === tenant.tenant_id}
                onClick={() => setSelectedTenantId(tenant.tenant_id)}
              >
                <span className="tenant-code-mark">{shortCode(tenant.tenant_code)}</span>
                <span className="tenant-card-copy">
                  <span className="tenant-name-line">
                    <strong>{tenant.tenant_name}</strong>
                    {sessionQuery.data.last_tenant_id === tenant.tenant_id ? (
                      <span className="badge badge-success">Last accessed</span>
                    ) : null}
                  </span>
                  <span className="tenant-code-line">
                    {tenant.tenant_code} · {tenant.tenant_visibility === "global" ? "Global" : "Private"}
                  </span>
                  <span className="tenant-card-meta">{roleLabel(tenant.effective_role)}</span>
                </span>
                <span className="tenant-card-indicator" aria-hidden="true">
                  {selectedTenantId === tenant.tenant_id ? "✓" : "→"}
                </span>
              </button>
            ))}
          </section>
        ) : (
          <div className="empty-state">No Tenants match this filter.</div>
        )}

        <footer className="tenant-entry-footer">
          <div>
            <strong>{selectedTenant?.tenant_name ?? "Choose a Tenant"}</strong>
            <span>
              {selectedTenant
                ? `${roleLabel(selectedTenant.effective_role)} · ${selectedTenant.tenant_code}`
                : "Select a workspace to continue"}
            </span>
          </div>
          <button
            className="button button-primary button-enter"
            type="button"
            disabled={!selectedTenantId || selectMutation.isPending}
            onClick={() => {
              if (selectedTenantId) selectMutation.mutate(selectedTenantId);
            }}
          >
            {selectMutation.isPending ? "Entering…" : "Enter Workbench"}
            <span aria-hidden="true">→</span>
          </button>
        </footer>
        {selectMutation.isError ? (
          <p className="inline-error" role="alert">The workspace could not be opened.</p>
        ) : null}
      </main>
    </div>
  );
}
