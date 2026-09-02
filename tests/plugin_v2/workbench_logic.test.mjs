import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const core = require("../../plugins/v2/gds/skills/gds/workbench/core.js");
const commonValidation = require(
  "../../plugins/v2/gds/skills/gds/workbench/validation/common.js",
);
const metadataValidation = require(
  "../../plugins/v2/gds/skills/gds/workbench/validation/metadata.js",
);
const modelValidation = require(
  "../../plugins/v2/gds/skills/gds/workbench/validation/model.js",
);
const model = require("../../plugins/v2/gds/skills/gds/workbench/model.js");

test("effective overlay replaces matching keys and preserves omissions", () => {
  const definition = {
    name: "source_object",
    canonical_key: ["tenant_code", "system_code", "object_name"],
  };
  const baseline = [
    { tenant_code: "T", system_code: "CRM", object_name: "Customer", is_active: true },
    { tenant_code: "T", system_code: "ERP", object_name: "Order", is_active: true },
  ];
  const pending = [
    { tenant_code: "t", system_code: " crm ", object_name: "customer", is_active: false },
  ];

  const effective = core.overlay("metadata", definition, baseline, pending);

  assert.equal(effective.length, 2);
  assert.equal(effective.find((record) => record.object_name === "customer").is_active, false);
  assert.ok(effective.some((record) => record.object_name === "Order"));
});

test("Model keys use Unicode casefold", () => {
  assert.equal(core.normalize("model", "model_name", " Straße "), "strasse");
  assert.equal(core.normalize("model", "model_name", "ΟΣ"), "οσ");
});

test("review distinguishes deactivation and groups Mapping by natural-key Binding and System", () => {
  const definition = { name: "source_object", canonical_key: ["object_name"] };
  const baseline = [{ object_name: "Customer", is_active: true }];
  assert.deepEqual(core.reviewActions("metadata", definition, baseline, []), []);
  assert.equal(
    core.reviewActions("metadata", definition, baseline, [
      { object_name: "Customer", is_active: false },
    ])[0].action,
    "deactivated",
  );

  const groups = model.reviewGroups(
    { name: "mapping_attribute" },
    [
      {
        modeled_entity_type: "logical_entity",
        modeled_entity_name: "Customer",
        modeled_attribute_name: "CustomerID",
        source_system_code: "CRM",
      },
      {
        modeled_entity_type: "logical_entity",
        modeled_entity_name: "Customer",
        modeled_attribute_name: "CustomerName",
        source_system_code: "CRM",
      },
      {
        modeled_entity_type: "dimensional_entity",
        modeled_entity_name: "DimCustomer",
        modeled_attribute_name: "CustomerKey",
        source_system_code: "ERP",
      },
    ],
  );
  assert.deepEqual(
    groups.map((group) => [group.label, group.records.length]),
    [
      ["Dimensional Entity DimCustomer · source System ERP", 1],
      ["Logical Entity Customer · source System CRM", 2],
    ],
  );
});

test("review groups Model Attribute Bindings by their natural-key Entity", () => {
  const groups = model.reviewGroups(
    { name: "model_attribute_binding" },
    [
      {
        modeled_entity_type: "logical_entity",
        modeled_entity_name: "Customer",
        modeled_attribute_name: "CustomerID",
      },
      {
        modeled_entity_type: "logical_entity",
        modeled_entity_name: "Customer",
        modeled_attribute_name: "CustomerName",
      },
    ],
  );

  assert.deepEqual(
    groups.map((group) => [group.label, group.records.length]),
    [["Logical Entity Customer · Model Binding", 2]],
  );
});

test("JSON Schema validation remains generic", () => {
  const schema = {
    type: "object",
    additionalProperties: false,
    properties: {
      ordinal: { type: "integer", minimum: 1 },
      tags: { type: "array", minItems: 1, items: { type: "string" } },
      run_date: { type: "string", format: "date" },
    },
    required: ["ordinal", "tags", "run_date"],
  };

  assert.deepEqual(
    commonValidation.validateSchema(
      { ordinal: 1, tags: ["one"], run_date: "2026-02-28" },
      schema,
    ),
    [],
  );
  const issues = commonValidation.validateSchema(
    { ordinal: 0, tags: [], run_date: "2026-02-30" },
    schema,
  );
  assert.ok(issues.some((issue) => issue.includes("below minimum")));
  assert.ok(issues.some((issue) => issue.includes("fewer than minItems")));
  assert.ok(issues.some((issue) => issue.includes("fails date")));
});

test("common validation enforces eligibility, keys, constraints, and locks", () => {
  const baseline = [{ id: 1, name: "Original", is_locked: true }];
  const pending = [
    { id: 1, name: "Changed", is_locked: true, ordinal: 1 },
    { id: 1, name: "Duplicate", is_locked: false, ordinal: 1 },
  ];
  const loaded = new Map([
    [
      "object",
      {
        definition: { name: "object", canonical_key: ["id"] },
        schema: {
          type: "object",
          "x-gds-change-set-eligible": true,
          "x-gds-unique-constraints": [["ordinal"]],
        },
        baseline,
        pending,
        effective: pending,
        overlayError: null,
      },
    ],
  ]);

  const issues = commonValidation.validateLoaded("metadata", loaded);
  assert.ok(issues.some((issue) => issue.code === "duplicate_canonical_key"));
  assert.ok(issues.some((issue) => issue.code === "duplicate_unique_constraint"));
  assert.ok(issues.some((issue) => issue.code === "locked_record"));
});

test("metadata validation follows declared references", () => {
  const datasets = new Map([
    [
      "object",
      {
        definition: { name: "object", record_type: "object" },
        schema: {},
        records: [{ object_id: 1, is_active: true }],
      },
    ],
    [
      "attribute",
      {
        definition: { name: "attribute", record_type: "attribute" },
        schema: {
          "x-gds-references": [
            {
              columns: ["object_id"],
              target_record_type: "object",
              target_columns: ["object_id"],
              nullable: false,
            },
          ],
        },
        records: [{ object_id: 2, attribute_id: 10, is_active: true }],
      },
    ],
  ]);

  const issues = metadataValidation.validateReferences(datasets);
  assert.deepEqual(issues.map((issue) => issue.code), ["broken_reference"]);
});

test("model validation follows current schema references across Model datasets", () => {
  const datasets = new Map([
    [
      "model_object_binding",
      {
        definition: { name: "model_object_binding", record_type: "model_object_binding" },
        schema: { "x-gds-record-type": "model_object_binding" },
        records: [{ model_object_binding_id: 3, is_active: true }],
      },
    ],
    [
      "mapping_object",
      {
        definition: { name: "mapping_object", record_type: "mapping_object" },
        schema: {
          "x-gds-record-type": "mapping_object",
          "x-gds-references": [
            {
              columns: ["model_object_binding_id"],
              target_record_type: "model_object_binding",
              target_columns: ["model_object_binding_id"],
              nullable: false,
            },
          ],
        },
        records: [
          { model_object_binding_id: 3, is_active: true },
          { model_object_binding_id: 4, is_active: true },
        ],
      },
    ],
  ]);

  const issues = modelValidation.validateGraph(datasets);
  assert.equal(issues.length, 1);
  assert.equal(issues[0].code, "broken_reference");
  assert.equal(issues[0].record, 2);
});

test("model validation can resolve declared references into Metadata", () => {
  const metadata = new Map([
    [
      "silver_object",
      {
        definition: { name: "silver_object", record_type: "object" },
        schema: { "x-gds-record-type": "object" },
        records: [{ object_id: 101, is_active: true }],
      },
    ],
  ]);
  const datasets = new Map([
    [
      "model_object_binding",
      {
        definition: { name: "model_object_binding" },
        schema: {
          "x-gds-record-type": "model_object_binding",
          "x-gds-references": [
            {
              columns: ["object_id"],
              target_record_type: "object",
              target_columns: ["object_id"],
              nullable: false,
            },
          ],
        },
        records: [{ object_id: 101, is_active: true }],
      },
    ],
  ]);

  assert.deepEqual(modelValidation.validateGraph(datasets, metadata), []);
});

test("model validation handles nullable and partial-null references", () => {
  const datasets = new Map([
    [
      "target",
      {
        definition: { name: "target", record_type: "target" },
        schema: { "x-gds-record-type": "target" },
        records: [{ left_id: 1, right_id: 2, is_active: true }],
      },
    ],
    [
      "source",
      {
        definition: { name: "source" },
        schema: {
          "x-gds-references": [
            {
              columns: ["left_id", "right_id"],
              target_record_type: "target",
              target_columns: ["left_id", "right_id"],
              nullable: true,
            },
          ],
        },
        records: [
          { left_id: null, right_id: null, is_active: true },
          { left_id: 1, right_id: null, is_active: true },
        ],
      },
    ],
  ]);

  const issues = modelValidation.validateGraph(datasets);
  assert.deepEqual(issues.map((issue) => issue.code), ["partial_null_reference"]);
});

test("model validation rejects malformed reference metadata", () => {
  const datasets = new Map([
    [
      "broken",
      {
        definition: { name: "broken" },
        schema: { "x-gds-references": { target: "object" } },
        records: [],
      },
    ],
  ]);

  assert.deepEqual(
    modelValidation.validateGraph(datasets).map((issue) => issue.code),
    ["invalid_reference_contract"],
  );
});
