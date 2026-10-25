import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { evaluateQuality } = require("../../atlas/atlas-plugin/workbench/project-quality.js");
const core = require("../../atlas/atlas-plugin/workbench/core.js");
const physicalFields = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"];
const keys = {
  project_input_scope: physicalFields,
  subject_area: ["subject_area_name"],
  subject_area_table: ["subject_area_name", ...physicalFields],
  logical_entity: ["logical_entity_schema_name", "logical_entity_name"],
  logical_attribute: ["logical_entity_schema_name", "logical_entity_name", "logical_attribute_name"],
  logical_relationship: ["from_logical_entity_schema_name", "from_logical_entity_name", "from_logical_attribute_name", "to_logical_entity_schema_name", "to_logical_entity_name", "to_logical_attribute_name", "logical_relationship_name"],
  analysis_result: [...["from", "to"].flatMap((prefix) => [...physicalFields, "attribute_name"].map((field) => `${prefix}_${field}`)), "relationship_kind"],
  context_group: ["context_group_name"],
  context_record: ["context_record_id"],
  profiling_profile: [...physicalFields, "attribute_name"],
  mapping_object: ["object_mapping_name"],
};
const physical = (name, attribute) => ({ tenant_code: "Tenant", system_code: "System", connection_code: "Connection",
  object_schema: "bronze", object_name: name, ...(attribute ? { attribute_name: attribute } : {}) });
const source = (name, attribute) => ({ support_source_type: attribute ? "attribute" : "object",
  [attribute ? "source_attribute" : "source_object"]: physical(name, attribute), status: "active" });
const entity = (name) => ({ logical_entity_schema_name: "silver", logical_entity_name: name, logical_entity_status: "active", sources: [source(name)] });
const attr = (entityName, name, natural = false, surrogate = false) => ({ logical_entity_schema_name: "silver", logical_entity_name: entityName,
  logical_attribute_name: name, logical_attribute_status: "active", logical_attribute_is_natural_key: natural,
  logical_attribute_is_surrogate_key: surrogate, logical_attribute_is_audit_column: false,
  logical_attribute_data_type: "BIGINT", sources: surrogate ? [] : [source(entityName, name)] });
const scope = (name) => ({ ...physical(name), project_input_scope_is_locked: false, is_active: true });
const area = (name, status = "active") => ({ subject_area_name: name, subject_area_definition: `${name} capability.`,
  subject_area_status: status, subject_area_is_locked: false });
const member = (areaName, table, status = "active") => ({ subject_area_name: areaName, ...physical(table),
  subject_area_table_status: status, subject_area_table_is_locked: false });
const bronze = (...names) => ({ metadataMap: new Map([["bronze_object", {
  baseline: names.map((name) => ({ ...physical(name), zone_code: "bronze", is_active: true })) }]]) });
function project(effective, pending = effective, baseline = {}) {
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
    relationship_kind: "reference", inferred_cardinality: "many_to_one", analysis_result_status: "active", validation_policy_version: "1.0.0",
    validation_result: "supported", validation_source_non_null_count: 10, validation_source_distinct_count: 3,
    validation_target_non_null_count: 4, validation_target_distinct_count: 4,
    validation_source_missing_target_count: 0, validation_unused_target_count: 1,
    validation_duplicate_target_key_count: 0,
  };
  const relationship = { logical_relationship_name: "OrderCustomer", logical_relationship_status: "active",
    from_logical_entity_schema_name: "silver", from_logical_entity_name: "Order", from_logical_attribute_name: "CustomerCode",
    to_logical_entity_schema_name: "silver", to_logical_entity_name: "Customer", to_logical_attribute_name: "CustomerID", logical_relationship_cardinality: "many_to_one" };
  const records = { logical_entity: [entity("Order"), entity("Customer")], logical_attribute: [attr("Order", "OrderCode", true),
    attr("Order", "CustomerCode"), attr("Customer", "CustomerID", false, true), attr("Customer", "CustomerCode", true)],
    logical_relationship: [relationship], analysis_result: [analysis] };
  const graph = project(records);
  const decisions = decisionsFor(graph);
  decisions.relationships[0].evidence = [{ dataset: "analysis_result", key: recordKey("analysis_result", analysis) }];
  return { graph, decisions, records, relationship, analysis };
}
const codes = (result) => result.errors.map((error) => error.code);

test("a normalized source may remain one entity when identity and dependency evidence is present", () => {
  const graph = project({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  const result = evaluateQuality(graph, decisionsFor(graph), options);
  assert.equal(result.status, "evidence_present");
  assert.equal(result.required, true);
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.metrics.entity_source_support_ratio, { numerator: 1, denominator: 1 });
  assert.deepEqual(result.metrics.single_source_attribute_ratio, { numerator: 1, denominator: 1 });
  assert.ok(result.warnings.some((warning) => warning.code === "source_shaped_project"));
  assert.deepEqual(result.note_paths, [note]);
});

test("profiling, mapping and byte-identical project edits do not activate modeling handoff", () => {
  const customer = entity("Customer");
  for (const [dataset, record] of [["profiling_profile", { ...physical("Customer", "CustomerCode"), row_count: 10 }],
    ["mapping_object", { object_mapping_name: "mapping" }], ["logical_entity", customer]]) {
    const graph = project({ logical_entity: [customer], [dataset]: [record] }, { [dataset]: [record] }, { logical_entity: [customer] });
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

test("metadata-only Analysis supports explicit inference without fabricated SQL counts", () => {
  const { graph, decisions, analysis } = sales();
  for (const field of Object.keys(analysis).filter((field) => field.startsWith("validation_"))) analysis[field] = null;
  analysis.relationship_basis = "Order.CustomerCode identifies the referenced Customer business identifier; many orders may share one customer.";
  const result = evaluateQuality(graph, decisions, options);
  assert.equal(codes(result).includes("analysis_not_supported"), false);
  assert.ok(result.warnings.some(issue => issue.code === "analysis_inferred"));
});

test("Analysis inference disagrees with observed uniqueness as a warning without rewriting evidence", () => {
  for (const [sourceCount, targetCount, observed] of [
    [3, 4, "one_to_one"], [3, 8, "one_to_many"], [10, 4, "many_to_one"], [10, 8, "many_to_many"],
  ]) {
    const { analysis } = sales();
    analysis.validation_source_non_null_count = sourceCount;
    analysis.validation_target_non_null_count = targetCount;
    analysis.validation_duplicate_target_key_count = targetCount - analysis.validation_target_distinct_count;
    analysis.validation_result = targetCount === 4 ? "supported" : "unsupported";
    analysis.inferred_cardinality = observed === "one_to_one" ? "many_to_one" : "one_to_one";
    const before = structuredClone(analysis);
    const graph = project({ analysis_result: [analysis] });
    const result = evaluateQuality(graph, null);
    assert.deepEqual(result.errors, []);
    assert.equal(result.required, false);
    assert.equal(result.warnings.filter(issue => issue.code === "analysis_inferred_cardinality_mismatch").length, 1);
    assert.deepEqual(analysis, before);
    analysis.inferred_cardinality = observed;
    assert.equal(evaluateQuality(graph, null).warnings.some(issue => issue.code === "analysis_inferred_cardinality_mismatch"), false);
  }
});

test("Analysis mismatch review requires known inference and complete nonempty measurements", () => {
  for (const mutate of [
    analysis => { analysis.inferred_cardinality = "unknown"; },
    analysis => { delete analysis.inferred_cardinality; },
    analysis => { for (const field of Object.keys(analysis).filter(field => field.startsWith("validation_"))) analysis[field] = null; },
    analysis => { analysis.validation_source_distinct_count = null; },
    analysis => { analysis.validation_policy_version = null; },
    analysis => { analysis.validation_result = "inconclusive"; analysis.validation_source_non_null_count = 0; analysis.validation_source_distinct_count = 0; analysis.validation_unused_target_count = 4; },
    analysis => { analysis.validation_source_distinct_count = 20; },
    analysis => { analysis.analysis_result_status = "inactive"; },
  ]) {
    const { analysis } = sales();
    analysis.inferred_cardinality = "one_to_one";
    mutate(analysis);
    assert.equal(evaluateQuality(project({ analysis_result: [analysis] }), null).warnings.some(issue => issue.code === "analysis_inferred_cardinality_mismatch"), false);
  }
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
  const graph = project({ logical_entity: [entity("Order")], logical_attribute: [attr("Order", "SystemCode", true), attr("Order", "OrderCode", true)] });
  const decisions = decisionsFor(graph);
  decisions.entities[0].identity_attributes = ["OrderCode"];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("identity_attributes_mismatch"));
  decisions.entities[0].identity_attributes = [" systemcode ", "ORDERCODE"];
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
});

test("provided malformed, duplicate and unknown decisions cannot be hidden by an authored pass flag", () => {
  const graph = project({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  assert.ok(evaluateQuality(graph, null).warnings.some(issue => issue.code === "decision_review_required"));
  const decisions = decisionsFor(graph);
  decisions.reviewed = true;
  decisions.entities.push(structuredClone(decisions.entities[0]));
  decisions.entities.push({ ...structuredClone(decisions.entities[0]), key: { logical_entity_schema_name: "silver", logical_entity_name: "Imaginary" } });
  const result = evaluateQuality(graph, decisions, options);
  for (const expected of ["decisions_missing_or_invalid", "decision_duplicate", "decision_unknown"]) assert.ok(codes(result).includes(expected));
});

test("notes must exist and relationship notes are explicitly labeled inference", () => {
  const { graph, decisions } = sales();
  assert.ok(codes(evaluateQuality(graph, decisions)).includes("note_missing"));
  decisions.relationships[0].evidence = [{ note }];
  assert.ok(evaluateQuality(graph, decisions, options).warnings.some(issue => issue.code === "relationship_inferred"));
  decisions.entities[0].evidence = [{ note: "../outside.md" }];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("note_invalid"));
});

test("append-only decisions can cite retained business notes or applicable active Contexts", () => {
  const context = { context_record_id: "fc39b0b7-af74-5c2c-99f9-9a5ec1f5461e", context_group_name: "Policy",
    status: "active" };
  const document = { context_group_name: "Policy", is_active: true };
  const graph = project({ logical_entity: [entity("Event")], logical_attribute: [attr("Event", "EventID", false, true)],
    context_record: [context], context_group: [document] });
  const decisions = decisionsFor(graph);
  assert.ok(codes(evaluateQuality(graph, decisions)).includes("identity_evidence_missing"));
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
  decisions.entities[0].evidence = [{ dataset: "context_record", key: { context_record_id: "fc39b0b7-af74-5c2c-99f9-9a5ec1f5461e" } }];
  assert.equal(evaluateQuality(graph, decisions).status, "evidence_present");
  document.is_active = false;
  assert.ok(codes(evaluateQuality(graph, decisions)).includes("context_not_applicable"));
});

test("changed natural-key lineage or Analysis rechecks an otherwise unchanged relationship", () => {
  for (const dataset of ["logical_attribute", "analysis_result"]) {
    const { records, decisions, analysis } = sales();
    const baseline = structuredClone(records);
    if (dataset === "analysis_result") analysis.validation_result = "inconclusive";
    else records.logical_attribute[3].sources = [source("OtherCustomer", "CustomerCode")];
    const graph = project(records, { [dataset]: dataset === "analysis_result" ? [analysis] : [records.logical_attribute[3]] }, baseline);
    const result = evaluateQuality(graph, decisions, options);
    assert.equal(result.required, true);
    assert.equal(result.template.relationships.length, 1);
    assert.equal(result.status, "needs_evidence");
  }
});

test("Subject Area findings list unassigned Bronze tables and empty areas once the Project has an area", () => {
  const records = { project_input_scope: ["Order", "Customer", "Invoice", "Landing"].map(scope),
    subject_area: [area("Sales"), area("Billing"), area("Retired", "inactive")],
    subject_area_table: [member(" sales ", "Order"), member("Sales", "Customer", "inactive"), member("Retired", "Invoice")] };
  const metadata = bronze("Order", "Customer", "Invoice");
  metadata.metadataMap.set("source_object", { baseline: [{ ...physical("Landing"), zone_code: "source", is_active: true }] });
  const result = evaluateQuality(project(records), null, metadata);
  // Grouping is never modeling evidence, so it needs no decision review.
  assert.equal(result.status, "not_required");
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.warnings.map((warning) => [warning.code, warning.dataset]),
    [["unassigned_tables", "subject_area_table"], ["empty_subject_areas", "subject_area"]]);
  assert.equal(result.metrics.subject_areas, 2);
  assert.equal(result.metrics.unassigned_table_count, 2);
  assert.deepEqual(result.metrics.unassigned_tables, [physical("Customer"), physical("Invoice")]);
  assert.equal(result.metrics.empty_subject_area_count, 1);
  assert.deepEqual(result.metrics.empty_subject_areas, ["Billing"]);
  assert.equal(result.metrics.logical_physical_support_objects, 0);

  // Only Metadata proves a Bronze table; without an active area nothing is unassigned.
  assert.deepEqual(evaluateQuality(project(records), null).warnings.map((warning) => warning.code), ["empty_subject_areas"]);
  const ungrouped = { ...records, subject_area: [area("Sales", "inactive")], subject_area_table: [] };
  const none = evaluateQuality(project(ungrouped), null, metadata);
  assert.deepEqual(none.warnings, []);
  assert.equal(none.metrics.unassigned_table_count, 0);
});

test("Subject Areas cannot change Logical quality findings or decisions", () => {
  const { records } = sales();
  const pending = { logical_entity: records.logical_entity };
  const graph = project(records, pending, { ...records, logical_entity: [] });
  const decisions = decisionsFor(graph);
  decisions.relationships.forEach(entry => { entry.evidence = [{ note }]; });
  const withoutAreas = evaluateQuality(graph, decisions, options);
  const grouping = { project_input_scope: ["Order", "Customer"].map(scope), subject_area: [area("Sales")],
    subject_area_table: [member("Sales", "Order"), member("Sales", "Customer")] };
  const withAreas = evaluateQuality(project({ ...records, ...grouping }, { ...pending, ...grouping }, { ...records, logical_entity: [] }),
    decisions, { ...options, ...bronze("Order", "Customer") });
  assert.equal(withAreas.status, withoutAreas.status);
  assert.deepEqual(withAreas.errors, withoutAreas.errors);
  assert.deepEqual(withAreas.warnings, withoutAreas.warnings);
  assert.deepEqual(withAreas.template, withoutAreas.template);
  assert.equal(withAreas.metrics.logical_physical_support_objects, withoutAreas.metrics.logical_physical_support_objects);
  assert.equal(withAreas.metrics.logical_physical_support_objects, 2);
  assert.equal(withAreas.metrics.subject_areas, 1);
  assert.equal(withAreas.metrics.unassigned_table_count, 0);
});

test("topology excludes self edges from connectivity and reports framework expansion and unsafe capacity", () => {
  const one = entity("One"), two = entity("Two");
  const audit = { ...attr("One", "CreatedDate"), logical_attribute_is_audit_column: true };
  const money = { ...attr("One", "Cost"), logical_attribute_data_type: "DECIMAL(5,5)" };
  const relationship = { logical_relationship_name: "Parent", logical_relationship_status: "active",
    from_logical_entity_schema_name: "silver", from_logical_entity_name: "One", from_logical_attribute_name: "ParentID",
    to_logical_entity_schema_name: "silver", to_logical_entity_name: "One", to_logical_attribute_name: "OneID", logical_relationship_cardinality: "many_to_one" };
  const records = { logical_entity: [one, two], logical_attribute: [attr("One", "OneID", false, true), audit, money], logical_relationship: [relationship] };
  const result = evaluateQuality(project(records, {}, records), null);
  assert.equal(result.metrics.self_relationships, 1);
  assert.equal(result.metrics.cross_entity_relationships, 0);
  assert.equal(result.metrics.connected_components, 2);
  assert.equal(result.metrics.framework_attributes, 2);
  assert.equal(result.metrics.business_attributes, 1);
  assert.ok(result.warnings.some((warning) => warning.code === "decimal_zero_integer_capacity"));
});

test("evaluator is pure and reports inferred-type divergence only when Metadata is available", () => {
  const graph = project({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  const decisions = decisionsFor(graph);
  const before = core.stableStringify([...graph]);
  const metadataMap = new Map([["bronze_attribute", { baseline: [{ ...physical("Customer", "CustomerCode"), attribute_inferred_data_type: "STRING" }] }]]);
  const result = evaluateQuality(graph, decisions, { ...options, metadataMap });
  assert.equal(core.stableStringify([...graph]), before);
  assert.ok(result.warnings.some((warning) => warning.code === "type_divergence"));
});

test("template is directly usable and root's hashed note-file object is supported", () => {
  const graph = project({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  const template = evaluateQuality(graph, null).template;
  assert.equal(template.schema_version, "1.0");
  const decisions = decisionsFor(graph);
  assert.equal(evaluateQuality(graph, decisions, { noteFiles: { [note]: { sha256: "a".repeat(64) } } }).status, "evidence_present");
});

test("inverse one-to-many direction uses the same proven foreign-key lookup", () => {
  const { records, analysis, relationship } = sales();
  Object.assign(relationship, { from_logical_entity_schema_name: "silver", from_logical_entity_name: "Customer", from_logical_attribute_name: "CustomerID",
    to_logical_entity_schema_name: "silver", to_logical_entity_name: "Order", to_logical_attribute_name: "CustomerCode", logical_relationship_cardinality: "one_to_many" });
  const graph = project(records);
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
  const graph = project({ logical_entity: [entity("Customer")], logical_attribute: [attr("Customer", "CustomerCode", true)] });
  const decisions = decisionsFor(graph);
  for (let index = 0; index < 210; index += 1) decisions.entities.push({ ...structuredClone(decisions.entities[0]), key: { logical_entity_schema_name: "silver", logical_entity_name: `Unknown${index}` } });
  const result = evaluateQuality(graph, decisions, options);
  assert.equal(result.errors.length, 200);
  assert.equal(result.error_count, 210);
  assert.equal(result.truncated, true);
});

test("one-column Analysis cannot prove a surrogate lookup against composite natural identity", () => {
  const { records, analysis } = sales();
  records.logical_attribute.push(attr("Customer", "SystemCode", true));
  const graph = project(records);
  const decisions = decisionsFor(graph);
  decisions.relationships[0].evidence = [{ dataset: "analysis_result", key: recordKey("analysis_result", analysis) }];
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_composite_identity"));

  const context = { context_record_id: "fefd4c8b-8bdd-5386-852c-1ba9c3245759", context_group_name: "Policy",
    status: "active" };
  graph.get("context_group").effective.push({ context_group_name: "Policy", is_active: true });
  graph.get("context_record").effective.push(context);
  decisions.relationships[0].evidence.push({ dataset: "context_record", key: recordKey("context_record", context) });
  assert.equal(evaluateQuality(graph, decisions, options).status, "evidence_present");
  context.status = "inactive";
  assert.ok(codes(evaluateQuality(graph, decisions, options)).includes("analysis_composite_identity"));
});

test("incomplete or malformed modeling records return actionable diagnostics instead of crashing", () => {
  for (const record of [null, 7, {}, { logical_entity_schema_name: "silver", logical_entity_name: " " },
    { ...entity("Customer"), sources: {} }, { ...entity("Customer"), sources: [null] }]) {
    const graph = project({ logical_entity: [record] });
    const result = evaluateQuality(graph, null);
    assert.equal(result.status, "needs_evidence");
    assert.deepEqual(codes(result), ["project_quality_input_invalid"]);
    assert.equal(result.errors[0].dataset, "logical_entity");
  }
  assert.ok(codes(evaluateQuality(null, null)).includes("project_quality_input_invalid"));
  const graph = project({}, { mapping_object: [null], profiling_profile: [{}] });
  assert.equal(evaluateQuality(graph, null).status, "not_required");
});

test("large graph metrics retain full counts while limiting all name examples", () => {
  const names = Array.from({ length: 650 }, (_, index) => `Entity${String(index).padStart(3, "0")}`);
  const records = { logical_entity: names.map(entity), logical_relationship: names.slice(1, 250).map((name, index) => ({
    logical_relationship_name: `Edge${index}`, logical_relationship_status: "active",
    from_logical_entity_schema_name: "silver", from_logical_entity_name: names[index], from_logical_attribute_name: "ID",
    to_logical_entity_schema_name: "silver", to_logical_entity_name: name, to_logical_attribute_name: "ParentID", logical_relationship_cardinality: "one_to_many",
  })) };
  const result = evaluateQuality(project(records), {schema_version: "1.0", entities: [], relationships: [], pass: true});
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

  const isolated = evaluateQuality(project({ logical_entity: names.map(entity) }, {}, { logical_entity: names.map(entity) }), null);
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

test("modeling decisions can remain in records without a compulsory sidecar or Context", () => {
  const {graph} = sales();
  const quality = evaluateQuality(graph, null);
  assert.equal(quality.status, "review_required");
  assert.equal(quality.errors.length, 0);
  assert.ok(quality.warnings.some((issue) => issue.code === "decision_review_required"));
});

test("shared validation checks Analysis counts and applied scope without a decision file", () => {
  const { run } = require("../../atlas/atlas-plugin/workbench/validation/run.js");
  const { analysis } = sales();
  const measured = structuredClone(analysis);
  for (const field of Object.keys(analysis).filter(field => field.startsWith("validation_"))) analysis[field] = null;
  analysis.relationship_basis = "Orders refer to Customer business identifiers; this is metadata inference, not a measured result.";
  const graph = project({ subject_area: [area("Sales")], subject_area_table: [member("Sales", "Order")], analysis_result: [analysis] });
  for (const value of graph.values()) value.schema = { "x-gds-change-set-eligible": true };
  graph.get("analysis_result").schema["x-gds-record-validation"] = { version: "1.0", rules: ["analysis_result"] };
  const objects = ["Order", "Customer"].map(name => ({ ...physical(name), zone_code: "bronze", is_active: true }));
  for (const [name, canonical_key, baseline] of [
    ["project_details", ["project_name"], [{ project_name: "Sales" }]],
    ["project_input_scope", physicalFields, objects],
  ]) graph.set(name, { definition: { name, canonical_key }, schema: {}, baseline, pending: [], effective: baseline });
  const metadata = new Map([
    ["bronze_object", { definition: { name: "bronze_object", record_type: "object" }, schema: {}, baseline: objects }],
    ["bronze_attribute", { definition: { name: "bronze_attribute", record_type: "attribute" }, schema: {},
      baseline: objects.map(object => ({ ...object, attribute_name: "CustomerCode" })) }],
  ]);
  const validate = () => run("project", graph, metadata, { tenantCode: "Tenant", decisions: null });
  const inferred = validate();
  assert.equal(inferred.valid, true, JSON.stringify(inferred.issues));
  assert.equal(inferred.quality.status, "not_required");
  // Customer is in scope but in no area: a review finding, never a blocking error.
  assert.ok(inferred.issues.some(issue => issue.code === "unassigned_tables" && issue.severity === "warning"));

  Object.assign(analysis, measured, { validation_target_distinct_count: 5 });
  const inconsistent = validate();
  assert.equal(inconsistent.valid, false);
  assert.ok(inconsistent.issues.some(issue => issue.dataset === "analysis_result" && issue.code === "schema" && issue.message.includes("counts do not reconcile")));

  Object.assign(analysis, measured, { to_attribute_name: "MissingAttribute" });
  const outsideScope = validate();
  assert.equal(outsideScope.valid, false);
  assert.ok(outsideScope.issues.some(issue => issue.dataset === "analysis_result" && issue.code === "project_input_reference_invalid"));
});


test("disconnected connected pairs prompt review even without isolated Entities", () => {
  const names = ["Customer", "Order", "Product", "Category"];
  const edge = (from, to, status = "active") => ({
    logical_relationship_name: `${from}${to}`, logical_relationship_status: status,
    from_logical_entity_schema_name: "silver", from_logical_entity_name: from, from_logical_attribute_name: `${from}ID`,
    to_logical_entity_schema_name: "silver", to_logical_entity_name: to, to_logical_attribute_name: `${to}ID`,
    logical_relationship_cardinality: "many_to_one",
  });
  const bridge = edge("Order", "Product", "inactive");
  const records = { logical_entity: names.map(entity),
    logical_attribute: names.map(name => attr(name, `${name}ID`, true)),
    logical_relationship: [edge("Order", "Customer"), edge("Product", "Category"), bridge] };
  const graph = project(records);
  const before = core.stableStringify([...graph]);
  const disconnected = evaluateQuality(graph, null);
  assert.deepEqual(disconnected.errors, []);
  assert.equal(disconnected.metrics.connected_components, 2);
  assert.equal(disconnected.metrics.isolated_entity_count, 0);
  assert.deepEqual(disconnected.metrics.components, [["silver.Customer", "silver.Order"], ["silver.Category", "silver.Product"]]);
  assert.ok(disconnected.warnings.some(warning => warning.code === "disconnected_components" && /Ask the user/.test(warning.message) && /do not invent joins/.test(warning.message)));
  assert.ok(!disconnected.warnings.some(warning => warning.code === "isolated_entities"));
  assert.equal(core.stableStringify([...graph]), before);

  bridge.logical_relationship_status = "active";
  const connected = evaluateQuality(graph, null);
  assert.equal(connected.metrics.connected_components, 1);
  assert.ok(!connected.warnings.some(warning => warning.code === "disconnected_components"));
});

test("intentional standalone Entities remain warnings and unchanged locked Projects need no new evidence", () => {
  const records = { logical_entity: [{ ...entity("Calendar"), logical_entity_is_locked: true, sources: [] }],
    logical_attribute: [attr("Calendar", "CalendarID", true)] };
  const graph = project(records, {}, records);
  const before = core.stableStringify([...graph]);
  const unchanged = evaluateQuality(graph, null);
  assert.equal(unchanged.required, false);
  assert.equal(unchanged.status, "not_required");
  assert.deepEqual(unchanged.errors, []);
  assert.equal(unchanged.metrics.connected_components, 1);
  assert.deepEqual(unchanged.metrics.isolated_entities, ["silver.Calendar"]);
  assert.ok(unchanged.warnings.some(warning => warning.code === "isolated_entities" && /Ask the user/.test(warning.message) && /intentionally standalone/.test(warning.message)));
  assert.ok(!unchanged.warnings.some(warning => warning.code === "disconnected_components"));
  assert.equal(core.stableStringify([...graph]), before);

  const empty = evaluateQuality(project({}), null);
  assert.equal(empty.status, "not_required");
  assert.ok(!empty.warnings.some(warning => ["isolated_entities", "disconnected_components"].includes(warning.code)));
});
