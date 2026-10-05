import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import {
  createMappingApi,
  loadActiveMappingOutputTemplates,
  loadMappingFilterSystems,
  loadMappingGenerationTargets,
  type MappingApi,
  type MappingGenerationTarget,
  type MappingObject,
  type OutputTemplateTargetType,
} from "./api";

describe("Mapping HTTP adapter", () => {
  it("owns exact normalized Mapping and Output Template read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createMappingApi(createHttpRequest(fetcher));

    await api.listMappingGenerationTargets(7, 18, "logical_entity", 50, "target+/=");
    await api.listMappingObjects(7, 18, {
      entityType: "logical_entity",
      sourceSystemId: 2,
      sourceSystemCode: " CRM ",
      status: "inactive",
      locked: false,
    }, 50, "opaque+/=");
    await api.listMappingObjects(7, 18);
    await api.readMappingObject(7, 18, 81);
    await api.listMappingAttributes(7, 18, {
      mappingObjectId: 81,
      sourceSystemId: 4,
      sourceSystemCode: " ERP ",
      locked: true,
    }, 25, "attributes+/=");
    await api.readMappingAttribute(7, 18, 91);
    await api.listOutputTemplates(7, "mapping_object", 75, "templates+/=");
    await api.listOutputTemplates(7, "mapping_attribute");

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/mapping/generation-targets?entity_type=logical_entity&page_size=50&cursor=target%2B%2F%3D",
      "/api/v1/tenants/7/models/18/mapping/objects?entity_type=logical_entity&source_system_id=2&source_system_code=crm&status=inactive&locked=false&page_size=50&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/mapping/objects?page_size=200",
      "/api/v1/tenants/7/models/18/mapping/objects/81",
      "/api/v1/tenants/7/models/18/mapping/attributes?source_system_id=4&source_system_code=erp&locked=true&mapping_object_id=81&page_size=25&cursor=attributes%2B%2F%3D",
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
        output_template_modeled_entity_type: null,
        output_template_schema_digest: "a".repeat(64),
        output_template_schema_digest_is_valid: true,
        is_active: true,
        field_count: 3,
      }],
      next_cursor: cursor ?? null,
    }));

    const catalog = await loadActiveMappingOutputTemplates({ listOutputTemplates }, 7, "logical_entity");

    expect(catalog.mappingObjects.map((item) => item.output_template_id)).toEqual([801]);
    expect(catalog.mappingAttributes.map((item) => item.output_template_id)).toEqual([802]);
    expect(listOutputTemplates.mock.calls).toEqual([
      [7, "mapping_object", 200, undefined, "logical_entity"],
      [7, "mapping_attribute", 200, undefined, "logical_entity"],
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
        output_template_modeled_entity_type: null,
        output_template_schema_digest: "a".repeat(64),
        output_template_schema_digest_is_valid: true,
        is_active: true,
        field_count: 1,
      }],
      next_cursor: targetType === "mapping_object" && cursor === undefined
        ? "object-next"
        : null,
    }));

    const catalog = await loadActiveMappingOutputTemplates({ listOutputTemplates }, 7, "logical_entity");

    expect(catalog.mappingObjects.map((item) => item.output_template_id)).toEqual([801, 803]);
    expect(listOutputTemplates).toHaveBeenCalledWith(
      7,
      "mapping_object",
      200,
      "object-next",
      "logical_entity",
    );
  });

  it("loads the complete Output Template catalog beyond five pages", async () => {
    let objectPage = 0;
    const listOutputTemplates = vi.fn(async (
      tenantId: number,
      targetType: OutputTemplateTargetType,
    ) => {
      if (targetType === "mapping_object") objectPage += 1;
      return {
        tenant_id: tenantId,
        items: [],
        next_cursor: targetType === "mapping_object" && objectPage < 7 ? `next-${objectPage}` : null,
      };
    });

    await expect(loadActiveMappingOutputTemplates({ listOutputTemplates }, 7, "logical_entity")).resolves.toEqual({
      mappingObjects: [], mappingAttributes: [],
    });
    expect(listOutputTemplates.mock.calls.filter(([, targetType]) => (
      targetType === "mapping_object"
    ))).toHaveLength(7);
  });
});

describe("Mapping target loader", () => {
  it("keeps revision consistency and repeated-cursor protection", async () => {
    const listMappingGenerationTargets = vi.fn<MappingApi["listMappingGenerationTargets"]>()
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

    await expect(loadMappingGenerationTargets(
      { listMappingGenerationTargets },
      7,
      18,
      "logical_entity",
    )).resolves.toEqual({
      modelRevision: 4,
      items: [],
    });
    expect(listMappingGenerationTargets.mock.calls).toEqual([
      [7, 18, "logical_entity", 200, undefined],
      [7, 18, "logical_entity", 200, "next"],
    ]);

    const repeatedCursor = vi.fn<MappingApi["listMappingGenerationTargets"]>().mockResolvedValue({
      model_id: 18,
      model_revision: 4,
      items: [],
      next_cursor: "same",
    });
    await expect(loadMappingGenerationTargets(
      { listMappingGenerationTargets: repeatedCursor },
      7,
      18,
      "logical_entity",
    )).rejects.toThrow(
      "Mapping target cursor repeated",
    );
  });
});

describe("Mapping filter System loader", () => {
  const target: MappingGenerationTarget = {
    entity_type: "logical_entity", entity_id: 701, entity_schema_name: "silver", entity_name: "customer",
    source_system: { system_id: 2, system_code: "ERP", system_name: "ERP" },
    mapping_object_id: null, object_order: 0, is_locked: false, has_sources: true, attributes: [],
  };
  const saved: MappingObject = {
    mapping_object_id: 81, workflow_run_id: 1048, target,
    source_system: { system_id: 3, system_code: "RETIRED", system_name: "Retained System" },
    dependency_order: 0, status: "inactive", is_locked: true, updated_at: "2026-09-27T00:00:00Z",
  };
  const targetPage = { model_id: 18, model_revision: 4, items: [target], next_cursor: null };
  const savedPage = { model_id: 18, model_revision: 4, items: [saved], next_cursor: null };

  it("unions every target and retained Mapping page, including fallback Systems, without duplicate codes", async () => {
    const listMappingGenerationTargets = vi.fn<MappingApi["listMappingGenerationTargets"]>()
      .mockResolvedValueOnce({ ...targetPage, next_cursor: "targets-next" })
      .mockResolvedValueOnce({ ...targetPage, items: [{
        ...target, entity_id: 702, has_sources: false,
        source_system: { system_id: 4, system_code: "ASSERTIONS", system_name: "Assertion fallback" },
      }] });
    const listMappingObjects = vi.fn<MappingApi["listMappingObjects"]>()
      .mockResolvedValueOnce({ ...savedPage, next_cursor: "saved-next" })
      .mockResolvedValueOnce({ ...savedPage, items: [
        { ...saved, mapping_object_id: 82, source_system: target.source_system },
        { ...saved, mapping_object_id: 83, source_system: { system_id: 5, system_code: "CRM", system_name: "CRM" } },
      ] });

    await expect(loadMappingFilterSystems({ listMappingGenerationTargets, listMappingObjects }, 7, 18, "logical_entity"))
      .resolves.toEqual({ modelRevision: 4, codes: ["ASSERTIONS", "CRM", "ERP", "RETIRED"] });
    expect(listMappingGenerationTargets.mock.calls).toEqual([
      [7, 18, "logical_entity", 200, undefined], [7, 18, "logical_entity", 200, "targets-next"],
    ]);
    expect(listMappingObjects.mock.calls).toEqual([
      [7, 18, { entityType: "logical_entity" }, 200, undefined],
      [7, 18, { entityType: "logical_entity" }, 200, "saved-next"],
    ]);
  });

  it("rejects repeated saved Mapping cursors instead of returning partial System choices", async () => {
    const listMappingGenerationTargets = vi.fn<MappingApi["listMappingGenerationTargets"]>().mockResolvedValue(targetPage);
    const listMappingObjects = vi.fn<MappingApi["listMappingObjects"]>().mockResolvedValue({ ...savedPage, next_cursor: "same" });

    await expect(loadMappingFilterSystems({ listMappingGenerationTargets, listMappingObjects }, 7, 18, "logical_entity"))
      .rejects.toThrow("Mapping filter cursor repeated");
    expect(listMappingObjects).toHaveBeenCalledTimes(2);
  });

  it.each(["first", "later"] as const)("rejects revision drift on the %s saved Mapping page", async (page) => {
    const listMappingGenerationTargets = vi.fn<MappingApi["listMappingGenerationTargets"]>().mockResolvedValue(targetPage);
    const listMappingObjects = vi.fn<MappingApi["listMappingObjects"]>()
      .mockResolvedValueOnce({ ...savedPage, model_revision: page === "first" ? 5 : 4, next_cursor: "saved-next" })
      .mockResolvedValueOnce({ ...savedPage, model_revision: 5 });

    await expect(loadMappingFilterSystems({ listMappingGenerationTargets, listMappingObjects }, 7, 18, "logical_entity"))
      .rejects.toThrow("Mapping filter revision changed while loading");
    expect(listMappingObjects).toHaveBeenCalledTimes(page === "first" ? 1 : 2);
  });

  it("rejects mixed target revisions before reading saved Mapping choices", async () => {
    const listMappingGenerationTargets = vi.fn<MappingApi["listMappingGenerationTargets"]>()
      .mockResolvedValueOnce({ ...targetPage, next_cursor: "targets-next" })
      .mockResolvedValueOnce({ ...targetPage, model_revision: 5 });
    const listMappingObjects = vi.fn<MappingApi["listMappingObjects"]>().mockResolvedValue(savedPage);

    await expect(loadMappingFilterSystems({ listMappingGenerationTargets, listMappingObjects }, 7, 18, "logical_entity"))
      .rejects.toThrow("Mapping target revision changed while loading");
    expect(listMappingObjects).not.toHaveBeenCalled();
  });

  it.each(["targets", "saved"] as const)("rejects a later %s page failure without returning partial codes", async (collection) => {
    const failure = new Error("Later page unavailable");
    const listMappingGenerationTargets = vi.fn<MappingApi["listMappingGenerationTargets"]>()
      .mockResolvedValueOnce({ ...targetPage, next_cursor: collection === "targets" ? "targets-next" : null })
      .mockRejectedValueOnce(failure);
    const listMappingObjects = vi.fn<MappingApi["listMappingObjects"]>()
      .mockResolvedValueOnce({ ...savedPage, next_cursor: "saved-next" })
      .mockRejectedValueOnce(failure);

    await expect(loadMappingFilterSystems({ listMappingGenerationTargets, listMappingObjects }, 7, 18, "logical_entity"))
      .rejects.toBe(failure);
    expect(listMappingObjects).toHaveBeenCalledTimes(collection === "targets" ? 0 : 2);
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}

describe("Mapping workbook download", () => {
  it("rejects an unexpected download content type", async () => {
    const api = createMappingApi(createHttpRequest(vi.fn<typeof fetch>(async () => new Response("not a workbook", { headers: { "content-type": "text/html" } }))));
    await expect(api.exportMapping(7, 18, 4, "dimensional_entity", "CRM")).rejects.toMatchObject({ status: 502, code: "invalid_response" });
  });
});
