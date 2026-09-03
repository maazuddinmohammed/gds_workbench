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

test("JSON Schema validation enforces conditional authoring rules", () => {
  const schema = {
    type: "object",
    properties: {
      logical_entity_type: { enum: ["core", "other"] },
      logical_entity_type_detail: { anyOf: [{ type: "string" }, { type: "null" }] },
    },
    required: ["logical_entity_type", "logical_entity_type_detail"],
    allOf: [
      {
        if: { properties: { logical_entity_type: { const: "other" } } },
        then: { properties: { logical_entity_type_detail: { type: "string" } } },
        else: { properties: { logical_entity_type_detail: { type: "null" } } },
      },
    ],
  };

  assert.deepEqual(
    commonValidation.validateSchema(
      { logical_entity_type: "core", logical_entity_type_detail: null },
      schema,
    ),
    [],
  );
  assert.ok(
    commonValidation
      .validateSchema(
        { logical_entity_type: "core", logical_entity_type_detail: "Core entity" },
        schema,
      )
      .some((issue) => issue.includes("expected null")),
  );
});

test("portable Snapshot rules cover every backend record validator", () => {
  const sameObject = {
    source_tenant_code: "Tenant",
    source_system_code: "System",
    source_connection_code: "Connection",
    source_object_schema: "Schema",
    source_object_name: "Object",
    target_tenant_code: " tenant ",
    target_system_code: "system",
    target_connection_code: "connection",
    target_object_schema: "schema",
    target_object_name: "object",
  };
  const sameAttribute = {
    ...sameObject,
    source_attribute_name: "Attribute",
    target_attribute_name: "attribute",
  };
  const sameRelationship = (layer) => ({
    [`from_${layer}_entity_name`]: "Entity",
    [`from_${layer}_attribute_name`]: "ID",
    [`to_${layer}_entity_name`]: " entity ",
    [`to_${layer}_attribute_name`]: "id",
  });
  const analysisNulls = Object.fromEntries([
    "validation_policy_version", "validation_result",
    "validation_source_non_null_count", "validation_source_distinct_count",
    "validation_target_non_null_count", "validation_target_distinct_count",
    "validation_source_missing_target_count", "validation_unused_target_count",
    "validation_duplicate_target_key_count",
  ].map((field) => [field, null]));
  const cases = [
    ["tenant_gds_connection_key", {
      gds_connection_tenant_code: "Tenant", gds_connection_system_code: null,
      gds_connection_code: null,
    }],
    ["ingestion_object_endpoints", sameObject],
    ["ingestion_attribute_endpoints", sameAttribute],
    ["copy_record_limit", { copy_source_record_limit: "9223372036854775808" }],
    ["model_details_policy", {
      silver_model_naming_instructions: "x".repeat(32769),
      gold_model_naming_instructions: null,
      silver_model_audit_columns_template: null,
      gold_model_technical_columns_template: null,
      gold_model_audit_columns_template: null,
    }],
    ["profiling_profile", {
      row_count: 2, non_null_count: 1, null_count: 0,
      blank_count: null, distinct_count: null,
      min_data_length: null, max_data_length: null,
    }],
    ["analysis_result", {
      ...analysisNulls,
      from_tenant_code: "Tenant", from_system_code: "System",
      from_connection_code: "Connection", from_object_schema: "Schema",
      from_object_name: "Object", from_attribute_name: "Attribute",
      to_tenant_code: "tenant", to_system_code: "system",
      to_connection_code: "connection", to_object_schema: "schema",
      to_object_name: "object", to_attribute_name: "attribute",
    }],
    ["modeling_assertion_document", {
      modeling_assertion_document_metadata: { raw_rows: ["prohibited"] },
    }],
    ["modeling_assertion_record", {
      modeling_assertion_text: "Text", modeling_assertion_details: {},
      modeling_assertion_source_location: null,
      modeling_assertion_applicable_layers: ["logical", "logical"],
    }],
    ["conceptual_object", {
      conceptual_object_aliases: ["Alias", " alias "], supports: [],
    }],
    ["conceptual_relationship", {
      from_conceptual_object_name: "Concept", to_conceptual_object_name: " concept ",
      supports: [],
    }],
    ["logical_entity", {
      submodels: [{ submodel_name: "Core" }, { submodel_name: " core " }], sources: [],
    }],
    ["logical_attribute", {
      logical_attribute_is_natural_key: true, logical_attribute_is_surrogate_key: true,
      logical_attribute_is_primary_key: false, logical_attribute_is_nullable: false,
      sources: [],
    }],
    ["logical_relationship", sameRelationship("logical")],
    ["dimensional_entity", {
      dimensional_entity_type: "fact", dimensional_fact_type: null,
      dimensional_entity_grain_definition: "Transaction", submodels: [], sources: [],
    }],
    ["dimensional_attribute", {
      dimensional_attribute_key_role: "primary", dimensional_attribute_role: "descriptive",
      dimensional_attribute_additivity: null,
      dimensional_attribute_default_aggregation: null,
      dimensional_attribute_aggregation_basis: null,
      dimensional_attribute_is_audit_column: false,
      sources: [],
    }],
    ["dimensional_relationship", sameRelationship("dimensional")],
    ["mapping_object", { mapping_transformation_document: { text: "x".repeat(524289) } }],
    ["mapping_attribute", {
      attribute_mapping_transformation_document: { text: "x".repeat(65537) },
    }],
    ["generated_code", { generated_code_content: "select 1", artifact_name: "dir/code.sql" }],
    ["validation_group", { validation_group_description: "x".repeat(16385) }],
    ["validation_check", {
      validation_check_description: null,
      validation_query_sql: "select 1",
      validation_comparison_query_sql: null,
      validation_result_data_type: null,
      validation_comparison_operator: "equal",
      validation_comparison_value_type: "none",
      validation_comparison_value: null,
    }],
  ];

  for (const [rule, record] of cases) {
    const issues = commonValidation.validateSchema(record, {
      type: "object",
      "x-gds-record-validation": { version: "1.0", rules: [rule] },
    });
    assert.ok(issues.length > 0, `${rule} did not reject its invalid record`);
    assert.ok(!issues.some((issue) => issue.includes("unsupported")), `${rule} is unsupported`);
  }
});

test("profiling decimals enforce the backend bounds", () => {
  const record = {
    row_count: 1, non_null_count: 1, null_count: 0,
    blank_count: null, distinct_count: null,
    min_data_length: null, max_data_length: null,
    avg_data_length: "-1.0",
    percent_populated: "100.0001", percent_duplicates: null,
    percent_null: null, percent_blank: null, percent_distinct: null,
  };
  const issues = commonValidation.validateSchema(record, {
    type: "object",
    "x-gds-record-validation": { version: "1.0", rules: ["profiling_profile"] },
  });

  assert.ok(issues.some((issue) => issue.includes("average length")));
  assert.ok(issues.some((issue) => issue.includes("percent_populated")));

  const numeric = {
    ...record,
    avg_data_length: 1.25,
    percent_populated: 100,
  };
  assert.deepEqual(commonValidation.validateSchema(numeric, {
    type: "object",
    "x-gds-record-validation": { version: "1.0", rules: ["profiling_profile"] },
  }), []);
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

test("metadata references aggregate target records across zone datasets", () => {
  const reference = {
    columns: ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"],
    target_columns: ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"],
    target_record_type: "object",
    nullable: false,
  };
  const object = {
    tenant_code: "TENANT", system_code: "SYSTEM", connection_code: "CONNECTION",
    object_schema: "schema", object_name: "Source",
  };
  const datasets = new Map([
    ["source_object", {
      definition: { name: "source_object", record_type: "object" },
      schema: {}, records: [object], baseline: [object], pending: [], effective: [object],
    }],
    ["silver_object", {
      definition: { name: "silver_object", record_type: "object" },
      schema: {}, records: [], baseline: [], pending: [], effective: [],
    }],
    ["process", {
      definition: { name: "process", record_type: "process" },
      schema: { "x-gds-references": [reference] }, records: [object],
      baseline: [], pending: [object], effective: [object],
    }],
  ]);

  assert.deepEqual(metadataValidation.validateReferences(datasets), []);
});

test("metadata additional unique constraints detect duplicates within one dataset", () => {
  const duplicate = { natural: "same", alternate: "same" };
  const datasets = new Map([["records", {
    definition: { name: "records", record_type: "record" },
    schema: { "x-gds-unique-constraints": [["alternate"]] },
    records: [duplicate, { ...duplicate, natural: "different" }],
  }]]);

  assert.deepEqual(
    metadataValidation.validateUniqueConstraints(datasets).map((issue) => issue.code),
    ["duplicate_unique_constraint"],
  );
});

test("metadata local rules match object locks and GDS Tenant scope", () => {
  const gdsObject = {
    tenant_code: "GDS", system_code: "GDS", connection_code: "DEV",
    source_tenant_code: "TENANT_A", object_schema: "silver", object_name: "Customer",
    zone_code: "silver", is_locked: false,
  };
  const datasets = new Map([
    ["tenant", {
      definition: { name: "tenant", record_type: "tenant" },
      baseline: [{
        tenant_code: "TENANT_A", gds_connection_tenant_code: "GDS",
        gds_connection_system_code: "GDS", gds_connection_code: "DEV",
      }], pending: [], effective: [],
    }],
    ["connection", {
      definition: { name: "connection", record_type: "connection" },
      baseline: [{ tenant_code: "TENANT_A", system_code: "CRM", connection_code: "SOURCE" }],
      pending: [], effective: [],
    }],
    ["silver_object", {
      definition: { name: "silver_object", record_type: "object" },
      schema: { properties: { source_tenant_code: {}, zone_code: {} } },
      baseline: [], pending: [gdsObject], effective: [gdsObject],
    }],
  ]);

  assert.deepEqual(metadataValidation.validateTenantScope(datasets, "TENANT_A"), []);
  datasets.get("silver_object").pending[0] = { ...gdsObject, source_tenant_code: "TENANT_B" };
  datasets.get("silver_object").effective[0] = datasets.get("silver_object").pending[0];
  assert.deepEqual(
    metadataValidation.validateTenantScope(datasets, "TENANT_A").map((issue) => issue.code),
    ["tenant_scope_mismatch"],
  );

  const locked = new Map([["source_attribute", {
    definition: { name: "source_attribute", record_type: "attribute" },
    baseline: [], pending: [{
      tenant_code: "TENANT_A", system_code: "CRM", connection_code: "SOURCE",
      object_schema: "dbo", object_name: "Customer", attribute_name: "Name",
    }], effective: [],
  }], ["source_object", {
    definition: { name: "source_object", record_type: "object" },
    baseline: [{
      tenant_code: "TENANT_A", system_code: "CRM", connection_code: "SOURCE",
      object_schema: "dbo", object_name: "Customer", is_locked: true,
    }], pending: [], effective: [],
  }]]);
  assert.deepEqual(metadataValidation.validateLocks(locked).map((issue) => issue.code), ["object_locked"]);
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

function modelDataset(name, records, baseline = records, pending = []) {
  return {
    definition: { name, canonical_key: [], record_type: name },
    schema: {}, records, baseline, pending,
  };
}

test("full local Model validation checks physical scope and active Binding conflicts", () => {
  const target = {
    tenant_code: "GDS", system_code: "GDS", connection_code: "DEV",
    source_tenant_code: "TENANT_A", object_schema: "silver", object_name: "Customer",
    zone_code: "silver", is_active: true,
  };
  const metadata = new Map([
    ["system", {
      definition: { name: "system", record_type: "system" }, schema: {},
      records: [{ system_code: "GDS", is_active: true }],
    }],
    ["silver_object", {
      definition: { name: "silver_object", record_type: "object" }, schema: {},
      records: [target],
    }],
  ]);
  const entities = ["Customer", "Party"].map((name) => ({
    logical_entity_name: name, logical_entity_status: "active", submodels: [], sources: [],
  }));
  const bindings = entities.map((entity) => ({
    tenant_code: target.tenant_code, system_code: target.system_code,
    connection_code: target.connection_code, object_schema: target.object_schema,
    object_name: target.object_name, modeled_entity_type: "logical_entity",
    modeled_entity_name: entity.logical_entity_name,
    model_object_binding_status: "active",
  }));
  const graph = new Map([
    ["model_details", modelDataset("model_details", [{ model_name: "Customer Model" }])],
    ["model_input_scope", modelDataset("model_input_scope", [])],
    ["logical_entity", modelDataset("logical_entity", entities)],
    ["model_object_binding", modelDataset("model_object_binding", bindings)],
  ]);

  const issues = modelValidation.validateGraph(graph, metadata, {
    tenantCode: "TENANT_A",
    model: { other_active_model_names: [] },
  });
  assert.ok(issues.some((item) => item.code === "binding_target_conflict"));

  graph.get("model_details").records[0].model_name = "Existing";
  const conflict = modelValidation.validateGraph(graph, metadata, {
    tenantCode: "TENANT_A",
    model: { other_active_model_names: [" existing "] },
  });
  assert.ok(conflict.some((item) => item.code === "model_name_conflict"));
});

test("full local Model validation accepts a Source or Bronze input in active scope", () => {
  const input = {
    tenant_code: "TENANT_A", system_code: "CRM", connection_code: "SOURCE",
    object_schema: "dbo", object_name: "Customer", zone_code: "source", is_active: true,
  };
  const graph = new Map([
    ["model_details", modelDataset("model_details", [{ model_name: "Customer Model" }])],
    ["model_input_scope", modelDataset("model_input_scope", [{ ...input,
      model_input_scope_is_locked: false,
    }])],
  ]);
  const metadata = new Map([
    ["system", { definition: { name: "system", record_type: "system" }, schema: {},
      records: [{ system_code: "CRM", is_active: true }] }],
    ["source_object", { definition: { name: "source_object", record_type: "object" },
      schema: {}, records: [{ ...input, source_tenant_code: "TENANT_A" }] }],
  ]);
  assert.deepEqual(modelValidation.validateGraph(graph, metadata, {
    tenantCode: "TENANT_A", model: { other_active_model_names: [] },
  }), []);
});

test("local Databricks SQL policy matches backend safety cases", () => {
  const accepted = [
    "SELECT 1",
    "VALUES (1), (2)",
    "SHOW TABLES",
    "DESCRIBE TABLE catalog.schema.orders",
    "SELECT * FROM `catalog`.`schema`.`orders`",
    "SELECT * FROM range(10)",
    "SELECT 1 UNION ALL SELECT 2",
    "SELECT 1; -- keep ; comment\nSELECT 2 /* keep ; block */;",
    `CREATE TEMP VIEW recent_orders AS SELECT * FROM catalog.sales.orders;
     WITH ranked AS (SELECT * FROM recent_orders) SELECT * FROM ranked`,
  ];
  const rejected = [
    "SELECT FROM",
    "SELECT * FROM orders",
    "SELECT * FROM sales.orders",
    "DESCRIBE TABLE sales.orders",
    "INSERT INTO catalog.schema.orders VALUES (1)",
    "UPDATE catalog.schema.orders SET status = 'done'",
    "DELETE FROM catalog.schema.orders",
    "MERGE INTO catalog.schema.orders USING catalog.schema.updates ON 1 = 1 WHEN MATCHED THEN UPDATE SET *",
    "COPY INTO catalog.schema.orders FROM '/Volumes/files'",
    "CREATE TABLE orders AS SELECT 1",
    "CREATE OR REPLACE VIEW orders AS SELECT 1",
    "DROP TABLE orders",
    "ALTER TABLE orders ADD COLUMN note STRING",
    "TRUNCATE TABLE orders",
    "CREATE TEMP VIEW catalog.schema.recent_orders AS SELECT 1",
    "CREATE GLOBAL TEMP VIEW recent_orders AS SELECT 1",
    "CREATE TEMP TABLE recent_orders USING CSV LOCATION '/tmp/orders' AS SELECT 1",
    "SELECT * INTO copied_orders FROM catalog.schema.orders",
    "SELECT secret('scope', 'key')",
    "SELECT try_secret('scope', 'key')",
    "USE CATALOG production",
    "SET spark.sql.ansi.enabled = false",
    "CALL system.example()",
    "GRANT SELECT ON TABLE catalog.schema.orders TO user@example.com",
    "EXPLAIN SELECT 1",
    "",
  ];
  for (const sql of accepted) {
    assert.equal(modelValidation.validateReadSql(sql).valid, true, sql);
  }
  for (const sql of rejected) {
    assert.equal(modelValidation.validateReadSql(sql).valid, false, sql);
  }
  assert.equal(modelValidation.validateReadSql("CREATE TEMP TABLE scratch AS SELECT 1").finalReturnsRows, false);
  assert.equal(
    modelValidation.validateReadSql(Array.from({ length: 26 }, () => "SELECT 1").join(";")).valid,
    false,
  );
});

test("reference validation includes inactive source and target records", () => {
  const datasets = new Map([
    ["target", {
      definition: { name: "target", record_type: "target" }, schema: {},
      records: [{ target_code: "A", is_active: false }],
    }],
    ["source", {
      definition: { name: "source", record_type: "source" },
      schema: { "x-gds-references": [{
        columns: ["target_code"], target_record_type: "target",
        target_columns: ["target_code"], nullable: false,
      }] },
      records: [{ target_code: "A", is_active: false }],
    }],
  ]);
  assert.deepEqual(metadataValidation.validateReferences(datasets), []);
  assert.deepEqual(modelValidation.validateReferences(datasets), []);
});

test("Model physical-scope validation covers every backend rule family", () => {
  const missingObject = {
    tenant_code: "TENANT_A", system_code: "MISSING", connection_code: "CONNECTION",
    object_schema: "schema", object_name: "Object",
  };
  const missingAttribute = { ...missingObject, attribute_name: "Attribute" };
  const graph = new Map([
    ["model_details", modelDataset("model_details", [])],
    ["model_input_scope", modelDataset("model_input_scope", [{ ...missingObject, is_active: true }])],
    ["profiling_profile", modelDataset("profiling_profile", [missingAttribute])],
    ["analysis_result", modelDataset("analysis_result", [{
      ...Object.fromEntries(Object.entries(missingAttribute).map(([field, value]) => [`from_${field}`, value])),
      ...Object.fromEntries(Object.entries(missingAttribute).map(([field, value]) => [`to_${field}`, value])),
    }])],
    ["modeling_assertion_document", modelDataset("modeling_assertion_document", [{
      tenant_code: "TENANT_B", system_code: "MISSING",
    }])],
    ["conceptual_object", modelDataset("conceptual_object", [{
      supports: [{ support_source_type: "object", source_object: missingObject }],
    }])],
    ["logical_entity", modelDataset("logical_entity", [{ sources: [{
      support_source_type: "object", source_object: missingObject,
    }] }])],
    ["logical_attribute", modelDataset("logical_attribute", [{ sources: [{
      support_source_type: "attribute", source_attribute: missingAttribute,
    }] }])],
    ["dimensional_entity", modelDataset("dimensional_entity", [{ sources: [{
      support_source_type: "object", source_object: missingObject,
    }] }])],
    ["mapping_dependency", modelDataset("mapping_dependency", [{
      source_system_code: "MISSING",
    }])],
    ["validation_group", modelDataset("validation_group", [{
      tenant_code: "TENANT_B", system_code: "MISSING", validation_group_name: "Checks",
      is_active: false,
    }])],
    ["validation_check", modelDataset("validation_check", [{
      tenant_code: "TENANT_A", system_code: "MISSING", validation_group_name: "Checks",
      validation_query_sql: "CREATE TEMP TABLE scratch AS SELECT 1",
      validation_comparison_query_sql: null, validation_comparison_operator: "equal",
      is_active: true,
    }])],
  ]);
  const catalog = {
    tenant: "tenant_a", otherModelNames: new Set(), activeSystems: new Set(["crm"]),
    objects: new Set(), attributes: new Set(), inputObjects: new Set(),
    inputAttributes: new Set(), dimensionalSourceObjects: new Set(),
    dimensionalSourceAttributes: new Set(), logicalTargets: new Set(),
    logicalTargetAttributes: new Set(), dimensionalTargets: new Set(),
    dimensionalTargetAttributes: new Set(),
  };

  const issues = modelValidation.validatePhysicalScope(graph, catalog);
  const codes = new Set(issues.map((item) => item.code));
  assert.ok(codes.has("model_details_invalid"));
  assert.ok(codes.has("model_input_reference_invalid"));
  assert.ok(codes.has("validation_query_result_invalid"));
  for (const dataset of [
    "model_input_scope", "profiling_profile", "analysis_result",
    "modeling_assertion_document", "conceptual_object", "logical_entity",
    "logical_attribute", "dimensional_entity", "mapping_dependency",
    "validation_group", "validation_check",
  ]) assert.ok(issues.some((item) => item.dataset === dataset), dataset);
});

test("Model future-graph references cover every backend relationship family", () => {
  const assertionSource = {
    support_source_type: "assertion",
    assertion_record: { modeling_assertion_record_key: "MissingAssertion" },
  };
  const graph = new Map([
    ["modeling_assertion_document", modelDataset("modeling_assertion_document", [])],
    ["modeling_assertion_record", modelDataset("modeling_assertion_record", [{
      modeling_assertion_document_name: "MissingDocument",
      modeling_assertion_record_key: "Assertion", modeling_assertion_applicable_layers: ["logical"],
    }])],
    ["conceptual_object", modelDataset("conceptual_object", [{
      conceptual_object_name: "Concept", supports: [assertionSource],
    }])],
    ["conceptual_relationship", modelDataset("conceptual_relationship", [{
      from_conceptual_object_name: "MissingA", to_conceptual_object_name: "MissingB",
      supports: [],
    }])],
    ["logical_submodel", modelDataset("logical_submodel", [])],
    ["logical_entity", modelDataset("logical_entity", [{
      logical_entity_name: "Entity", submodels: [{ submodel_name: "Missing" }],
      sources: [assertionSource],
    }])],
    ["logical_attribute", modelDataset("logical_attribute", [{
      logical_entity_name: "MissingEntity", logical_attribute_name: "Attribute", sources: [],
    }])],
    ["logical_relationship", modelDataset("logical_relationship", [{
      from_logical_entity_name: "Entity", from_logical_attribute_name: "MissingA",
      to_logical_entity_name: "Entity", to_logical_attribute_name: "MissingB",
    }])],
    ["model_object_binding", modelDataset("model_object_binding", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "MissingEntity",
    }])],
    ["model_attribute_binding", modelDataset("model_attribute_binding", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "AnotherMissing",
      modeled_attribute_name: "MissingAttribute",
    }])],
    ["mapping_dependency", modelDataset("mapping_dependency", [])],
    ["mapping_object", modelDataset("mapping_object", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "NoBinding",
      source_system_code: "CRM",
    }])],
    ["mapping_attribute", modelDataset("mapping_attribute", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "NoBinding",
      modeled_attribute_name: "Missing", source_system_code: "CRM",
    }])],
    ["generated_code", modelDataset("generated_code", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "NoBinding",
      artifact_name: "code.sql",
    }])],
    ["generated_code_source_system", modelDataset("generated_code_source_system", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "NoBinding",
      artifact_name: "missing.sql",
    }])],
    ["validation_group", modelDataset("validation_group", [])],
    ["validation_check", modelDataset("validation_check", [{
      tenant_code: "TENANT_A", system_code: "CRM", validation_group_name: "Missing",
    }])],
  ]);

  const issues = modelValidation.validateBackendReferences(graph);
  for (const dataset of [
    "modeling_assertion_record", "conceptual_object", "conceptual_relationship",
    "logical_entity", "logical_attribute", "logical_relationship",
    "model_object_binding", "model_attribute_binding", "mapping_object",
    "mapping_attribute", "generated_code", "generated_code_source_system",
    "validation_check",
  ]) assert.ok(issues.some((item) => item.dataset === dataset), dataset);
  assert.ok(issues.some((item) => item.code === "assertion_layer_invalid") === false);
});

test("Model active dependencies cover Binding, Mapping, Code, and Validation", () => {
  const graph = new Map([
    ["logical_entity", modelDataset("logical_entity", [])],
    ["logical_attribute", modelDataset("logical_attribute", [])],
    ["model_object_binding", modelDataset("model_object_binding", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "Entity",
      model_object_binding_status: "active",
    }])],
    ["model_attribute_binding", modelDataset("model_attribute_binding", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "Entity",
      modeled_attribute_name: "Attribute", model_attribute_binding_status: "active",
    }])],
    ["mapping_dependency", modelDataset("mapping_dependency", [])],
    ["mapping_object", modelDataset("mapping_object", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "Entity",
      source_system_code: "CRM", object_mapping_status: "active",
      mapping_transformation_document: null,
    }])],
    ["mapping_attribute", modelDataset("mapping_attribute", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "Entity",
      modeled_attribute_name: "Attribute", source_system_code: "CRM",
      attribute_mapping_status: "active", attribute_mapping_transformation_document: null,
    }])],
    ["generated_code", modelDataset("generated_code", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "NoBinding",
      artifact_name: "code.sql", generated_code_status: "active",
    }])],
    ["generated_code_source_system", modelDataset("generated_code_source_system", [{
      modeled_entity_type: "logical_entity", modeled_entity_name: "NoBinding",
      artifact_name: "code.sql", source_system_code: "CRM",
      generated_code_source_system_status: "active",
    }])],
    ["validation_group", modelDataset("validation_group", [{
      tenant_code: "TENANT_A", system_code: "CRM", validation_group_name: "Checks",
      is_active: true,
    }])],
    ["validation_check", modelDataset("validation_check", [{
      tenant_code: "TENANT_A", system_code: "CRM", validation_group_name: "Missing",
      is_active: true,
    }])],
  ]);

  const issues = modelValidation.validateActiveDependencies(graph);
  assert.ok(issues.length >= 8);
  assert.ok(issues.every((item) => item.code === "active_dependency_invalid"));
  for (const dataset of [
    "model_object_binding", "model_attribute_binding", "mapping_object",
    "mapping_attribute", "generated_code", "generated_code_source_system",
    "validation_group", "validation_check",
  ]) assert.ok(issues.some((item) => item.dataset === dataset), dataset);
});
