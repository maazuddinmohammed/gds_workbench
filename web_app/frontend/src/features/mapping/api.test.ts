import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import {
  createMappingApi,
  loadActiveMappingOutputTemplates,
  loadAllMappingScope,
  type MappingApi,
  type OutputTemplateTargetType,
} from "./api";

describe("Mapping HTTP adapter", () => {
  it("owns exact normalized Mapping and Output Template read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createMappingApi(createHttpRequest(fetcher));

    await api.listMappingDependencies(7, 18, {
      entityType: "logical_entity",
      sourceSystemId: 2,
      sourceSystemCode: " CRM ",
      status: "needs_review",
      locked: false,
    }, 50, "opaque+/=");
    await api.listMappingObjects(7, 18);
    await api.readMappingObject(7, 18, 81);
    await api.listMappingAttributes(7, 18, {
      sourceSystemId: 4,
      sourceSystemCode: " ERP ",
      locked: true,
    }, 25, "attributes+/=");
    await api.readMappingAttribute(7, 18, 91);
    await api.listOutputTemplates(7, "mapping_object", 75, "templates+/=");
    await api.listOutputTemplates(7, "mapping_attribute");

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/mapping/dependencies?entity_type=logical_entity&source_system_id=2&source_system_code=crm&status=needs_review&locked=false&page_size=50&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/mapping/objects?page_size=200",
      "/api/v1/tenants/7/models/18/mapping/objects/81",
      "/api/v1/tenants/7/models/18/mapping/attributes?source_system_id=4&source_system_code=erp&locked=true&page_size=25&cursor=attributes%2B%2F%3D",
      "/api/v1/tenants/7/models/18/mapping/attributes/91",
      "/api/v1/tenants/7/output-templates?target_type=mapping_object&active=true&page_size=75&cursor=templates%2B%2F%3D",
      "/api/v1/tenants/7/output-templates?target_type=mapping_attribute&active=true&page_size=200",
    ]);
    for (const [, init] of fetcher.mock.calls) {
      expect(init).toEqual({
        cache: "no-store",
        credentials: "same-origin",
        headers: { accept: "application/json" },
      });
    }
  });
});

describe("Mapping Output Template catalog", () => {
  it("loads active Object and Attribute templates into separate selections", async () => {
    const listOutputTemplates = vi.fn(async (
      tenantId: number,
      targetType: OutputTemplateTargetType,
      _pageSize = 200,
      cursor?: string,
    ) => ({
      tenant_id: tenantId,
      items: [{
        output_template_id: targetType === "mapping_object" ? 801 : 802,
        output_template_code: `${targetType}.standard`,
        output_template_name: targetType === "mapping_object"
          ? "Standard Object Mapping"
          : "Standard Attribute Mapping",
        output_template_description: null,
        output_template_target_type: targetType,
        output_template_schema_digest: "a".repeat(64),
        output_template_schema_digest_is_valid: true,
        is_active: true,
        field_count: 3,
      }],
      next_cursor: cursor ?? null,
    }));

    const catalog = await loadActiveMappingOutputTemplates({ listOutputTemplates }, 7);

    expect(catalog.mappingObjects.map((item) => item.output_template_id)).toEqual([801]);
    expect(catalog.mappingAttributes.map((item) => item.output_template_id)).toEqual([802]);
    expect(listOutputTemplates.mock.calls).toEqual([
      [7, "mapping_object", 200, undefined],
      [7, "mapping_attribute", 200, undefined],
    ]);
  });

  it("follows each target type's opaque catalog cursor", async () => {
    const listOutputTemplates = vi.fn(async (
      tenantId: number,
      targetType: OutputTemplateTargetType,
      _pageSize = 200,
      cursor?: string,
    ) => ({
      tenant_id: tenantId,
      items: [{
        output_template_id: cursor ? 803 : targetType === "mapping_object" ? 801 : 802,
        output_template_code: `${targetType}.${cursor ?? "first"}`,
        output_template_name: `${targetType} ${cursor ?? "first"}`,
        output_template_description: null,
        output_template_target_type: targetType,
        output_template_schema_digest: "a".repeat(64),
        output_template_schema_digest_is_valid: true,
        is_active: true,
        field_count: 1,
      }],
      next_cursor: targetType === "mapping_object" && cursor === undefined
        ? "object-next"
        : null,
    }));

    const catalog = await loadActiveMappingOutputTemplates({ listOutputTemplates }, 7);

    expect(catalog.mappingObjects.map((item) => item.output_template_id)).toEqual([801, 803]);
    expect(listOutputTemplates).toHaveBeenCalledWith(
      7,
      "mapping_object",
      200,
      "object-next",
    );
  });

  it("rejects an Output Template catalog beyond its five-page bound", async () => {
    let objectPage = 0;
    const listOutputTemplates = vi.fn(async (
      tenantId: number,
      targetType: OutputTemplateTargetType,
    ) => {
      if (targetType === "mapping_object") objectPage += 1;
      return {
        tenant_id: tenantId,
        items: [],
        next_cursor: targetType === "mapping_object" ? `next-${objectPage}` : null,
      };
    });

    await expect(loadActiveMappingOutputTemplates({ listOutputTemplates }, 7)).rejects.toThrow(
      "Output Template selection exceeds the supported bound",
    );
    expect(listOutputTemplates.mock.calls.filter(([, targetType]) => (
      targetType === "mapping_object"
    ))).toHaveLength(5);
  });
});

describe("Mapping Scope loader", () => {
  it("keeps revision consistency and repeated-cursor protection", async () => {
    const listModelScope = vi.fn<MappingApi["listModelScope"]>()
      .mockResolvedValueOnce({
        model_id: 18,
        model_revision: 4,
        items: [],
        next_cursor: "next",
      })
      .mockResolvedValueOnce({
        model_id: 18,
        model_revision: 4,
        items: [],
        next_cursor: null,
      });

    await expect(loadAllMappingScope({ listModelScope }, 7, 18)).resolves.toEqual({
      modelRevision: 4,
      items: [],
    });
    expect(listModelScope.mock.calls).toEqual([
      [7, 18, {}, 200, undefined],
      [7, 18, {}, 200, "next"],
    ]);

    const repeatedCursor = vi.fn<MappingApi["listModelScope"]>().mockResolvedValue({
      model_id: 18,
      model_revision: 4,
      items: [],
      next_cursor: "same",
    });
    await expect(loadAllMappingScope({ listModelScope: repeatedCursor }, 7, 18)).rejects.toThrow(
      "Model Scope cursor repeated",
    );
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
