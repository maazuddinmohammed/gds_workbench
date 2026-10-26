import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const dbml = require("../../atlas/atlas-plugin/workbench/dbml.js");

function state(records) {
  return { effective: records };
}

const object = (name) => ({ tenant_code: "T", system_code: "CRM", connection_code: "MAIN", object_schema: "bronze", object_name: name });
const objectSource = (name, isActive = true) => ({ support_source_type: "object", source_object: object(name), rationale: null, is_active: isActive, is_locked: false });
const logicalSource = (name) => ({ support_source_type: "logical_entity", source_logical_entity: { logical_entity_schema_name: "silver", logical_entity_name: name }, rationale: null, is_active: true, is_locked: false });

function entity(layer, name, sources, extra = {}) {
  return {
    [`${layer}_entity_schema_name`]: layer === "logical" ? "silver" : "gold", [`${layer}_entity_name`]: name,
    [`${layer}_entity_definition`]: `${name} definition.`, [`${layer}_entity_dependency_order`]: 1,
    [`${layer}_entity_is_active`]: true, [`${layer}_entity_is_locked`]: false, sources, ...extra,
  };
}

function attribute(layer, entityName, name, ordinal, extra = {}) {
  return {
    [`${layer}_entity_schema_name`]: layer === "logical" ? "silver" : "gold", [`${layer}_entity_name`]: entityName,
    [`${layer}_attribute_name`]: name, [`${layer}_attribute_definition`]: `${name} of ${entityName}.`,
    [`${layer}_attribute_data_type`]: "bigint", [`${layer}_attribute_ordinal_position`]: ordinal,
    [`${layer}_attribute_is_nullable`]: false, [`${layer}_attribute_is_natural_key`]: false,
    [`${layer}_attribute_is_surrogate_key`]: false, [`${layer}_attribute_is_audit_column`]: false,
    [`${layer}_attribute_is_active`]: true, ...extra,
  };
}

function relationship(layer, from, to, attributeName, extra = {}) {
  return {
    [`from_${layer}_entity_schema_name`]: layer === "logical" ? "silver" : "gold", [`from_${layer}_entity_name`]: from,
    [`from_${layer}_attribute_name`]: attributeName,
    [`to_${layer}_entity_schema_name`]: layer === "logical" ? "silver" : "gold", [`to_${layer}_entity_name`]: to,
    [`to_${layer}_attribute_name`]: attributeName, [`${layer}_relationship_is_active`]: true, ...extra,
  };
}

function project() {
  return new Map([
    ["subject_area", state([
      { subject_area_name: "Sales", subject_area_definition: "Customer orders.", subject_area_is_active: true, subject_area_is_locked: false },
      { subject_area_name: "Billing", subject_area_definition: "Invoices.", subject_area_is_active: true, subject_area_is_locked: false },
      { subject_area_name: "Retired", subject_area_definition: "Old grouping.", subject_area_is_active: false, subject_area_is_locked: false },
    ])],
    ["subject_area_table", state([
      { subject_area_name: "Sales", ...object("customer"), subject_area_table_is_active: true, subject_area_table_is_locked: false },
      { subject_area_name: " sales ", ...object("ORDERS"), subject_area_table_is_active: true, subject_area_table_is_locked: false },
      { subject_area_name: "Billing", ...object("invoice"), subject_area_table_is_active: true, subject_area_table_is_locked: false },
      { subject_area_name: "Retired", ...object("customer"), subject_area_table_is_active: true, subject_area_table_is_locked: false },
    ])],
    ["logical_entity_type", state([{ logical_entity_type_code: "core", logical_entity_type_description: "Core subject.", logical_entity_type_is_active: true }])],
    ["logical_entity", state([
      entity("logical", "Customer", [objectSource("customer")], { logical_entity_type: "core", logical_entity_grain: "One customer" }),
      entity("logical", "Order", [objectSource("orders")], { logical_entity_type: "transaction", logical_entity_grain: "One order" }),
      entity("logical", "Calendar", [], { logical_entity_type: "reference", logical_entity_grain: "One day" }),
    ])],
    ["logical_attribute", state([
      attribute("logical", "Customer", "CustomerID", 1, { logical_attribute_is_surrogate_key: true }),
      attribute("logical", "Order", "OrderID", 1, { logical_attribute_is_surrogate_key: true }),
      attribute("logical", "Order", "CustomerID", 2),
      attribute("logical", "Calendar", "CalendarID", 1, { logical_attribute_is_surrogate_key: true }),
    ])],
    ["logical_relationship", state([
      relationship("logical", "Order", "Customer", "CustomerID", { logical_relationship_cardinality: "many_to_one", logical_relationship_basis: "Each Order names its Customer." }),
    ])],
    ["dimensional_fact_type", state([{ dimensional_fact_type_code: "transaction", dimensional_fact_type_description: "One event.", dimensional_fact_type_is_active: true }])],
    ["dimensional_entity", state([
      entity("dimensional", "DimCustomer", [logicalSource("Customer")], { dimensional_entity_type: "dimension", dimensional_fact_type: null }),
      entity("dimensional", "FactOrder", [logicalSource("Order")], { dimensional_entity_type: "fact", dimensional_fact_type: "transaction", dimensional_entity_grain_definition: "One order" }),
      entity("dimensional", "DimDate", [], { dimensional_entity_type: "dimension", dimensional_fact_type: null }),
    ])],
    ["dimensional_attribute", state([
      attribute("dimensional", "DimCustomer", "CustomerKey", 1, { dimensional_attribute_is_surrogate_key: true }),
      attribute("dimensional", "FactOrder", "FactOrderKey", 1, { dimensional_attribute_is_surrogate_key: true }),
      attribute("dimensional", "FactOrder", "CustomerKey", 2, { dimensional_attribute_is_nullable: true }),
      attribute("dimensional", "DimDate", "DimDateKey", 1, { dimensional_attribute_is_surrogate_key: true }),
    ])],
    ["dimensional_relationship", state([
      relationship("dimensional", "FactOrder", "DimCustomer", "CustomerKey", { dimensional_relationship_role_name: null, dimensional_relationship_basis: null }),
    ])],
  ]);
}

const identity = { project_id: 41, project_name: "Customer Operations", project_revision: 8 };

test("local DBML renders the complete model and one file per Subject Area with modeled Entities", () => {
  const documents = dbml.render(project(), identity);
  assert.deepEqual(documents.map((document) => [document.path, document.view, document.subject_area_name, document.table_count, document.relationship_count]), [
    ["dimensional_complete.dbml", "complete", null, 3, 1],
    ["dimensional_sales.dbml", "subject_area", "Sales", 2, 1],
    ["logical_complete.dbml", "complete", null, 3, 1],
    ["logical_sales.dbml", "subject_area", "Sales", 2, 1],
  ]);
  const byPath = new Map(documents.map((document) => [document.path, document.content]));
  const logical = byPath.get("logical_complete.dbml");
  assert.match(logical, /Table "silver"\."Customer"/);
  assert.match(logical, /"CustomerID" bigint \[unique, not null/);
  assert.match(logical, /Subject Areas: Sales/);
  assert.doesNotMatch(logical, /Retired|Billing/);
  // Child -> parent: the foreign key points many-to-one at the parent's key.
  assert.match(logical, /\/\/ Relationship: Order\.CustomerID -> Customer\.CustomerID \| Basis: Each Order names its Customer\./);
  assert.match(logical, /"silver"\."Order"\."CustomerID" > "silver"\."Customer"\."CustomerID"/);
  assert.match(byPath.get("logical_sales.dbml"), /View: Logical Subject Area: Sales\. Customer orders\./);
  assert.doesNotMatch(byPath.get("logical_sales.dbml"), /Calendar/);
  const dimensional = byPath.get("dimensional_sales.dbml");
  assert.match(dimensional, /Table "gold"\."DimCustomer"/);
  assert.doesNotMatch(dimensional, /DimDate/);
  assert.match(dimensional, /Kind: fact_dimension \| Optional: yes/);
  assert.match(dimensional, /"gold"\."FactOrder"\."CustomerKey" > "gold"\."DimCustomer"\."CustomerKey"/);
  assert.equal(dbml.render(project(), identity, { includeSubjectAreas: false }).length, 2);
  assert.throws(() => dbml.render(project(), identity, { modelType: "subject_area" }), /model type is invalid/);
});

test("an inactive Object source leaves its Logical Entity and the Dimensional Entity built from it out of the area", () => {
  const loaded = project();
  loaded.get("logical_entity").effective[1].sources = [objectSource("orders", false)];
  const documents = dbml.render(loaded, identity);
  const logical = documents.find((document) => document.path === "logical_sales.dbml");
  assert.equal(logical.table_count, 1);
  assert.equal(logical.relationship_count, 0);
  const dimensional = documents.find((document) => document.path === "dimensional_sales.dbml");
  assert.match(dimensional.content, /DimCustomer/);
  assert.doesNotMatch(dimensional.content, /FactOrder/);
  loaded.get("subject_area").effective[0].subject_area_is_active = false;
  assert.deepEqual(dbml.render(loaded, identity).map((document) => document.path), ["dimensional_complete.dbml", "logical_complete.dbml"]);
});

test("local DBML rejects relationships whose effective endpoints or cardinality are invalid", () => {
  const loaded = new Map([
    ["logical_entity", state([entity("logical", "Order", [])])],
    ["logical_attribute", state([attribute("logical", "Order", "CustomerID", 1)])],
    ["logical_relationship", state([relationship("logical", "Order", "Customer", "CustomerID", { logical_relationship_cardinality: "many_to_one" })])],
  ]);
  assert.throws(() => dbml.render(loaded, identity), /inactive or missing endpoint/);
  loaded.set("logical_entity", state([entity("logical", "Order", []), entity("logical", "Customer", [])]));
  loaded.set("logical_attribute", state([attribute("logical", "Order", "CustomerID", 1), attribute("logical", "Customer", "CustomerID", 1)]));
  loaded.get("logical_relationship").effective[0].logical_relationship_cardinality = "one_to_many";
  assert.throws(() => dbml.render(loaded, identity), /invalid cardinality/);
});

test("natural-key tuples remain composite and repeat across declared history", () => {
  for (const layer of ["logical", "dimensional"]) {
    const keys = { [`${layer}_entity_schema_name`]: layer === "logical" ? "silver" : "gold", [`${layer}_entity_name`]: "Customer" };
    const column = (name, ordinal, surrogate) => ({
      ...keys,
      [`${layer}_attribute_name`]: name,
      [`${layer}_attribute_definition`]: surrogate ? "Generated row identity." : "Part of business identity.",
      [`${layer}_attribute_data_type`]: "bigint",
      [`${layer}_attribute_ordinal_position`]: ordinal,
      [`${layer}_attribute_is_nullable`]: false,
      [`${layer}_attribute_is_active`]: true,
      [`${layer}_attribute_is_surrogate_key`]: surrogate,
      [`${layer}_attribute_is_natural_key`]: !surrogate,
    });
    const columns = [column("CustomerID", 1, true), column("SystemID", 2, false), column("CustomerCode", 3, false)];
    const details = { [`${layer}_entity_scd_type`]: "type_1" };
    const loaded = new Map([
      ["project_details", state([details])],
      [`${layer}_entity`, state([{ ...keys, [`${layer}_entity_is_active`]: true, [`${layer}_entity_type`]: "dimension", sources: [] }])],
      [`${layer}_attribute`, state(columns)],
    ]);
    const current = dbml.render(loaded, identity, { modelType: layer })[0].content;
    assert.match(current, /\("SystemID", "CustomerCode"\) \[unique\]/);
    assert.match(current, /"CustomerID" bigint \[unique, not null/);
    assert.doesNotMatch(current, /\[pk[,\]]/);
    details[`${layer}_entity_scd_type`] = "type_2";
    const history = dbml.render(loaded, identity, { modelType: layer })[0].content;
    assert.match(history, /"CustomerID" bigint \[unique, not null/);
    assert.doesNotMatch(history, /\("SystemID", "CustomerCode"\) \[unique\]/);
    assert.doesNotMatch(history, /\[pk[,\]]/);
    assert.match(history, /Natural key\./);
    if (layer === "dimensional") {
      for (const kind of ["fact", "bridge"]) {
        loaded.get("dimensional_entity").effective[0].dimensional_entity_type = kind;
        const unversioned = dbml.render(loaded, identity, { modelType: layer })[0].content;
        assert.match(unversioned, /\("SystemID", "CustomerCode"\) \[unique\]/);
      }
    }
  }
});
