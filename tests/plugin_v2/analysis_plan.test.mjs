import assert from "node:assert/strict";
import test from "node:test";
import {createRequire} from "node:module";
const require = createRequire(import.meta.url);
const {planAnalysis} = require("../../plugins/v2/gds/skills/gds/scripts/analysis.js");
const {ownKey} = require("../../plugins/v2/gds/skills/gds/scripts/profiling.js");

function fixture() {
  const source = {tenant_code:"OWNER",system_code:"CRM",connection_code:"SRC",object_schema:"dbo",object_name:"Customer",
    source_tenant_code:"OWNER",zone_code:"source",fc_object_schema:"remote",fc_object_name:"Customers",is_active:true};
  const bronze = {...source,tenant_code:"STORE",system_code:"GDS",connection_code:"LAKE",object_schema:"bronze",object_name:"customer",zone_code:"bronze"};
  const fields = Object.keys(ownKey(source));
  const mapping = Object.fromEntries(fields.flatMap((field) => [["source_"+field,source[field]],["target_"+field,bronze[field]]]));
  const attrs = (object) => ["ID","Region","Name"].map((name) => ({...ownKey(object),attribute_name:name,
    fc_attribute_name:"Physical "+name,attribute_data_type:"STRING",is_active:true,is_masking_required:false}));
  const metadata = {source_object:[source],bronze_object:[bronze],source_attribute:attrs(source),bronze_attribute:attrs(bronze),
    connection:[{tenant_code:"OWNER",system_code:"CRM",connection_code:"SRC",foreign_catalog:"foreign"},
      {tenant_code:"STORE",system_code:"GDS",connection_code:"LAKE"}],
    tenant:[{tenant_code:"OWNER",tenant_catalog:"owner"},{tenant_code:"STORE",tenant_catalog:"lake"}],
    ingestion_object_mapping:[mapping],ingestion_attribute_mapping:[{...mapping,source_attribute_name:"ID",target_attribute_name:"ID"}]};
  const plan = {scope:"all_rows",probes:[
    {id:"identity",kind:"key",object:ownKey(bronze),columns:["ID","Region"]},
    {id:"descriptor",kind:"dependency",object:ownKey(source),determinants:["ID","Region"],dependents:["Name"]},
    {id:"reference",kind:"join",from:{object:ownKey(source),columns:["ID","Region"]},to:{object:ownKey(bronze),columns:["ID","Region"]}},
  ]};
  return {metadata,scope:[source,bronze],plan};
}

test("Analysis resolves registered Source and Bronze coordinates and explicit tuple evidence", () => {
  const {metadata,scope,plan} = fixture();
  const queries = planAnalysis(metadata,scope,plan);
  assert.equal(queries.length,3);
  assert.match(queries[0].sql,/`lake`\.`bronze`\.`customer`/);
  assert.match(queries[1].sql,/`foreign`\.`remote`\.`Customers`/);
  assert.match(queries[1].sql,/`Physical ID` AS c0/);
  assert.match(queries[1].sql,/GROUP BY c0, c1, c2/);
  assert.match(queries[2].sql,/s.c0 = t.c0 AND s.c1 = t.c1/);
  assert.ok(queries.every((query) => query.max_result_rows === 1 && query.execution_state === "not_run" && query.scan_cost === "unknown"));
  assert.deepEqual(queries[0].endpoints[0].source_system_codes,["crm"]);
  assert.deepEqual(queries[0].endpoints[0].object,ownKey(scope[1]));
  assert.ok(queries.every((query) => query.sql.length <= 100000 && !/CONCAT|LIMIT|SELECT \*/i.test(query.sql)));
});

test("SQL identifier punctuation stays quoted; expressions and type coercions are rejected", () => {
  const {metadata,scope,plan} = fixture();
  metadata.source_attribute[0].fc_attribute_name = "ID`); SELECT 1; --";
  const queries = planAnalysis(metadata,scope,plan);
  assert.match(queries[1].sql,/`ID``\); SELECT 1; --` AS c0/);
  plan.probes[0].sql = "SELECT 1";
  assert.throws(() => planAnalysis(metadata,scope,plan),/documented fields/);
  delete plan.probes[0].sql;
  metadata.bronze_attribute[0].attribute_data_type = "BIGINT";
  assert.throws(() => planAnalysis(metadata,scope,plan),/matching registered types/);
});

test("Analysis refuses masked Attributes, including direct originating Source masking", () => {
  const {metadata,scope,plan} = fixture();
  metadata.bronze_attribute[0].is_masking_required = true;
  assert.throws(() => planAnalysis(metadata,scope,plan),/Masked Attributes/);
  metadata.bronze_attribute[0].is_masking_required = false;
  metadata.source_attribute[0].is_masking_required = true;
  // The first probe targets Bronze: the originating Source mask must still block it.
  assert.throws(() => planAnalysis(metadata,scope,{scope:"all_rows",probes:[plan.probes[0]]}),/Masked Attributes/);
});

test("Analysis rejects unregistered, inactive, ambiguous, oversized, and vacuous probes", () => {
  for (const change of [
    ({plan}) => { plan.scope = "sample"; },
    ({plan}) => { plan.probes = Array(51).fill(plan.probes[0]); },
    ({plan}) => { plan.probes.push(plan.probes[0]); },
    ({plan}) => { plan.probes[0].columns = []; },
    ({plan}) => { plan.probes[0].columns = ["ID"," id "]; },
    ({plan}) => { plan.probes[0].columns = ["Missing"]; },
    ({scope}) => { scope[1].is_active = false; },
    ({metadata}) => { metadata.bronze_object.push({...metadata.bronze_object[0]}); },
    ({metadata}) => { metadata.connection[1].is_active = false; },
    ({metadata}) => { metadata.source_attribute[0].attribute_data_type = "ARRAY<STRING>"; },
    ({plan}) => { plan.probes[1].dependents = ["ID"]; },
    ({plan}) => { plan.probes[2].to = plan.probes[2].from; },
    ({plan}) => { plan.probes[2].to.columns = ["ID"]; },
  ]) {
    const f = fixture();
    change(f);
    assert.throws(() => planAnalysis(f.metadata,f.scope,f.plan));
  }
});
