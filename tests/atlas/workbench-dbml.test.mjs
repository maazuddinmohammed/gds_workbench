import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const dbml = require("../../atlas/atlas-plugin/workbench/dbml.js");

function state(records) {
  return { effective: records };
}

test("local DBML renders complete and submodel files from the effective Project, never Subject Areas", () => {
  const loaded = new Map([
    ["subject_area", state([
      { subject_area_name: "Sales", subject_area_definition: "Customer orders.", subject_area_status: "active", subject_area_is_locked: false },
    ])],
    ["subject_area_table", state([])],
    ["logical_submodel", state([
      { logical_submodel_name: "Sales", logical_submodel_definition: "Sales operations", logical_submodel_status: "active" },
    ])],
    ["logical_entity", state([
      {
        logical_entity_schema_name: "silver", logical_entity_name: "Customer",
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
        logical_entity_schema_name: "silver", logical_entity_name: "Customer",
        logical_attribute_name: "CustomerID",
        logical_attribute_definition: "Customer identifier",
        logical_attribute_data_type: "bigint",
        logical_attribute_ordinal_position: 1,
        logical_attribute_is_nullable: false,
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

  const project = { project_id: 41, project_name: "Customer Operations", project_revision: 8 };
  const documents = dbml.render(loaded, project);

  assert.deepEqual(documents.map((document) => document.path), [
    "dimensional_complete.dbml",
    "logical_complete.dbml",
    "logical_sales.dbml",
  ]);
  const logical = documents.find((document) => document.path === "logical_complete.dbml");
  assert.match(logical.content, /Table "silver"\."Customer"/);
  assert.match(logical.content, /"CustomerID" bigint \[unique, not null/);
  assert.equal(logical.table_count, 1);
  assert.throws(() => dbml.render(loaded, project, { modelType: "subject_area" }), /model type is invalid/);
});

test("local DBML rejects relationships whose effective endpoints are missing", () => {
  const loaded = new Map([
    ["logical_submodel", state([])],
    ["logical_entity", state([
      { logical_entity_schema_name: "silver", logical_entity_name: "Order", logical_entity_dependency_order: 1, logical_entity_status: "active", submodels: [] },
    ])],
    ["logical_attribute", state([])],
    ["logical_relationship", state([
      {
        logical_relationship_name: "MissingEndpoint",
        from_logical_entity_schema_name: "silver", from_logical_entity_name: "Order",
        from_logical_attribute_name: "CustomerID",
        to_logical_entity_schema_name: "silver", to_logical_entity_name: "Customer",
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
    () => dbml.render(loaded, { project_id: 41, project_name: "Orders", project_revision: 1 }),
    /inactive or missing endpoint/,
  );
});

test("natural-key tuples remain composite and repeat across declared history", () => {
  for (const layer of ["logical", "dimensional"]) {
    const entity = { [`${layer}_entity_schema_name`]: layer === "logical" ? "silver" : "gold", [`${layer}_entity_name`]: "Customer" };
    const attribute = (name, ordinal, surrogate) => ({
      ...entity,
      [`${layer}_attribute_name`]: name,
      [`${layer}_attribute_definition`]: surrogate ? "Generated row identity." : "Part of business identity.",
      [`${layer}_attribute_data_type`]: "bigint",
      [`${layer}_attribute_ordinal_position`]: ordinal,
      [`${layer}_attribute_is_nullable`]: false,
      [`${layer}_attribute_status`]: "active",
      [`${layer}_attribute_is_surrogate_key`]: surrogate,
      [`${layer}_attribute_is_natural_key`]: !surrogate,
    });
    const columns = [attribute("CustomerID", 1, true), attribute("SystemID", 2, false), attribute("CustomerCode", 3, false)];
    const details = { [`${layer}_entity_scd_type`]: "type_1" };
    const loaded = new Map([
      ["project_details", state([details])],
      [`${layer}_entity`, state([{ ...entity, [`${layer}_entity_status`]: "active", [`${layer}_entity_type`]: "dimension", submodels: [] }])],
      [`${layer}_attribute`, state(columns)],
    ]);
    const project = { project_id: 41, project_name: "Customer Operations", project_revision: 1 };
    const current = dbml.render(loaded, project, { modelType: layer })[0].content;
    assert.match(current, /\("SystemID", "CustomerCode"\) \[unique\]/);
    assert.match(current, /"CustomerID" bigint \[unique, not null/);
    assert.doesNotMatch(current, /\[pk[,\]]/);
    details[`${layer}_entity_scd_type`] = "type_2";
    const history = dbml.render(loaded, project, { modelType: layer })[0].content;
    assert.match(history, /"CustomerID" bigint \[unique, not null/);
    assert.doesNotMatch(history, /\("SystemID", "CustomerCode"\) \[unique\]/);
    assert.doesNotMatch(history, /\[pk[,\]]/);
    assert.match(history, /Natural key\./);
    if (layer === "dimensional") {
      for (const kind of ["fact", "bridge"]) {
        loaded.get("dimensional_entity").effective[0].dimensional_entity_type = kind;
        const unversioned = dbml.render(loaded, project, { modelType: layer })[0].content;
        assert.match(unversioned, /\("SystemID", "CustomerCode"\) \[unique\]/);
      }
    }
  }
});
