import { describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient } from "./api";

describe("Workbench API client", () => {
  it("uses only the same-origin tenant entry routes", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({
        display_name: "Maaz",
        actor_kind: "human",
        is_super_admin: false,
        last_tenant_id: 7,
      }))
      .mockResolvedValueOnce(jsonResponse({ items: [], next_cursor: null }))
      .mockResolvedValueOnce(jsonResponse({ tenant_id: 7 }))
      .mockResolvedValueOnce(jsonResponse(tenantHomePayload));
    const api = createApiClient(fetcher);

    await api.readSession();
    await api.listTenants();
    await api.selectTenant(7);
    await api.readTenantHome(7);

    expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
      "/api/v1/session",
      "/api/v1/tenants?page_size=200",
      "/api/v1/tenants/7/select",
      "/api/v1/tenants/7/home",
    ]);
    expect(fetcher.mock.calls[2]?.[1]?.method).toBe("POST");
  });

  it("posts only explicit lease inputs to the tenant-nested acquire route", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      tenant_id: 7,
      action: "acquired",
      lock: {
        owner_display_name: "Maaz",
        owned_by_current_principal: true,
        purpose: "Metadata review",
        acquired_at: "2026-08-24T14:00:00Z",
        expires_at: "2026-08-24T15:30:00Z",
      },
      previous_lock: null,
    }));

    await createApiClient(fetcher).acquireTenantLock(7, {
      duration_minutes: 90,
      purpose: "Metadata review",
    });

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/lock/acquire",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        headers: expect.objectContaining({ "content-type": "application/json" }),
        body: JSON.stringify({
          duration_minutes: 90,
          purpose: "Metadata review",
        }),
      }),
    );
    expect(String(fetcher.mock.calls[0]?.[1]?.body)).not.toMatch(
      /actor|principal|role|policy/i,
    );
  });

  it("posts only the explicit duration to the tenant-nested renew route", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      tenant_id: 7,
      action: "renewed",
      lock: {
        owner_display_name: "Maaz",
        owned_by_current_principal: true,
        purpose: "Metadata review",
        acquired_at: "2026-08-24T15:00:00Z",
        expires_at: "2026-08-24T17:00:00Z",
      },
      previous_lock: null,
    }));

    await createApiClient(fetcher).renewTenantLock(7, { duration_minutes: 120 });

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/lock/renew",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        headers: expect.objectContaining({ "content-type": "application/json" }),
        body: JSON.stringify({ duration_minutes: 120 }),
      }),
    );
    expect(String(fetcher.mock.calls[0]?.[1]?.body)).not.toMatch(
      /actor|principal|purpose|role|policy/i,
    );
  });

  it("posts no body to the tenant-nested release route", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      tenant_id: 7,
      action: "released",
      lock: null,
      previous_lock: null,
    }));

    await createApiClient(fetcher).releaseTenantLock(7);

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/lock/release",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
      }),
    );
    const init = fetcher.mock.calls[0]?.[1];
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).has("content-type")).toBe(false);
  });

  it("posts only the explicit reason to the tenant-nested override route", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      tenant_id: 7,
      action: "overridden",
      lock: null,
      previous_lock: {
        owner_display_name: "Elena Morris",
        owned_by_current_principal: false,
        purpose: "Metadata review",
        acquired_at: "2026-08-24T14:00:00Z",
        expires_at: "2026-08-24T15:00:00Z",
      },
    }));

    await createApiClient(fetcher).overrideTenantLock(7, {
      reason: "Incident 4821 access recovery",
    });

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/lock/override",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        headers: expect.objectContaining({ "content-type": "application/json" }),
        body: JSON.stringify({ reason: "Incident 4821 access recovery" }),
      }),
    );
    expect(String(fetcher.mock.calls[0]?.[1]?.body)).not.toMatch(
      /actor|principal|role|policy|acquire/i,
    );
  });

  it("reads bounded Tenant Lock history pages from the tenant-nested route", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ tenant_id: 7, items: [], next_cursor: "opaque-next" }))
      .mockResolvedValueOnce(jsonResponse({ tenant_id: 7, items: [], next_cursor: null }));
    const api = createApiClient(fetcher);

    await api.listTenantLockHistory(7);
    await api.listTenantLockHistory(7, "opaque-next");

    expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
      "/api/v1/tenants/7/lock/history?page_size=50",
      "/api/v1/tenants/7/lock/history?page_size=50&cursor=opaque-next",
    ]);
  });

  it("returns a bounded error without exposing an unexpected response body", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response("secret physical row", { status: 500 }),
    );

    await expect(createApiClient(fetcher).readSession()).rejects.toEqual(
      expect.objectContaining<ApiError>({
        name: "ApiError",
        status: 500,
        code: "request_failed",
        correlationId: null,
        message: "The request could not be completed.",
      }),
    );
  });

  it("keeps Model and Scope reads tenant nested and normalizes Scope filters", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ items: [], next_cursor: null }))
      .mockResolvedValueOnce(jsonResponse({ model_id: 18 }))
      .mockResolvedValueOnce(jsonResponse({ model_id: 18, model_revision: 4, items: [], next_cursor: null }))
      .mockResolvedValueOnce(jsonResponse({ object_id: 501, attributes: [] }));
    const api = createApiClient(fetcher);

    await api.listModels(7, "active");
    await api.readModel(7, 18);
    await api.listModelScope(7, 18, {
      zone: " Bronze ",
      systemCode: " CRM ",
      sourceTenantCode: " GRDM ",
      objectName: " Customer_Raw ",
    });
    await api.readModelScopeObject(7, 18, 501);

    expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
      "/api/v1/tenants/7/models?status=active&page_size=200",
      "/api/v1/tenants/7/models/18",
      "/api/v1/tenants/7/models/18/scope?zone=bronze&system_code=crm&source_tenant_code=grdm&object_name=customer_raw&page_size=200",
      "/api/v1/tenants/7/models/18/scope/501",
    ]);
  });

  it("reads the authoritative workflow overview inside the Model route", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ model_id: 18, model_revision: 18, items: [] }),
    );

    await createApiClient(fetcher).readModelOverview(7, 18);

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/overview",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("uses governed Profiling read, run creation, execution, and event routes", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({ items: [] }));
    const api = createApiClient(fetcher);

    await api.listProfilingObjects(7, 18, {
      objectId: 501,
      sourceTenantCode: " GRDM ",
      systemCode: " CRM ",
      objectSchema: " Bronze_CRM ",
      objectName: " Customer_Raw ",
    });
    await api.readProfilingObject(7, 18, 501);
    await api.listWorkflowRuns(7, 18, "profiling", "running");
    await api.readWorkflowRun(7, 18, 1048);
    await api.listWorkflowRunEvents(7, 18, 1048, 7);
    await api.createProfilingRun(7, 18, {
      expected_model_revision: 4,
      model_workflow: "profiling",
      selected_object_ids: [501],
      requested_batch_id: null,
    }, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
    await api.executeProfilingRun(7, 18, 1048, 4);

    expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
      "/api/v1/tenants/7/models/18/profiling?object_id=501&source_tenant_code=grdm&system_code=crm&object_schema=bronze_crm&object_name=customer_raw&page_size=200",
      "/api/v1/tenants/7/models/18/profiling/501",
      "/api/v1/tenants/7/models/18/runs?workflow=profiling&page_size=200&state=running",
      "/api/v1/tenants/7/models/18/runs/1048",
      "/api/v1/tenants/7/models/18/runs/1048/events?after_sequence=7&page_size=200",
      "/api/v1/tenants/7/models/18/runs",
      "/api/v1/tenants/7/models/18/profiling/runs/1048/execute",
    ]);
    expect(fetcher.mock.calls[5]?.[1]).toEqual(expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({
        "Idempotency-Key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      }),
    }));
    expect(fetcher.mock.calls[6]?.[1]?.body).toBe(JSON.stringify({
      expected_model_revision: 4,
    }));
  });

  it("uses normalized Analysis review and shared workflow-run routes", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({ items: [] }));
    const api = createApiClient(fetcher);

    await api.listAnalysisFindings(7, 18, {
      objectId: 501,
      validationState: "unvalidated",
      showInactive: true,
    });
    await api.readAnalysisFinding(7, 18, 81);
    await api.readAgentCapabilities();
    await api.createWorkflowRun(7, 18, {
      expected_model_revision: 18,
      model_workflow: "analysis",
      workflow_execution_mode: "tool_assisted",
      selected_object_ids: [501],
      requested_batch_id: null,
      agent: {
        sdk_code: "openai_agents",
        provider_code: "databricks",
        model_code: "databricks-primary",
        reasoning_effort_code: "medium",
        max_turns: 8,
        validation_retry_count: 1,
      },
      prompt_overrides: {},
    }, "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");

    expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
      "/api/v1/tenants/7/models/18/analysis?object_id=501&validation_state=unvalidated&show_inactive=true&page_size=200",
      "/api/v1/tenants/7/models/18/analysis/81",
      "/api/v1/config/agent-capabilities",
      "/api/v1/tenants/7/models/18/runs",
    ]);
    expect(fetcher.mock.calls[3]?.[1]).toEqual(expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({
        "Idempotency-Key": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      }),
    }));
  });

  it("uses normalized Assertion Document and Record read routes", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({ items: [] }));
    const api = createApiClient(fetcher);

    await api.listAssertionDocuments(7, 18, {
      sourceSystemId: 2,
      sourceSystemCode: " CRM ",
      active: true,
      namePrefix: " Customer ",
    });
    await api.readAssertionDocument(7, 18, 31);
    await api.listAssertionRecords(7, 18, {
      documentId: 31,
      documentName: " Customer Rules ",
      sourceSystemId: 2,
      sourceSystemCode: " CRM ",
      status: "needs_review",
      locked: false,
      applicableLayer: "logical",
      keyPrefix: " Customer. ",
    });
    await api.readAssertionRecord(7, 18, 91);

    expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
      "/api/v1/tenants/7/models/18/assertions/documents?source_system_id=2&source_system_code=crm&active=true&name_prefix=customer&page_size=200",
      "/api/v1/tenants/7/models/18/assertions/documents/31",
      "/api/v1/tenants/7/models/18/assertions/records?document_id=31&document_name=customer+rules&source_system_id=2&source_system_code=crm&status=needs_review&locked=false&applicable_layer=logical&key_prefix=customer.&page_size=200",
      "/api/v1/tenants/7/models/18/assertions/records/91",
    ]);
  });

  it("uses the governed Metadata registry, typed filters, and XLSX export", async () => {
    const workbook = new Uint8Array([80, 75, 3, 4]);
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", datasets: [] }))
      .mockResolvedValueOnce(jsonResponse({
        schema_version: "1.0",
        dataset: "source_object",
        row_schema: { properties: { tenant_code: { type: "string" } } },
      }))
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", items: [] }))
      .mockResolvedValueOnce(new Response(workbook, {
        status: 200,
        headers: {
          "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "content-disposition": "attachment; filename=\"gds_operational_metadata__tenant_7__2_sheets.xlsx\"",
          "x-gds-sheet-count": "2",
        },
      }));
    const api = createApiClient(fetcher);

    await api.listMetadataDatasets(7);
    await api.describeMetadataDataset(7, "source_object");
    await api.listMetadataRows(7, "source_object", {
      is_active: true,
      tenant_code: "NWA",
    }, 25, "opaque-next");
    const download = await api.exportMetadataWorkbook(7, ["source_object", "copy"]);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/metadata/datasets",
      "/api/v1/tenants/7/metadata/datasets/source_object",
      "/api/v1/tenants/7/metadata/datasets/source_object/rows?filters=%7B%22is_active%22%3Atrue%2C%22tenant_code%22%3A%22NWA%22%7D&page_size=25&cursor=opaque-next",
      "/api/v1/tenants/7/metadata/exports/xlsx",
    ]);
    expect(fetcher.mock.calls[3]?.[1]).toEqual(expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
      body: JSON.stringify({
        schema_version: "1.0",
        sheet_codes: ["source_object", "copy"],
      }),
    }));
    expect(download.filename).toBe("gds_operational_metadata__tenant_7__2_sheets.xlsx");
    expect(download.sheetCount).toBe(2);
    expect(Array.from(new Uint8Array(await download.blob.arrayBuffer()))).toEqual([80, 75, 3, 4]);
  });

  it("uses fenced Metadata Change Set commands and raw bounded XLSX import", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createApiClient(fetcher);
    const changeSetId = "11111111-1111-1111-1111-111111111111";
    const idempotencyKey = "22222222-2222-2222-2222-222222222222";
    const row = { tenant_code: "NWA", system_code: "CRM", is_active: true };

    await api.createMetadataChangeSet(7, idempotencyKey);
    await api.readMetadataChangeSet(7, changeSetId, "source_object");
    await api.stageMetadataChangeSet(7, changeSetId, {
      schema_version: "1.0",
      expected_draft_revision: 3,
      changes: [{ dataset: "source_object", records: [row] }],
    }, idempotencyKey);
    await api.validateMetadataChangeSet(7, changeSetId, 4);
    await api.applyMetadataChangeSet(7, changeSetId, 4, idempotencyKey);
    await api.archiveMetadataChangeSet(7, changeSetId, 4, idempotencyKey);
    const workbook = new Blob([new Uint8Array([80, 75, 3, 4])]);
    await api.importMetadataWorkbook(7, changeSetId, 4, workbook, idempotencyKey);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/metadata-change-sets",
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}?dataset=source_object`,
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}/stage`,
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}/validate`,
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}/apply`,
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}/archive`,
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}/imports/xlsx`,
    ]);
    expect(fetcher.mock.calls[2]?.[1]).toEqual(expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({
        schema_version: "1.0",
        expected_draft_revision: 3,
        changes: [{ dataset: "source_object", records: [row] }],
      }),
      headers: expect.objectContaining({ "Idempotency-Key": idempotencyKey }),
    }));
    expect(fetcher.mock.calls[6]?.[1]).toEqual(expect.objectContaining({
      method: "POST",
      body: workbook,
      headers: expect.objectContaining({
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "If-Match": "4",
        "Idempotency-Key": idempotencyKey,
      }),
    }));
  });

  it("uses normalized Conceptual Object and Relationship read routes", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({ items: [] }));
    const api = createApiClient(fetcher);

    await api.listConceptualObjects(7, 18, {
      status: "needs_review",
      locked: true,
      namePrefix: " Customer ",
    });
    await api.readConceptualObject(7, 18, 41);
    await api.listConceptualRelationships(7, 18, {
      status: "active",
      locked: false,
      nameExact: " Places Order ",
    });
    await api.readConceptualRelationship(7, 18, 51);

    expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
      "/api/v1/tenants/7/models/18/conceptual/objects?status=needs_review&locked=true&name_prefix=customer&page_size=200",
      "/api/v1/tenants/7/models/18/conceptual/objects/41",
      "/api/v1/tenants/7/models/18/conceptual/relationships?status=active&locked=false&name_exact=places+order&page_size=200",
      "/api/v1/tenants/7/models/18/conceptual/relationships/51",
    ]);
  });
});

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const tenantHomePayload = {
  tenant: {
    tenant_id: 7,
    tenant_code: "NWA",
    tenant_name: "Northwind Analytics",
    tenant_description: null,
    tenant_visibility: "private",
    effective_role: "tenant_admin",
  },
  lock: {
    is_locked: false,
    owner_display_name: null,
    owned_by_current_principal: null,
    purpose: null,
    acquired_at: null,
    expires_at: null,
  },
  lock_actions: {
    can_acquire: true,
    can_renew: false,
    can_release: false,
    can_override: false,
  },
  systems: [],
};
