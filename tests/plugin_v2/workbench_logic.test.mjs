import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const core = require("../../plugins/v2/gds/workbench/core.js");
const commonValidation = require(
  "../../plugins/v2/gds/workbench/validation/common.js",
);
const metadataValidation = require(
  "../../plugins/v2/gds/workbench/validation/metadata.js",
);
const modelValidation = require(
  "../../plugins/v2/gds/workbench/validation/model.js",
);
const model = require("../../plugins/v2/gds/workbench/model.js");

const dataset = {
  name: "source_object",
  canonical_key: ["tenant_code", "system_code", "object_name"],
};

test("effective overlay replaces only matching canonical keys", () => {
  const baseline = [
    { tenant_code: "T", system_code: "CRM", object_name: "Customer", is_active: true },
    { tenant_code: "T", system_code: "ERP", object_name: "Order", is_active: true },
  ];
  const pending = [
    { tenant_code: "t", system_code: " crm ", object_name: "customer", is_active: false },
  ];

  const effective = core.overlay("metadata", dataset, baseline, pending);

  assert.equal(effective.length, 2);
  assert.equal(effective.find((record) => record.object_name === "customer").is_active, false);
  assert.ok(effective.some((record) => record.object_name === "Order"));
});

test("effective overlay uses deterministic ordinal key order", () => {
  const definition = { name: "item", canonical_key: ["name"] };

  assert.deepEqual(
    core.overlay("model", definition, [{ name: "ä" }, { name: "z" }], []),
    [{ name: "z" }, { name: "ä" }],
  );
});

test("Model keys use Unicode casefold rather than lowercase", () => {
  assert.equal(core.normalize("model", "model_name", " Straße "), "strasse");
  assert.equal(core.normalize("model", "model_name", "ΟΣ"), "οσ");
});

test("action review distinguishes explicit deactivation from omission", () => {
  const baseline = [
    { tenant_code: "T", system_code: "CRM", object_name: "Customer", is_active: true },
  ];

  assert.deepEqual(core.reviewActions("metadata", dataset, baseline, []), []);
  assert.equal(
    core.reviewActions("metadata", dataset, baseline, [
      { ...baseline[0], is_active: false },
    ])[0].action,
    "deactivated",
  );
});

test("Mapping review groups records by target then source System", () => {
  const definition = { name: "mapping_attribute" };
  const records = [
    {
      tenant_code: "T",
      system_code: "SILVER",
      connection_code: "MAIN",
      object_schema: "silver",
      object_name: "Order",
      source_system_code: "ERP",
      attribute_name: "OrderId",
    },
    {
      tenant_code: "T",
      system_code: "SILVER",
      connection_code: "MAIN",
      object_schema: "silver",
      object_name: "Customer",
      source_system_code: "CRM",
      attribute_name: "Name",
    },
    {
      tenant_code: "T",
      system_code: "SILVER",
      connection_code: "MAIN",
      object_schema: "silver",
      object_name: "Customer",
      source_system_code: "CRM",
      attribute_name: "CustomerId",
    },
  ];

  const groups = model.reviewGroups(definition, records);

  assert.equal(groups.length, 2);
  assert.equal(groups[0].label, "SILVER · silver.Customer · from CRM");
  assert.equal(groups[0].records.length, 2);
  assert.equal(groups[1].label, "SILVER · silver.Order · from ERP");
  assert.deepEqual(model.reviewGroups({ name: "logical_entity" }, records), []);
});

test("schema validation allows JSON drafts but reports domain issues on demand", () => {
  const schema = {
    type: "object",
    additionalProperties: false,
    properties: { name: { type: "string" }, active: { type: "boolean" } },
    required: ["name", "active"],
  };

  assert.deepEqual(commonValidation.validateSchema({ name: "A", active: true }, schema), []);
  assert.match(commonValidation.validateSchema({ name: "A" }, schema)[0], /required/);
});

test("schema validation enforces numeric, array, and serialized date constraints", () => {
  const schema = {
    type: "object",
    properties: {
      ordinal: { type: "integer", minimum: 1, maximum: 3 },
      ratio: { type: "number", exclusiveMinimum: 0, exclusiveMaximum: 1 },
      tags: { type: "array", minItems: 1, maxItems: 2, items: { type: "string" } },
      run_date: { type: "string", format: "date" },
      run_time: { type: "string", format: "date-time" },
    },
  };

  assert.deepEqual(
    commonValidation.validateSchema(
      {
        ordinal: 1,
        ratio: 0.5,
        tags: ["one"],
        run_date: "2026-02-28",
        run_time: "2026-02-28T10:30:00Z",
      },
      schema,
    ),
    [],
  );
  const issues = commonValidation.validateSchema(
    {
      ordinal: 0,
      ratio: 1,
      tags: [],
      run_date: "2026-02-30",
      run_time: "2026-02-28 10:30:00",
    },
    schema,
  );
  assert.ok(issues.some((issue) => issue.includes("below minimum")));
  assert.ok(issues.some((issue) => issue.includes("not below exclusiveMaximum")));
  assert.ok(issues.some((issue) => issue.includes("fewer than minItems")));
  assert.equal(issues.filter((issue) => issue.includes("fails date")).length, 2);
});

test("schema validation enforces exactly one generated union branch", () => {
  const schema = {
    oneOf: [
      {
        type: "object",
        additionalProperties: false,
        properties: {
          support_source_type: { const: "object" },
          source_object: { type: "object" },
        },
        required: ["support_source_type", "source_object"],
      },
      {
        type: "object",
        additionalProperties: false,
        properties: {
          support_source_type: { const: "assertion" },
          assertion_record: { type: "object" },
        },
        required: ["support_source_type", "assertion_record"],
      },
    ],
  };

  assert.deepEqual(
    commonValidation.validateSchema(
      { support_source_type: "object", source_object: {} },
      schema,
    ),
    [],
  );
  assert.match(
    commonValidation.validateSchema(
      { support_source_type: "object", assertion_record: {} },
      schema,
    )[0],
    /exactly one allowed schema/,
  );
});

test("schema validation combines allOf and compares JSON objects structurally", () => {
  const combined = {
    allOf: [
      { type: "object", required: ["ordinal"] },
      { type: "object", properties: { ordinal: { minimum: 1 } } },
    ],
  };

  assert.match(commonValidation.validateSchema({ ordinal: 0 }, combined)[0], /minimum/);
  assert.deepEqual(
    commonValidation.validateSchema(
      { second: 2, first: 1 },
      { const: { first: 1, second: 2 } },
    ),
    [],
  );
});

test("metadata validation checks references against effective records", () => {
  const datasets = new Map([
    [
      "source_object",
      {
        definition: {
          name: "source_object",
          record_type: "source_object",
          canonical_key: ["tenant_code", "system_code", "object_name"],
        },
        schema: { "x-gds-references": [] },
        records: [],
      },
    ],
    [
      "source_attribute",
      {
        definition: {
          name: "source_attribute",
          record_type: "source_attribute",
          canonical_key: ["tenant_code", "system_code", "object_name", "attribute_name"],
        },
        schema: {
          "x-gds-references": [
            {
              columns: ["tenant_code", "system_code", "object_name"],
              target_record_type: "source_object",
              target_columns: ["tenant_code", "system_code", "object_name"],
              nullable: false,
            },
          ],
        },
        records: [
          {
            tenant_code: "T",
            system_code: "CRM",
            object_name: "Missing",
            attribute_name: "Id",
            is_active: true,
          },
        ],
      },
    ],
  ]);

  const issues = metadataValidation.validateReferences(datasets);

  assert.equal(issues.length, 1);
  assert.equal(issues[0].code, "broken_reference");
});

test("metadata validation checks unique keys across zone datasets", () => {
  const record = {
    tenant_code: "T",
    system_code: "SHARED",
    connection_code: "MAIN",
    object_schema: "data",
    object_name: "Customer",
  };
  const constraint = [
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
  ];
  const datasets = new Map(
    ["source_object", "silver_object"].map((name) => [
      name,
      {
        definition: { name, record_type: "object" },
        schema: { "x-gds-unique-constraints": [constraint] },
        records: [record],
      },
    ]),
  );

  const issues = metadataValidation.validateUniqueConstraints(datasets);

  assert.equal(issues.length, 1);
  assert.equal(issues[0].code, "duplicate_unique_constraint");
  assert.equal(issues[0].dataset, "silver_object");
});

test("common validation checks secondary unique keys on effective records", () => {
  const records = [
    { tenant_code: "T", object_name: "Customer", attribute_name: "Id", ordinal: 1 },
    { tenant_code: "T", object_name: "Customer", attribute_name: "Name", ordinal: 1 },
  ];
  const loaded = new Map([
    [
      "source_attribute",
      {
        definition: {
          name: "source_attribute",
          canonical_key: ["tenant_code", "object_name", "attribute_name"],
        },
        schema: {
          "x-gds-change-set-eligible": true,
          "x-gds-unique-constraints": [["tenant_code", "object_name", "ordinal"]],
        },
        pending: records,
        effective: records,
        overlayError: null,
      },
    ],
  ]);

  const issues = commonValidation.validateLoaded("metadata", loaded);

  assert.ok(issues.some((issue) => issue.code === "duplicate_unique_constraint"));
});

test("model validation checks section endpoints and active Model Scope", () => {
  const datasets = new Map([
    ["model_scope", { records: [] }],
    [
      "logical_entity",
      {
        records: [{ logical_entity_name: "Customer", logical_entity_status: "active" }],
      },
    ],
    [
      "logical_attribute",
      {
        records: [
          {
            logical_entity_name: "Missing",
            logical_attribute_name: "Id",
            logical_attribute_status: "active",
          },
        ],
      },
    ],
    [
      "mapping_object",
      {
        records: [
          {
            tenant_code: "T",
            system_code: "SILVER",
            connection_code: "MAIN",
            object_schema: "silver",
            object_name: "customer",
            source_system_code: "CRM",
            modeled_entity_type: "logical_entity",
            modeled_entity_name: "Customer",
            object_mapping_status: "active",
          },
        ],
      },
    ],
  ]);

  const issues = modelValidation.validateGraph(datasets);

  assert.ok(
    issues.some(
      (issue) => issue.code === "reference_not_found" && issue.field === "logical_entity_name",
    ),
  );
  assert.ok(issues.some((issue) => issue.code === "model_scope_reference_invalid"));
});

test("model reference validation includes inactive future records", () => {
  const datasets = new Map([
    [
      "logical_entity",
      {
        records: [
          { logical_entity_name: "Retired", logical_entity_status: "inactive" },
        ],
      },
    ],
    [
      "logical_attribute",
      {
        records: [
          {
            logical_entity_name: "Retired",
            logical_attribute_name: "Id",
            logical_attribute_status: "inactive",
          },
        ],
      },
    ],
    [
      "logical_relationship",
      {
        records: [
          {
            from_logical_entity_name: "Retired",
            from_logical_attribute_name: "Id",
            to_logical_entity_name: "Missing",
            to_logical_attribute_name: "Id",
            logical_relationship_status: "inactive",
          },
        ],
      },
    ],
  ]);

  const issues = modelValidation.validateGraph(datasets);

  assert.equal(
    issues.some(
      (issue) => issue.code === "reference_not_found" && issue.field === "logical_entity_name",
    ),
    false,
  );
  assert.ok(
    issues.some(
      (issue) => issue.code === "reference_not_found" && issue.field === "logical_attribute_name",
    ),
  );
});

test("model validation closes assertion, submodel, and mapping dependency references", () => {
  const datasets = new Map([
    [
      "modeling_assertion_document",
      { records: [{ modeling_assertion_document_name: "Known document" }] },
    ],
    [
      "modeling_assertion_record",
      {
        records: [
          {
            modeling_assertion_record_key: "A-1",
            modeling_assertion_document_name: "Missing document",
            modeling_assertion_applicable_layers: ["conceptual"],
          },
        ],
      },
    ],
    [
      "conceptual_object",
      {
        records: [
          {
            conceptual_object_name: "Customer",
            supports: [
              {
                support_source_type: "assertion",
                assertion_record: { modeling_assertion_record_key: "Missing assertion" },
              },
            ],
          },
        ],
      },
    ],
    ["logical_submodel", { records: [] }],
    [
      "logical_entity",
      {
        records: [
          {
            logical_entity_name: "Customer",
            submodels: [{ submodel_name: "Missing submodel" }],
            sources: [
              {
                support_source_type: "assertion",
                assertion_record: { modeling_assertion_record_key: "A-1" },
              },
            ],
          },
        ],
      },
    ],
    ["mapping_dependency", { records: [] }],
    [
      "mapping_object",
      {
        records: [
          {
            tenant_code: "T",
            system_code: "SILVER",
            connection_code: "MAIN",
            object_schema: "silver",
            object_name: "customer",
            source_system_code: "CRM",
            modeled_entity_type: "logical_entity",
            modeled_entity_name: "Customer",
          },
        ],
      },
    ],
  ]);

  const issues = modelValidation.validateGraph(datasets);
  const missingFields = new Set(
    issues
      .filter((issue) => issue.code === "reference_not_found")
      .map((issue) => issue.field),
  );

  assert.ok(missingFields.has("modeling_assertion_document_name"));
  assert.ok(missingFields.has("modeling_assertion_record_key"));
  assert.ok(missingFields.has("submodel_name"));
  assert.ok(missingFields.has("mapping_dependency"));
  assert.ok(issues.some((issue) => issue.code === "assertion_layer_invalid"));
});

test("model validation checks changed physical references against active Model Scope", () => {
  const inScope = {
    tenant_code: "T",
    system_code: "CRM",
    connection_code: "MAIN",
    object_schema: "sales",
    object_name: "Customer",
  };
  const datasets = new Map([
    ["model_scope", { records: [{ ...inScope, is_active: true }], pending: [] }],
    [
      "logical_entity",
      {
        records: [
          {
            logical_entity_name: "Order",
            sources: [
              {
                support_source_type: "object",
                source_object: { ...inScope, object_name: "Missing" },
              },
            ],
          },
        ],
        pending: [
          {
            logical_entity_name: "Order",
            sources: [
              {
                support_source_type: "object",
                source_object: { ...inScope, object_name: "Missing" },
              },
            ],
          },
        ],
      },
    ],
  ]);

  const issues = modelValidation.validateGraph(datasets);

  assert.ok(
    issues.some(
      (issue) =>
        issue.code === "model_scope_reference_invalid" && issue.dataset === "logical_entity",
    ),
  );
});

test("model validation requires Bronze eligibility for logical sources", () => {
  const physical = {
    tenant_code: "T",
    system_code: "CRM",
    connection_code: "MAIN",
    object_schema: "sales",
    object_name: "Customer",
  };
  const logicalEntity = {
    logical_entity_name: "Customer",
    sources: [
      {
        support_source_type: "object",
        source_object: physical,
      },
    ],
  };
  const datasets = new Map([
    [
      "model_scope",
      {
        records: [
          {
            ...physical,
            is_active: true,
            is_bronze_source_eligible: false,
          },
        ],
        pending: [],
      },
    ],
    [
      "logical_entity",
      {
        records: [logicalEntity],
        pending: [logicalEntity],
      },
    ],
  ]);

  const issues = modelValidation.validateGraph(datasets);

  assert.ok(
    issues.some(
      (issue) =>
        issue.code === "model_scope_reference_invalid" &&
        issue.dataset === "logical_entity" &&
        issue.message.includes("eligible Bronze source"),
    ),
  );
});

test("model validation requires Bronze eligibility for physical evidence", () => {
  const customer = {
    tenant_code: "T",
    system_code: "CRM",
    connection_code: "MAIN",
    object_schema: "sales",
    object_name: "Customer",
  };
  const order = { ...customer, object_name: "Order" };
  const analysis = {
    ...Object.fromEntries(
      Object.entries(customer).map(([field, value]) => [`from_${field}`, value]),
    ),
    from_attribute_name: "CustomerId",
    ...Object.fromEntries(
      Object.entries(order).map(([field, value]) => [`to_${field}`, value]),
    ),
    to_attribute_name: "CustomerId",
  };
  const datasets = new Map([
    [
      "model_scope",
      {
        records: [customer, order].map((record) => ({
          ...record,
          is_active: true,
          is_bronze_source_eligible: false,
        })),
        pending: [],
      },
    ],
    [
      "profiling_profile",
      {
        records: [{ ...customer, attribute_name: "CustomerId" }],
        pending: [{ ...customer, attribute_name: "CustomerId" }],
      },
    ],
    [
      "analysis_result",
      {
        records: [analysis],
        pending: [analysis],
      },
    ],
    [
      "conceptual_object",
      {
        records: [
          {
            conceptual_object_name: "Customer",
            supports: [{ support_source_type: "object", source_object: customer }],
          },
        ],
        pending: [
          {
            conceptual_object_name: "Customer",
            supports: [{ support_source_type: "object", source_object: customer }],
          },
        ],
      },
    ],
  ]);

  const invalidDatasets = new Set(
    modelValidation
      .validateGraph(datasets)
      .filter((issue) => issue.code === "model_scope_reference_invalid")
      .map((issue) => issue.dataset),
  );

  assert.deepEqual(
    invalidDatasets,
    new Set(["profiling_profile", "analysis_result", "conceptual_object"]),
  );
});

test("model validation requires dimensional-source eligibility", () => {
  const silver = {
    tenant_code: "T",
    system_code: "SILVER",
    connection_code: "MAIN",
    object_schema: "silver",
    object_name: "Customer",
  };
  const entity = {
    dimensional_entity_name: "Customer",
    sources: [
      {
        support_source_type: "object",
        source_object: silver,
      },
    ],
  };
  const attribute = {
    dimensional_entity_name: "Customer",
    dimensional_attribute_name: "CustomerId",
    sources: [
      {
        support_source_type: "attribute",
        source_attribute: { ...silver, attribute_name: "CustomerId" },
      },
    ],
  };
  const datasets = new Map([
    [
      "model_scope",
      {
        records: [
          {
            ...silver,
            is_active: true,
            is_dimensional_source_eligible: false,
          },
        ],
        pending: [],
      },
    ],
    ["dimensional_entity", { records: [entity], pending: [entity] }],
    ["dimensional_attribute", { records: [attribute], pending: [attribute] }],
  ]);

  const invalidDatasets = new Set(
    modelValidation
      .validateGraph(datasets)
      .filter((issue) => issue.code === "model_scope_reference_invalid")
      .map((issue) => issue.dataset),
  );

  assert.deepEqual(
    invalidDatasets,
    new Set(["dimensional_entity", "dimensional_attribute"]),
  );
});

test("model validation requires layer-specific Mapping target eligibility", () => {
  const silver = {
    tenant_code: "T",
    system_code: "SILVER",
    connection_code: "MAIN",
    object_schema: "silver",
    object_name: "Customer",
  };
  const gold = {
    tenant_code: "T",
    system_code: "GOLD",
    connection_code: "MAIN",
    object_schema: "gold",
    object_name: "Customer",
  };
  const objects = [
    {
      ...silver,
      modeled_entity_type: "logical_entity",
      modeled_entity_name: "Customer",
      source_system_code: "CRM",
    },
    {
      ...gold,
      modeled_entity_type: "dimensional_entity",
      modeled_entity_name: "DimCustomer",
      source_system_code: "SILVER",
    },
  ];
  const attributes = objects.map((record) => ({
    ...record,
    attribute_name: "CustomerId",
    modeled_attribute_name: "CustomerId",
  }));
  const datasets = new Map([
    [
      "model_scope",
      {
        records: [
          {
            ...silver,
            is_active: true,
            is_logical_mapping_target_eligible: false,
          },
          {
            ...gold,
            is_active: true,
            is_dimensional_mapping_target_eligible: false,
          },
        ],
        pending: [],
      },
    ],
    ["mapping_object", { records: objects, pending: objects }],
    ["mapping_attribute", { records: attributes, pending: attributes }],
  ]);

  const invalidTargets = modelValidation
    .validateGraph(datasets)
    .filter((issue) => issue.code === "model_scope_reference_invalid");

  assert.equal(invalidTargets.filter((issue) => issue.dataset === "mapping_object").length, 2);
  assert.equal(
    invalidTargets.filter((issue) => issue.dataset === "mapping_attribute").length,
    2,
  );
  assert.ok(invalidTargets.every((issue) => issue.message.includes("eligible for its modeled layer")));
});

test("model validation rejects normalized duplicate nested keys", () => {
  const source = {
    support_source_type: "object",
    source_object: {
      tenant_code: "T",
      system_code: "CRM",
      connection_code: "MAIN",
      object_schema: "sales",
      object_name: "Customer",
    },
  };
  const datasets = new Map([
    [
      "modeling_assertion_record",
      {
        records: [
          {
            modeling_assertion_record_key: "A-1",
            modeling_assertion_document_name: "Doc",
            modeling_assertion_applicable_layers: ["logical", "logical"],
          },
        ],
      },
    ],
    [
      "conceptual_object",
      {
        records: [
          {
            conceptual_object_name: "Customer",
            conceptual_object_aliases: ["Client", " client "],
            supports: [],
          },
        ],
      },
    ],
    [
      "logical_entity",
      {
        records: [
          {
            logical_entity_name: "Customer",
            submodels: [{ submodel_name: "Sales" }, { submodel_name: " sales " }],
            sources: [source, { ...source, rationale: "Duplicate rationale" }],
          },
        ],
      },
    ],
  ]);

  const fields = new Set(
    modelValidation
      .validateGraph(datasets)
      .filter((issue) => issue.code === "duplicate_nested_key")
      .map((issue) => issue.field),
  );

  assert.deepEqual(
    fields,
    new Set([
      "modeling_assertion_applicable_layers",
      "conceptual_object_aliases",
      "submodels",
      "sources",
    ]),
  );
});

test("model validation accepts nullable Analysis evidence only as a complete group", () => {
  const validationFields = [
    "validation_policy_version",
    "validation_result",
    "validation_source_non_null_count",
    "validation_source_distinct_count",
    "validation_target_non_null_count",
    "validation_target_distinct_count",
    "validation_source_missing_target_count",
    "validation_unused_target_count",
    "validation_duplicate_target_key_count",
  ];
  const from = {
    tenant_code: "T",
    system_code: "CRM",
    connection_code: "MAIN",
    object_schema: "sales",
    object_name: "Customer",
    attribute_name: "CustomerId",
  };
  const to = { ...from, object_name: "Order" };
  const inferenceOnly = {
    ...Object.fromEntries(Object.entries(from).map(([field, value]) => [`from_${field}`, value])),
    ...Object.fromEntries(Object.entries(to).map(([field, value]) => [`to_${field}`, value])),
  };
  const allNull = {
    ...inferenceOnly,
    ...Object.fromEntries(validationFields.map((field) => [field, null])),
  };
  const partial = {
    ...allNull,
    validation_policy_version: "analysis.v1",
  };
  const analysis = [inferenceOnly, allNull, partial];

  const issues = modelValidation
    .validateGraph(new Map([["analysis_result", { records: analysis, pending: analysis }]]))
    .filter(
      (issue) =>
        issue.code === "record_policy_invalid" && issue.field === "analysis_validation_group",
    );

  assert.equal(issues.length, 1);
  assert.equal(issues[0].record, 3);
  assert.equal(
    issues[0].message,
    "Analysis validation fields must all be present or all be absent.",
  );
});

test("model validation enforces cross-field endpoint and key policies", () => {
  const endpoint = {
    tenant_code: "T",
    system_code: "CRM",
    connection_code: "MAIN",
    object_schema: "sales",
    object_name: "Customer",
    attribute_name: "Id",
  };
  const datasets = new Map([
    [
      "analysis_result",
      {
        records: [
          {
            ...Object.fromEntries(Object.entries(endpoint).map(([key, value]) => [`from_${key}`, value])),
            ...Object.fromEntries(Object.entries(endpoint).map(([key, value]) => [`to_${key}`, value])),
          },
        ],
      },
    ],
    [
      "conceptual_relationship",
      {
        records: [
          {
            from_conceptual_object_name: "Customer",
            to_conceptual_object_name: " customer ",
            supports: [],
          },
        ],
      },
    ],
    [
      "logical_attribute",
      {
        records: [
          {
            logical_entity_name: "Customer",
            logical_attribute_name: "Id",
            logical_attribute_is_nullable: true,
            logical_attribute_is_primary_key: false,
            logical_attribute_is_natural_key: true,
            logical_attribute_is_surrogate_key: true,
            sources: [],
          },
        ],
      },
    ],
    [
      "dimensional_attribute",
      {
        records: [
          {
            dimensional_entity_name: "Customer",
            dimensional_attribute_name: "Id",
            dimensional_attribute_role: "descriptor",
            dimensional_attribute_key_role: "surrogate",
            sources: [],
          },
        ],
      },
    ],
  ]);

  const fields = new Set(
    modelValidation
      .validateGraph(datasets)
      .filter((issue) => issue.code === "record_policy_invalid")
      .map((issue) => issue.field),
  );

  assert.ok(fields.has("analysis_endpoints"));
  assert.ok(fields.has("conceptual_relationship_endpoints"));
  assert.ok(fields.has("logical_attribute_key_policy"));
  assert.ok(fields.has("dimensional_attribute_key_role"));
});

test("model validation enforces remaining local record policies", () => {
  const datasets = new Map([
    [
      "profiling_profile",
      {
        records: [
          {
            row_count: 10,
            non_null_count: 8,
            null_count: 3,
            blank_count: 9,
            distinct_count: 9,
            min_data_length: 5,
            max_data_length: 2,
          },
        ],
      },
    ],
    [
      "logical_entity",
      {
        records: [
          {
            logical_entity_name: "Customer",
            logical_entity_type: "other",
            logical_entity_type_detail: null,
            submodels: [],
            sources: [],
          },
        ],
      },
    ],
    [
      "dimensional_entity",
      {
        records: [
          {
            dimensional_entity_name: "FactSale",
            dimensional_entity_type: "fact",
            dimensional_fact_type: null,
            dimensional_entity_grain_definition: null,
            submodels: [],
            sources: [],
          },
        ],
      },
    ],
    [
      "dimensional_attribute",
      {
        records: [
          {
            dimensional_entity_name: "FactSale",
            dimensional_attribute_name: "Amount",
            dimensional_attribute_role: "measure",
            dimensional_attribute_key_role: "none",
            dimensional_attribute_additivity: null,
            dimensional_attribute_default_aggregation: null,
            dimensional_attribute_aggregation_basis: null,
            dimensional_attribute_is_audit_column: true,
            sources: [],
          },
        ],
      },
    ],
    [
      "mapping_object",
      {
        records: [
          {
            modeled_entity_type: "logical_entity",
            modeled_entity_name: "Customer",
            source_system_code: "CRM",
            artifact_type: "sql_file",
            artifact_generation_instructions: null,
            mapping_profile_key: null,
            mapping_profile_version: null,
            mapping_package_document: null,
            object_mapping_transformation_document: null,
          },
        ],
      },
    ],
    [
      "mapping_attribute",
      {
        records: [
          {
            modeled_entity_type: "logical_entity",
            modeled_entity_name: "Customer",
            modeled_attribute_name: "Id",
            source_system_code: "CRM",
            attribute_mapping_transformation_document: {
              schema_version: "2.0",
              transformation_kind: "invalid",
            },
          },
        ],
      },
    ],
  ]);

  const fields = new Set(
    modelValidation
      .validateGraph(datasets)
      .filter((issue) => issue.code === "record_policy_invalid")
      .map((issue) => issue.field),
  );

  for (const field of [
    "profiling_counts",
    "logical_entity_type_detail",
    "dimensional_entity_policy",
    "dimensional_attribute_measure_policy",
    "dimensional_attribute_audit_policy",
    "mapping_authored_group",
    "attribute_mapping_transformation_document",
  ]) {
    assert.ok(fields.has(field), field);
  }
});
