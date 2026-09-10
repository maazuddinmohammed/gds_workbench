import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { evaluateQuality } = require("../../plugins/v2/gds/skills/gds/workbench/model-quality.js");
const core = require("../../plugins/v2/gds/skills/gds/workbench/core.js");
const physicalFields = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"];
const keys = {
  conceptual_object: ["conceptual_object_name"],
  conceptual_relationship: ["from_conceptual_object_name", "to_conceptual_object_name", "conceptual_relationship_name"],
  logical_entity: ["logical_entity_name"],
  logical_attribute: ["logical_entity_name", "logical_attribute_name"],
  logical_relationship: ["from_logical_entity_name", "from_logical_attribute_name", "to_logical_entity_name", "to_logical_attribute_name", "logical_relationship_name"],
  analysis_result: [...["from", "to"].flatMap((prefix) => [...physicalFields, "attribute_name"].map((field) => `${prefix}_${field}`)), "relationship_kind"],
  modeling_assertion_document: ["modeling_assertion_document_name"],
  modeling_assertion_record: ["modeling_assertion_record_key"],
  profiling_profile: [...physicalFields, "attribute_name"],
  mapping_object: ["object_mapping_name"],
};
const physical = (name, attribute) => ({ tenant_code: "Tenant", system_code: "System", connection_code: "Connection",
  object_schema: "bronze", object_name: name, ...(attribute ? { attribute_name: attribute } : {}) });
const source = (name, attribute) => ({ support_source_type: attribute ? "attribute" : "object",
  [attribute ? "source_attribute" : "source_object"]: physical(name, attribute), status: "active" });
const entity = (name) => ({ logical_entity_name: name, logical_entity_status: "active", sources: [source(name)] });
const attr = (entityName, name, natural = false, surrogate = false) => ({ logical_entity_name: entityName,
  logical_attribute_name: name, logical_attribute_status: "active", logical_attribute_is_natural_key: natural,
  logical_attribute_is_surrogate_key: surrogate, logical_attribute_is_audit_column: false,
  logical_attribute_data_type: "BIGINT", sources: surrogate ? [] : [source(entityName, name)] });
const concept = (name) => ({ conceptual_object_name: name, conceptual_object_status: "active",
  supports: [{ support_source_type: "object", source_object: physical(name), support_status: "active" }] });
function model(effective, pending = effective, baseline = {}) {
  return new Map(Object.entries(keys).map(([dataset, canonical_key]) => [dataset, {
    definition: { name: dataset, canonical_key }, baseline: baseline[dataset] || [],
    pending: pending[dataset] || [], effective: effective[dataset] || [],
  }]));
}
function recordKey(dataset, record) { return Object.fromEntries(keys[dataset].map((field) => [field, record[field]])); }
const note = "working/03/object-analysis/identity.md";
const options = { noteFiles: new Map([[note, "sanitized evidence"]]) };
function decisionsFor(graph) {
  const template = evaluateQuality(graph, null).template;
  return { schema_version: "1.0", entities: template.entities.map((entry) => ({ ...entry,
    decision: "The documented business identifier determines descriptors at this lifecycle grain; retaining the source structure is justified.",
    evidence: [{ note }],
  })), relationships: template.relationships.map((entry) => ({ ...entry,
    decision: "The source role refers to the target's documented natural identity; lookup returns the generated target key.", evidence: [],
  })) };
}
function sales() {
  const analysis = {
    ...Object.fromEntries(Object.entries(physical("Order", "CustomerCode")).map(([field, value]) => [`from_${field}`, value])),
    ...Object.fromEntries(Object.entries(physical("Customer", "CustomerCode")).map(([field, value]) => [`to_${field}`, value])),
    relationship_kind: "reference", analysis_result_status: "active", validation_policy_version: "1.0.0",
    validation_result: "supported", validation_source_non_null_count: 10, validation_source_distinct_count: 3,
    validation_target_non_null_count: 4, validation_target_distinct_count: 4,
    validation_source_missing_target_count: 0, validation_unused_target_count: 1,
    validation_duplicate_target_key_count: 0,
  };
  const relationship = { logical_relationship_name: "OrderCustomer", logical_relationship_status: "active",
    from_logical_entity_name: "Order", from_logical_attribute_name: "CustomerCode",
    to_logical_entity_name: "Customer", to_logical_attribute_name: "CustomerID", logical_relationship_cardinality: "many_to_one" };
  const records = { logical_entity: [entity("Order"), entity("Customer")], logical_attribute: [attr("Order", "OrderCode", true),
    attr("Order", "CustomerCode"), attr("Customer", "CustomerID", false, true), attr("Customer", "CustomerCode", true)],
    logical_relationship: [relationship], analysis_result: [analysis] };
  const graph = model(records);
  const decisions = decisionsFor(graph);
  decisions.relationships[0].evidence = [{ dataset: "analysis_result", key: recordKey("analysis_result", analysis) }];
  return { graph, decisions, records, relationship, analysis };
}
const codes = (result) => result.errors.map((error) => error.code);

test("a normalized source may remain one entity when identity and dependency evidence is present", () => {
  const graph = model({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  const result = evaluateQuality(graph, decisionsFor(graph), options);
  assert.equal(result.status, "evidence_present");
  assert.equal(result.required, true);
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.metrics.entity_source_support_ratio, { numerator: 1, denominator: 1 });
  assert.deepEqual(result.metrics.single_source_attribute_ratio, { numerator: 1, denominator: 1 });
  assert.ok(result.warnings.some((warning) => warning.code === "source_shaped_model"));
  assert.deepEqual(result.note_paths, [note]);
});

test("profiling, mapping and byte-identical model edits do not activate modeling handoff", () => {
  const customer = entity("Customer");
  for (const [dataset, record] of [["profiling_profile", { ...physical("Customer", "CustomerCode"), row_count: 10 }],
    ["mapping_object", { object_mapping_name: "mapping" }], ["logical_entity", customer]]) {
    const graph = model({ logical_entity: [customer], [dataset]: [record] }, { [dataset]: [record] }, { logical_entity: [customer] });
    assert.equal(evaluateQuality(graph, null).status, "not_required");
  }
});

test("surrogate foreign keys trace measured physical targets through natural-key lineage", () => {
  const { graph, decisions } = sales();
  const result = evaluateQuality(graph, decisions, options);
  assert.equal(result.status, "evidence_present");
  assert.equal(result.metrics.connected_components, 1);
  assert.equal(result.metrics.cross_entity_relationships, 1);
  assert.deepEqual(result.metrics.entities_without_natural_key, []);
});

test("RCA-style unresolved Analysis cannot support an active logical relationship", () => {
  const { graph, decisions, analysis } = sales();
  for (const field of Object.keys(analysis).filter((field) => field.startsWith("validation_"))) analysis[field] = null;
  analysis.relationship_basis = "Very confident and fully reviewed";
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_not_supported"));
});

test("supported label cannot hide contradictory counts, an empty domain, or wrong lineage", () => {
  for (const mutation of [
    (analysis) => { analysis.validation_duplicate_target_key_count = 1; },
    (analysis) => { analysis.validation_source_missing_target_count = 1; },
    (analysis) => { analysis.validation_target_distinct_count = 5; },
    (analysis) => { analysis.validation_source_non_null_count = 0; analysis.validation_source_distinct_count = 0; },
  ]) {
    const { graph, decisions, analysis } = sales();
    mutation(analysis);
    assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_not_supported"));
  }
  const { graph, decisions } = sales();
  graph.get("logical_attribute").effective.find((row) => row.logical_entity_name === "Customer" && row.logical_attribute_is_natural_key)
    .sources = [source("OtherCustomer", "CustomerCode")];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_endpoint_mismatch"));
});

test("whole declared identity tuple must match the effective natural-key flags", () => {
  const graph = model({ logical_entity: [entity("Order")], logical_attribute: [attr("Order", "SystemCode", true), attr("Order", "OrderCode", true)] });
  const decisions = decisionsFor(graph);
  decisions.entities[0].identity_attributes = ["OrderCode"];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("identity_attributes_mismatch"));
  decisions.entities[0].identity_attributes = [" systemcode ", "ORDERCODE"];
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
});

test("missing, duplicate and unknown decisions cannot be hidden by an authored pass flag", () => {
  const graph = model({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  assert.ok(codes(evaluateQuality(graph, null)).includes("decision_missing"));
  const decisions = decisionsFor(graph);
  decisions.reviewed = true;
  decisions.entities.push(structuredClone(decisions.entities[0]));
  decisions.entities.push({ ...structuredClone(decisions.entities[0]), key: { logical_entity_name: "Imaginary" } });
  const result = evaluateQuality(graph, decisions, options);
  for (const expected of ["decisions_missing_or_invalid", "decision_duplicate", "decision_unknown"]) assert.ok(codes(result).includes(expected));
});

test("notes must exist and cannot serve as relationship proof", () => {
  const { graph, decisions } = sales();
  assert.ok(codes(evaluateQuality(graph, decisions)).includes("note_missing"));
  decisions.relationships[0].evidence = [{ note }];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("evidence_invalid"));
  decisions.entities[0].evidence = [{ note: "../outside.md" }];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("note_invalid"));
});

test("append-only identity needs an applicable active Assertion and active document", () => {
  const assertion = { modeling_assertion_record_key: "EventIdentity", modeling_assertion_document_name: "Policy",
    modeling_assertion_record_status: "active", modeling_assertion_applicable_layers: ["logical"] };
  const document = { modeling_assertion_document_name: "Policy", is_active: true };
  const graph = model({ logical_entity: [entity("Event")], logical_attribute: [attr("Event", "EventID", false, true)],
    modeling_assertion_record: [assertion], modeling_assertion_document: [document] });
  const decisions = decisionsFor(graph);
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("identity_evidence_missing"));
  decisions.entities[0].evidence = [{ dataset: "modeling_assertion_record", key: { modeling_assertion_record_key: "EventIdentity" } }];
  assert.equal(evaluateQuality(graph, decisions).status, "evidence_present");
  document.is_active = false;
  assert.ok(codes(evaluateQuality(graph, decisions)).includes("assertion_not_applicable"));
});

test("changed natural-key lineage or Analysis rechecks an otherwise unchanged relationship", () => {
  for (const dataset of ["logical_attribute", "analysis_result"]) {
    const { records, decisions, analysis } = sales();
    const baseline = structuredClone(records);
    if (dataset === "analysis_result") analysis.validation_result = "inconclusive";
    else records.logical_attribute[3].sources = [source("OtherCustomer", "CustomerCode")];
    const graph = model(records, { [dataset]: dataset === "analysis_result" ? [analysis] : [records.logical_attribute[3]] }, baseline);
    const result = evaluateQuality(graph, decisions, options);
    assert.equal(result.required, true);
    assert.equal(result.template.relationships.length, 1);
    assert.equal(result.status, "needs_evidence");
  }
});

test("Conceptual unknown cardinality still requires supported existence and aligned Object supports", () => {
  const { records, analysis } = sales();
  records.conceptual_object = [concept("Order"), concept("Customer")];
  records.conceptual_relationship = [{ from_conceptual_object_name: "Order", to_conceptual_object_name: "Customer",
    conceptual_relationship_name: "Places", conceptual_relationship_status: "active", conceptual_relationship_cardinality: "unknown" }];
  const graph = model(records);
  const decisions = decisionsFor(graph);
  for (const entry of decisions.relationships) entry.evidence = [{ dataset: "analysis_result", key: recordKey("analysis_result", analysis) }];
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
  records.conceptual_object[0].supports[0].source_object = physical("WrongDomain");
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_endpoint_mismatch"));
});

test("topology excludes self edges from connectivity and reports framework expansion and unsafe capacity", () => {
  const one = entity("One"), two = entity("Two");
  const audit = { ...attr("One", "CreatedDate"), logical_attribute_is_audit_column: true };
  const money = { ...attr("One", "Cost"), logical_attribute_data_type: "DECIMAL(5,5)" };
  const relationship = { logical_relationship_name: "Parent", logical_relationship_status: "active",
    from_logical_entity_name: "One", from_logical_attribute_name: "ParentID",
    to_logical_entity_name: "One", to_logical_attribute_name: "OneID", logical_relationship_cardinality: "many_to_one" };
  const records = { logical_entity: [one, two], logical_attribute: [attr("One", "OneID", false, true), audit, money], logical_relationship: [relationship] };
  const result = evaluateQuality(model(records, {}, records), null);
  assert.equal(result.metrics.self_relationships, 1);
  assert.equal(result.metrics.cross_entity_relationships, 0);
  assert.equal(result.metrics.connected_components, 2);
  assert.equal(result.metrics.framework_attributes, 2);
  assert.equal(result.metrics.business_attributes, 1);
  assert.ok(result.warnings.some((warning) => warning.code === "decimal_zero_integer_capacity"));
});

test("evaluator is pure and reports inferred-type divergence only when Metadata is available", () => {
  const graph = model({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  const decisions = decisionsFor(graph);
  const before = core.stableStringify([...graph]);
  const metadataMap = new Map([["bronze_attribute", { baseline: [{ ...physical("Customer", "CustomerCode"), attribute_inferred_data_type: "STRING" }] }]]);
  const result = evaluateQuality(graph, decisions, { ...options, metadataMap });
  assert.equal(core.stableStringify([...graph]), before);
  assert.ok(result.warnings.some((warning) => warning.code === "type_divergence"));
});

test("template is directly usable and root's hashed note-file object is supported", () => {
  const graph = model({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  const template = evaluateQuality(graph, null).template;
  assert.equal(template.schema_version, "1.0");
  const decisions = decisionsFor(graph);
  assert.equal(evaluateQuality(graph, decisions, { noteFiles: { [note]: { sha256: "a".repeat(64) } } }).status, "evidence_present");
});

test("inverse one-to-many direction uses the same proven foreign-key lookup", () => {
  const { records, analysis, relationship } = sales();
  Object.assign(relationship, { from_logical_entity_name: "Customer", from_logical_attribute_name: "CustomerID",
    to_logical_entity_name: "Order", to_logical_attribute_name: "CustomerCode", logical_relationship_cardinality: "one_to_many" });
  const graph = model(records);
  const decisions = decisionsFor(graph);
  decisions.relationships[0].evidence = [{ dataset: "analysis_result", key: recordKey("analysis_result", analysis) }];
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
  relationship.logical_relationship_cardinality = "many_to_one";
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_cardinality_mismatch"));
});

test("supported counts must reconcile distinct source values with unused target values", () => {
  const { graph, decisions, analysis } = sales();
  analysis.validation_unused_target_count = 0;
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_not_supported"));
});

test("diagnostic examples are bounded while total counts remain accurate", () => {
  const graph = model({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  const decisions = decisionsFor(graph);
  for (let index = 0; index < 210; index += 1) decisions.entities.push({ ...structuredClone(decisions.entities[0]), key: { logical_entity_name: `Unknown${index}` } });
  const result = evaluateQuality(graph, decisions, options);
  assert.equal(result.errors.length, 200);
  assert.equal(result.error_count, 210);
  assert.equal(result.truncated, true);
});

test("one-column Analysis cannot prove a surrogate lookup against composite natural identity", () => {
  const { records, analysis } = sales();
  records.logical_attribute.push(attr("Customer", "SystemCode", true));
  const graph = model(records);
  const decisions = decisionsFor(graph);
  decisions.relationships[0].evidence = [{ dataset: "analysis_result", key: recordKey("analysis_result", analysis) }];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_composite_identity"));

  const assertion = { modeling_assertion_record_key: "CompositeLookup", modeling_assertion_document_name: "Policy",
    modeling_assertion_record_status: "active", modeling_assertion_applicable_layers: ["logical"] };
  graph.get("modeling_assertion_document").effective.push({ modeling_assertion_document_name: "Policy", is_active: true });
  graph.get("modeling_assertion_record").effective.push(assertion);
  decisions.relationships[0].evidence.push({ dataset: "modeling_assertion_record", key: recordKey("modeling_assertion_record", assertion) });
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
  assertion.modeling_assertion_applicable_layers = ["conceptual"];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_composite_identity"));
});

test("incomplete or malformed modeling records return actionable diagnostics instead of crashing", () => {
  for (const record of [null, 7, {}, { logical_entity_name: " " },
    { ...entity("Customer"), sources: {} }, { ...entity("Customer"), sources: [null] }]) {
    const graph = model({ logical_entity: [record] });
    const result = evaluateQuality(graph, null);
    assert.equal(result.status, "needs_evidence");
    assert.deepEqual(codes(result), ["model_quality_input_invalid"]);
    assert.equal(result.errors[0].dataset, "logical_entity");
  }
  assert.ok(codes(evaluateQuality(null, null)).includes("model_quality_input_invalid"));
  const graph = model({}, { mapping_object: [null], profiling_profile: [{}] });
  assert.equal(evaluateQuality(graph, null).status, "not_required");
});

test("large graph metrics retain full counts while limiting all name examples", () => {
  const names = Array.from({ length: 650 }, (_, index) => `Entity${String(index).padStart(3, "0")}`);
  const records = { logical_entity: names.map(entity), logical_relationship: names.slice(1, 250).map((name, index) => ({
    logical_relationship_name: `Edge${index}`, logical_relationship_status: "active",
    from_logical_entity_name: names[index], from_logical_attribute_name: "ID",
    to_logical_entity_name: name, to_logical_attribute_name: "ParentID", logical_relationship_cardinality: "one_to_many",
  })) };
  const result = evaluateQuality(model(records), null);
  assert.equal(result.metrics.logical_entities, 650);
  assert.equal(result.metrics.cross_entity_relationships, 249);
  assert.equal(result.metrics.connected_components, 401);
  assert.equal(result.metrics.isolated_entity_count, 400);
  assert.equal(result.metrics.entities_without_natural_key_count, 650);
  assert.equal(result.metrics.components.flat().length, 200);
  assert.equal(result.metrics.isolated_entities.length, 200);
  assert.equal(result.metrics.entities_without_natural_key.length, 200);
  assert.equal(result.metrics.metric_examples_truncated, true);
  assert.equal(result.template.entities.length, 650);
  assert.equal(result.template.relationships.length, 249);
  assert.equal(result.error_count, 900);

  const isolated = evaluateQuality(model({ logical_entity: names.map(entity) }, {}, { logical_entity: names.map(entity) }), null);
  assert.equal(isolated.metrics.connected_components, 650);
  assert.equal(isolated.metrics.components.length, 200);
  assert.equal(isolated.metrics.components.flat().length, 200);
  assert.equal(isolated.metrics.isolated_entity_count, 650);
  assert.equal(isolated.status, "not_required");
});

test("complete small metric examples explicitly report no truncation", () => {
  const { graph, decisions } = sales();
  const result = evaluateQuality(graph, decisions, options);
  assert.equal(result.metrics.metric_examples_truncated, false);
  assert.equal(result.metrics.isolated_entity_count, 0);
  assert.equal(result.metrics.entities_without_natural_key_count, 0);
});

test("known Conceptual cardinality follows directional Analysis while unknown remains explicit", () => {
  const { analysis } = sales();
  const relationship = { from_conceptual_object_name: "Order", to_conceptual_object_name: "Customer",
    conceptual_relationship_name: "PlacedBy", conceptual_relationship_status: "active", conceptual_relationship_cardinality: "one_to_one" };
  const records = { conceptual_object: [concept("Order"), concept("Customer")],
    conceptual_relationship: [relationship], analysis_result: [analysis] };
  const graph = model(records);
  const decisions = decisionsFor(graph);
  decisions.relationships[0].evidence = [{ dataset: "analysis_result", key: recordKey("analysis_result", analysis) }];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_cardinality_mismatch"));
  relationship.conceptual_relationship_cardinality = "many_to_one";
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
  relationship.conceptual_relationship_cardinality = "unknown";
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");

  Object.assign(relationship, { from_conceptual_object_name: "Customer", to_conceptual_object_name: "Order",
    conceptual_relationship_cardinality: "one_to_many" });
  decisions.relationships[0].key = recordKey("conceptual_relationship", relationship);
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
  relationship.conceptual_relationship_cardinality = "many_to_one";
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_cardinality_mismatch"));
});

test("different Conceptual business grain needs applicable Assertion evidence in either reference order", () => {
  for (const reverse of [false, true]) {
    const { analysis } = sales();
    const relationship = { from_conceptual_object_name: "Order", to_conceptual_object_name: "Customer",
      conceptual_relationship_name: "BusinessAgreement", conceptual_relationship_status: "active", conceptual_relationship_cardinality: "one_to_one" };
    const assertion = { modeling_assertion_record_key: "BusinessGrain", modeling_assertion_document_name: "Policy",
      modeling_assertion_record_status: "active", modeling_assertion_applicable_layers: ["conceptual"] };
    const graph = model({ conceptual_object: [concept("Order"), concept("Customer")],
      conceptual_relationship: [relationship], analysis_result: [analysis], modeling_assertion_record: [assertion],
      modeling_assertion_document: [{ modeling_assertion_document_name: "Policy", is_active: true }] });
    const decisions = decisionsFor(graph);
    decisions.relationships[0].evidence = [{ dataset: "analysis_result", key: recordKey("analysis_result", analysis) },
      { dataset: "modeling_assertion_record", key: recordKey("modeling_assertion_record", assertion) }];
    if (reverse) decisions.relationships[0].evidence.reverse();
    assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
    assertion.modeling_assertion_applicable_layers = ["logical"];
    assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_cardinality_mismatch"));
  }
});
