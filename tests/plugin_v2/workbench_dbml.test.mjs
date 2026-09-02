import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const dbml = require("../../plugins/v2/gds/skills/gds/workbench/dbml.js");

function state(records) {
  return { effective: records };
}

test("local DBML renders complete and submodel files from the effective Model", () => {
  const loaded = new Map([
    ["conceptual_object", state([
      { conceptual_object_name: "Customer", conceptual_object_type: "party", conceptual_object_status: "active" },
    ])],
    ["conceptual_relationship", state([])],
    ["logical_submodel", state([
      { logical_submodel_name: "Sales", logical_submodel_definition: "Sales operations", logical_submodel_status: "active" },
    ])],
    ["logical_entity", state([
      {
        logical_entity_name: "Customer",
        logical_entity_definition: "Customer master",
        logical_entity_type: "master",
        logical_entity_grain: "One row per customer",
        logical_entity_dependency_order: 10,
        logical_entity_status: "active",
        submodels: [{ submodel_name: "Sales", membership_status: "active" }],
      },
    ])],
    ["logical_attribute", state([
      {
        logical_entity_name: "Customer",
        logical_attribute_name: "CustomerID",
        logical_attribute_definition: "Customer identifier",
        logical_attribute_data_type: "bigint",
        logical_attribute_ordinal_position: 1,
        logical_attribute_is_nullable: false,
        logical_attribute_is_primary_key: true,
        logical_attribute_is_natural_key: false,
        logical_attribute_is_surrogate_key: true,
        logical_attribute_is_audit_column: false,
        logical_attribute_status: "active",
      },
    ])],
    ["logical_relationship", state([])],
    ["dimensional_submodel", state([])],
    ["dimensional_entity", state([])],
    ["dimensional_attribute", state([])],
    ["dimensional_relationship", state([])],
  ]);

  const documents = dbml.render(loaded, {
    model_id: 41,
    model_name: "Customer Operations",
    model_revision: 8,
  });

  assert.deepEqual(documents.map((document) => document.path), [
    "conceptual.dbml",
    "dimensional_complete.dbml",
    "logical_complete.dbml",
    "logical_sales.dbml",
  ]);
  const logical = documents.find((document) => document.path === "logical_complete.dbml");
  assert.match(logical.content, /Table "Customer"/);
  assert.match(logical.content, /"CustomerID" bigint \[pk, not null/);
  assert.equal(logical.table_count, 1);
});

test("local DBML rejects relationships whose effective endpoints are missing", () => {
  const loaded = new Map([
    ["conceptual_object", state([])],
    ["conceptual_relationship", state([])],
    ["logical_submodel", state([])],
    ["logical_entity", state([
      { logical_entity_name: "Order", logical_entity_dependency_order: 1, logical_entity_status: "active", submodels: [] },
    ])],
    ["logical_attribute", state([])],
    ["logical_relationship", state([
      {
        logical_relationship_name: "MissingEndpoint",
        from_logical_entity_name: "Order",
        from_logical_attribute_name: "CustomerID",
        to_logical_entity_name: "Customer",
        to_logical_attribute_name: "CustomerID",
        logical_relationship_cardinality: "many_to_one",
        logical_relationship_status: "active",
      },
    ])],
    ["dimensional_submodel", state([])],
    ["dimensional_entity", state([])],
    ["dimensional_attribute", state([])],
    ["dimensional_relationship", state([])],
  ]);

  assert.throws(
    () => dbml.render(loaded, { model_id: 41, model_name: "Orders", model_revision: 1 }),
    /inactive or missing endpoint/,
  );
});
