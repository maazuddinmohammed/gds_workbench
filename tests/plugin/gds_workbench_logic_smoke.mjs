import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import vm from "node:vm";

const source = await readFile(new URL("../../plugins/gds/skills/open-gds-metadata-workbench/assets/workbench/logic.js", import.meta.url), "utf8");
const context = { console, JSON, Object, Array, Set, Map, RegExp, Number, String, Error, TextEncoder };
context.globalThis = context;
vm.runInNewContext(source, context, { filename: "logic.js" });
const logic = context.GdsWorkbenchLogic;
assert.ok(logic);
assert.equal(logic.ELIGIBLE_DATASETS.length, 16);
assert.equal(logic.METADATA_SNAPSHOT_DATASETS.length, 29);

const schema = {
  type: "object",
  additionalProperties: false,
  properties: {
    tenant_code: { type: "string", minLength: 1, pattern: "\\S" },
    object_name: { type: "string", minLength: 1 },
    description: { anyOf: [{ type: "string" }, { type: "null" }] },
    zone_code: { type: "string", const: "source" },
    is_active: { type: "boolean" }
  },
  required: ["tenant_code", "object_name", "description", "zone_code", "is_active"],
  "x-gds-dataset": "source_object",
  "x-gds-database-ids-included": false,
  "x-gds-change-set-eligible": true,
  "x-gds-canonical-key": ["tenant_code", "object_name"],
  "x-gds-unique-constraints": [["tenant_code", "object_name"]],
  "x-gds-key-normalization": {
    version: "1.0",
    string_field_suffixes: ["_code", "_name", "_schema"],
    trim_code_points: ["U+0020"],
    case: "unicode-lowercase",
    unicode_normalization: "none",
    other_values: "identity"
  }
};
const first = { tenant_code: "TENANT", object_name: "Order", description: null, zone_code: "source", is_active: true };
assert.equal(logic.validateSchema(schema, "source_object", true), schema);
assert.equal(logic.normalizeKeyValue("object_name", " Order ", schema), "order");
assert.equal(logic.normalizeKeyValue("process_location", " /Workspace/Load ", schema), " /Workspace/Load ");
assert.equal(logic.validateRecord(first, schema).length, 0);
assert.match(logic.validateRecord({ ...first, object_id: 4 }, schema)[0].message, /database IDs/i);

let merged = logic.mergeRecord([], first, schema, "source_object");
assert.equal(merged.action, "inserted");
assert.equal(merged.rows.length, 1);
merged = logic.mergeRecord(merged.rows, { ...first, tenant_code: " tenant ", object_name: "order", is_active: false }, schema, "source_object");
assert.equal(merged.action, "replaced");
assert.equal(merged.rows.length, 1);
assert.equal(merged.rows[0].is_active, false);
assert.equal(logic.classifyRecord(merged.rows[0], [first], schema), "deactivate");
assert.equal(logic.diffRecord(first, first, schema).action, "no_change");
assert.equal(logic.diffRecord({ ...first, description: "Changed" }, first, schema).action, "update");

const batch = logic.mergeRecords([], [first, { ...first, object_name: "Customer" }], schema, "source_object");
assert.equal(batch.action, "merged");
assert.equal(batch.rows.length, 2);
const rejectedBatch = logic.mergeRecords(
  [first],
  [{ ...first, object_name: "Customer" }, { ...first, object_name: "Product", object_id: 10 }],
  schema,
  "source_object"
);
assert.equal(rejectedBatch.action, "rejected");
assert.equal(rejectedBatch.rows.length, 1);

const nullKeySchema = {
  ...schema,
  properties: { ...schema.properties, description: { anyOf: [{ type: "string" }, { type: "null" }] } },
  "x-gds-unique-constraints": [["description"]]
};
assert.equal(logic.validateDataset([
  first,
  { ...first, object_name: "Customer", description: null }
], nullKeySchema).some(issue => /Duplicates row/.test(issue.message)), true);

const datedSchema = {
  ...schema,
  properties: {
    ...schema.properties,
    run_date: { type: "string", format: "date" },
    started_at: { type: "string", format: "date-time" },
    priority: { type: "integer", exclusiveMinimum: 0, exclusiveMaximum: 10 }
  },
  required: [...schema.required, "run_date", "started_at", "priority"]
};
const dated = { ...first, run_date: "2026-02-29", started_at: "2026-01-01T10:00:00", priority: 10 };
assert.equal(logic.validateRecord(dated, datedSchema).length, 3);
assert.equal(logic.validateRecord({ ...dated, run_date: "2028-02-29", started_at: "2026-01-01T10:00:00Z", priority: 9 }, datedSchema).length, 0);

assert.throws(
  () => logic.serializeDataset([{ ...first, description: "x".repeat(logic.MAX_DATASET_BYTES) }]),
  /16 MiB/
);
assert.equal(logic.validateDataset(Array(logic.MAX_DATASET_RECORDS + 1).fill(first), schema)[0].field, "$");

assert.throws(() => logic.safePathParts("../manifest.json"), /unsafe/);
assert.deepEqual([...logic.safePathParts("schemas/source_object.schema.json")], ["schemas", "source_object.schema.json"]);
const localState = logic.createLocalState({ schema_version: "2.0", snapshot_kind: "metadata", tenant_code: "TENANT", snapshot_id: "snapshot" });
assert.equal(localState.server_change_set.status, "local");
assert.equal(localState.tenant.tenant_id, null);

assert.equal(logic.MODEL_DATASETS.length, 19);
assert.equal(logic.MAX_MODEL_DATASET_RECORDS, 20000);
assert.equal(logic.MAX_MODEL_TOTAL_RECORDS, 50000);
assert.equal(logic.MAX_MODEL_SECTION_BYTES, 16777216);
const modelDetailsSchema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  type: "object",
  additionalProperties: false,
  $defs: {},
  properties: {
    model_name: { type: "string", minLength: 1, pattern: "\\S" },
    model_description: { anyOf: [{ type: "string", minLength: 1 }, { type: "null" }] },
    silver_model_naming_template: { anyOf: [{ type: "object" }, { type: "null" }] },
    silver_model_audit_columns_template: { anyOf: [{ type: "object" }, { type: "null" }] },
    gold_model_naming_template: { anyOf: [{ type: "object" }, { type: "null" }] },
    gold_model_technical_columns_template: { anyOf: [{ type: "object" }, { type: "null" }] },
    gold_model_audit_columns_template: { anyOf: [{ type: "object" }, { type: "null" }] }
  },
  required: [
    "model_name", "model_description", "silver_model_naming_template",
    "silver_model_audit_columns_template", "gold_model_naming_template",
    "gold_model_technical_columns_template", "gold_model_audit_columns_template"
  ],
  "x-gds-dataset": "model_details",
  "x-gds-section": "model_scope",
  "x-gds-database-ids-included": false,
  "x-gds-change-set-eligible": true,
  "x-gds-canonical-key": []
};
const modelDetails = {
  model_name: "Sales Model",
  model_description: null,
  silver_model_naming_template: null,
  silver_model_audit_columns_template: null,
  gold_model_naming_template: null,
  gold_model_technical_columns_template: null,
  gold_model_audit_columns_template: null
};
assert.equal(logic.validateSchema(modelDetailsSchema, "model_details", true), modelDetailsSchema);
assert.equal(logic.validateRecord(modelDetails, modelDetailsSchema).length, 0);
assert.equal(logic.validateDataset([modelDetails, modelDetails], modelDetailsSchema).some(issue => /singleton/.test(issue.message)), true);
assert.equal(logic.normalizeKeyValue("model_name", " Sales ", modelDetailsSchema), "sales");

const nestedModelSchema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  type: "object",
  additionalProperties: false,
  $defs: {
    PhysicalObject: {
      type: "object",
      additionalProperties: false,
      properties: {
        tenant_code: { type: "string", minLength: 1 },
        object_name: { type: "string", minLength: 1 }
      },
      required: ["tenant_code", "object_name"]
    },
    ObjectSupport: {
      type: "object",
      additionalProperties: false,
      properties: {
        support_source_type: { type: "string", const: "object" },
        source_object: { $ref: "#/$defs/PhysicalObject" },
        support_role: { anyOf: [{ type: "string" }, { type: "null" }] }
      },
      required: ["support_source_type", "source_object", "support_role"]
    },
    AssertionSupport: {
      type: "object",
      additionalProperties: false,
      properties: {
        support_source_type: { type: "string", const: "assertion" },
        assertion_key: { type: "string", minLength: 1 },
        support_role: { anyOf: [{ type: "string" }, { type: "null" }] }
      },
      required: ["support_source_type", "assertion_key", "support_role"]
    }
  },
  properties: {
    conceptual_object_name: { type: "string", minLength: 1 },
    supports: {
      type: "array",
      items: { oneOf: [{ $ref: "#/$defs/ObjectSupport" }, { $ref: "#/$defs/AssertionSupport" }] }
    }
  },
  required: ["conceptual_object_name", "supports"],
  "x-gds-dataset": "conceptual_object",
  "x-gds-section": "conceptual",
  "x-gds-database-ids-included": false,
  "x-gds-change-set-eligible": true,
  "x-gds-canonical-key": ["conceptual_object_name"]
};
const nestedModelRecord = {
  conceptual_object_name: "Customer",
  supports: [{ support_source_type: "object", source_object: { tenant_code: "T", object_name: "customer" }, support_role: null }]
};
assert.equal(logic.validateSchema(nestedModelSchema, "conceptual_object", true), nestedModelSchema);
assert.equal(logic.validateRecord(nestedModelRecord, nestedModelSchema).length, 0);
assert.equal(logic.validateRecord({ ...nestedModelRecord, supports: [{ ...nestedModelRecord.supports[0], unexpected: true }] }, nestedModelSchema).some(issue => issue.field.includes("supports[0].unexpected")), true);
assert.equal(logic.validateDataset(Array(logic.MAX_MODEL_DATASET_RECORDS + 1).fill(nestedModelRecord), nestedModelSchema)[0].field, "$");

const modelManifest = {
  schema_version: "2.0",
  snapshot_kind: "model",
  snapshot_id: "model-snapshot",
  model_id: 41,
  model_name: "Sales Model",
  model_revision: 7
};
const modelState = logic.createLocalState(modelManifest);
assert.equal(modelState.snapshot.path, "../model-snapshot");
assert.equal(modelState.server_change_set.model_change_set_id, null);
const modelDatasets = Object.fromEntries(logic.MODEL_DATASETS.map(name => [name, []]));
modelDatasets.model_details = [modelDetails];
modelDatasets.conceptual_object = [nestedModelRecord];
const proposed = logic.modelSnapshotFromDatasets(modelManifest, modelDatasets);
assert.equal(proposed.model_revision, 7);
assert.equal(proposed.model_scope.details.model_name, "Sales Model");
assert.equal(JSON.stringify(logic.modelSnapshotToDatasets(proposed)), JSON.stringify(modelDatasets));
const overlaid = logic.overlayDataset([nestedModelRecord], [{ ...nestedModelRecord, conceptual_object_name: " customer " }], nestedModelSchema);
assert.equal(overlaid.length, 1);
assert.equal(overlaid[0].conceptual_object_name, " customer ");
const stage = logic.modelStageDocument(modelManifest, modelState, new Map([["conceptual_object", [nestedModelRecord]]]));
assert.equal(stage.model_id, 41);
assert.equal(stage.changes[0].dataset, "conceptual_object");
assert.equal(stage.model_change_set_id, null);
const partialBinding = logic.clone(modelState);
partialBinding.server_change_set.model_change_set_id = "4a4d40a7-7fc9-48ab-b1dc-c14e23ee64ad";
assert.throws(
  () => logic.modelStageDocument(modelManifest, partialBinding, new Map([["conceptual_object", [nestedModelRecord]]])),
  /bound together/
);
assert.throws(() => logic.modelStageDocument(modelManifest, modelState, new Map()), /at least one/);
assert.throws(
  () => logic.modelStageDocument(modelManifest, modelState, new Map([
    ["conceptual_object", Array(20000).fill(nestedModelRecord)],
    ["conceptual_relationship", Array(20000).fill(nestedModelRecord)],
    ["logical_submodel", Array(10001).fill(nestedModelRecord)]
  ])),
  /50,000 total/
);
assert.throws(
  () => logic.modelStageDocument(modelManifest, modelState, new Map([
    ["conceptual_object", [{ value: "x".repeat(9 * 1024 * 1024) }]],
    ["conceptual_relationship", [{ value: "x".repeat(9 * 1024 * 1024) }]]
  ])),
  /section exceeds 16 MiB/
);
assert.equal(JSON.parse(logic.serializeJsonDocument(proposed).content).model_revision, 7);

if (process.argv[2]) {
  const snapshotRoot = path.resolve(process.argv[2]);
  const manifest = JSON.parse(await readFile(path.join(snapshotRoot, "manifest.json"), "utf8"));
  const catalog = JSON.parse(await readFile(path.join(snapshotRoot, "catalog.json"), "utf8"));
  const catalogDatasets = catalog.sections.flatMap(section => section.datasets);
  assert.equal(catalogDatasets.length, 29);
  for (const dataset of catalogDatasets) {
    const datasetSchema = JSON.parse(await readFile(path.join(snapshotRoot, dataset.schema_file), "utf8"));
    const datasetRows = logic.parseRows(await readFile(path.join(snapshotRoot, dataset.rows_file), "utf8"), dataset.rows_file);
    assert.equal(logic.validateSchema(datasetSchema, dataset.name, false), datasetSchema);
    assert.equal(logic.validateDataset(datasetRows, datasetSchema).length, 0, `${dataset.name} validates`);
  }
  const sourceObject = catalogDatasets.find(dataset => dataset.name === "source_object");
  assert.ok(sourceObject, "real Snapshot catalog contains source_object");
  const liveSchema = JSON.parse(await readFile(path.join(snapshotRoot, sourceObject.schema_file), "utf8"));
  const liveRows = logic.parseRows(await readFile(path.join(snapshotRoot, sourceObject.rows_file), "utf8"), sourceObject.rows_file);
  assert.equal(liveSchema["x-gds-change-set-eligible"], true);
  assert.equal(logic.validateDataset(liveRows, liveSchema).length, 0);
  assert.equal(logic.createLocalState(manifest).snapshot.snapshot_id, manifest.snapshot_id);
  if (liveRows.length) {
    const liveMerge = logic.mergeRecord([], liveRows[0], liveSchema, "source_object");
    assert.equal(liveMerge.action, "inserted");
    assert.equal(liveMerge.errors.length, 0);
  }
}

if (process.argv[3]) {
  const modelRoot = path.resolve(process.argv[3]);
  const manifest = JSON.parse(await readFile(path.join(modelRoot, "manifest.json"), "utf8"));
  const catalog = JSON.parse(await readFile(path.join(modelRoot, "catalog.json"), "utf8"));
  const datasets = {};
  const catalogDatasets = catalog.sections.flatMap(section => section.datasets);
  assert.equal(catalogDatasets.length, 19);
  for (const dataset of catalogDatasets) {
    const liveSchema = JSON.parse(await readFile(path.join(modelRoot, dataset.schema_file), "utf8"));
    const rows = logic.parseRows(await readFile(path.join(modelRoot, dataset.rows_file), "utf8"), dataset.rows_file);
    assert.equal(logic.validateSchema(liveSchema, dataset.name, true), liveSchema);
    let validation;
    try {
      validation = logic.validateDataset(rows, liveSchema);
    } catch (error) {
      error.message = `${dataset.name}: ${error.message}`;
      throw error;
    }
    assert.equal(validation.length, 0, `${dataset.name} validates: ${JSON.stringify(validation)}`);
    datasets[dataset.name] = rows;
  }
  assert.ok(datasets.mapping_dependency);
  assert.ok(datasets.mapping_object);
  assert.ok(datasets.mapping_attribute);
  const aggregate = logic.modelSnapshotFromDatasets(manifest, datasets);
  assert.equal(JSON.stringify(logic.modelSnapshotToDatasets(aggregate)), JSON.stringify(datasets));
  if (process.argv[4]) {
    await writeFile(path.resolve(process.argv[4]), logic.serializeJsonDocument(aggregate).content, "utf8");
  }
  if (process.argv[5]) {
    const bound = logic.createLocalState(manifest);
    bound.server_change_set.model_change_set_id = "4a4d40a7-7fc9-48ab-b1dc-c14e23ee64ad";
    bound.server_change_set.draft_revision = 3;
    bound.server_change_set.status = "active";
    const stageDocument = logic.modelStageDocument(manifest, bound, datasets);
    await writeFile(path.resolve(process.argv[5]), logic.serializeJsonDocument(stageDocument).content, "utf8");
  }
}

console.log("GDS Data Workbench logic smoke tests passed");
