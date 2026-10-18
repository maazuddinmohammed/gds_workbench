import { describe, expect, it, vi } from "vitest";
import { createHttpRequest } from "../../core/http";
import { createContextApi, loadContextSystems } from "./api";

const recordId = "00000000-0000-4000-8000-000000000091";
describe("Context HTTP adapter", () => {
  it("keeps UUID identity, exact filters, and opaque pagination cursors", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => new Response("{}", { headers: { "content-type": "application/json" } }));
    const api = createContextApi(createHttpRequest(fetcher));
    await api.listContextGroups(7, 18, { contextTypeId: 3, sourceSystemId: 2, active: false, namePrefix: " Customer " }, 50, "opaque+/=");
    await api.listContextRecords(7, 18, { groupId: 31, contextTypeId: 3, sourceSystemId: 2, status: "inactive", locked: false, textSearch: " Retain history " }, 25, "opaque+/=");
    await api.readContextRecord(7, 18, recordId);
    await api.listContextSourceSystems(7, 18, 25, "opaque+/=");
    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/projects/18/context/groups?context_type_id=3&source_system_id=2&active=false&name_prefix=customer&page_size=50&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/projects/18/context/records?group_id=31&context_type_id=3&source_system_id=2&status=inactive&locked=false&text_search=Retain+history&page_size=25&cursor=opaque%2B%2F%3D",
      `/api/v1/tenants/7/projects/18/context/records/${recordId}`,
      "/api/v1/tenants/7/projects/18/context/source-systems?page_size=25&cursor=opaque%2B%2F%3D",
    ]);
  });
  it("sends explicit create/edit identities through governed writes", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => new Response("{}", { headers: { "content-type": "application/json" } }));
    const api = createContextApi(createHttpRequest(fetcher));
    const command = { action: "create" as const, expected_project_revision: 18, context_record_id: recordId, context_group_id: 31, context_text: "Retain history.", source_reference: null };
    await api.saveContextRecord(7, 18, command, "same-request");
    const [url, options] = fetcher.mock.calls[0]!;
    expect(url).toBe("/api/v1/tenants/7/projects/18/change-sets/context-records");
    expect(JSON.parse(String(options?.body))).toEqual(command);
    expect(options?.headers).toEqual(expect.objectContaining({ "Idempotency-Key": "same-request" }));
  });
  it("loads complete authorized source choices from the Context contract", async () => {
    const first = { system_id: 11, system_code: "CRM", system_name: "Customers" };
    const second = { system_id: 12, system_code: "BILLING", system_name: "Billing" };
    const listContextSourceSystems = vi.fn()
      .mockResolvedValueOnce({ items: [first], next_cursor: "next-page" })
      .mockResolvedValueOnce({ items: [second, first], next_cursor: null });
    expect(await loadContextSystems({ listContextSourceSystems }, 7, 18)).toEqual([second, first]);
    expect(listContextSourceSystems.mock.calls).toEqual([[7, 18, 200, undefined], [7, 18, 200, "next-page"]]);
  });
  it("rejects repeated source pagination without presenting partial choices", async () => {
    const listContextSourceSystems = vi.fn().mockResolvedValue({ items: [], next_cursor: "repeated" });
    await expect(loadContextSystems({ listContextSourceSystems }, 7, 18)).rejects.toThrow("pagination did not advance");
    expect(listContextSourceSystems).toHaveBeenCalledTimes(2);
  });
});
