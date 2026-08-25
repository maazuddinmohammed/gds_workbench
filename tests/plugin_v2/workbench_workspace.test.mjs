import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const workspaceModule = require("../../plugins/v2/gds/workbench/workspace.js");

class MemoryFileHandle {
  constructor(name, text = "") {
    this.kind = "file";
    this.name = name;
    this.text = text;
  }

  async getFile() {
    const text = this.text;
    return {
      size: new TextEncoder().encode(text).length,
      text: async () => text,
      arrayBuffer: async () => new TextEncoder().encode(text).buffer,
    };
  }

  async createWritable() {
    let next = "";
    return {
      write: async (value) => {
        next = typeof value === "string" ? value : new TextDecoder().decode(value);
      },
      close: async () => {
        this.text = next;
      },
      abort: async () => {},
    };
  }
}

class MemoryDirectoryHandle {
  constructor(name) {
    this.kind = "directory";
    this.name = name;
    this.entries = new Map();
  }

  directory(name) {
    const handle = new MemoryDirectoryHandle(name);
    this.entries.set(name, handle);
    return handle;
  }

  file(name, text = "") {
    const handle = new MemoryFileHandle(name, text);
    this.entries.set(name, handle);
    return handle;
  }

  async getDirectoryHandle(name, options = {}) {
    const value = this.entries.get(name);
    if (value?.kind === "directory") return value;
    if (options.create) return this.directory(name);
    throw new DOMException("Missing directory", "NotFoundError");
  }

  async getFileHandle(name, options = {}) {
    const value = this.entries.get(name);
    if (value?.kind === "file") return value;
    if (options.create) return this.file(name);
    throw new DOMException("Missing file", "NotFoundError");
  }

  async *values() {
    yield* this.entries.values();
  }
}

function digest(text) {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

function nestedFile(directory, relativePath) {
  let current = directory;
  const segments = relativePath.split("/");
  for (const segment of segments.slice(0, -1)) current = current.entries.get(segment);
  return current.entries.get(segments.at(-1));
}

function signSnapshot(metadata, catalog) {
  const catalogHandle = metadata.entries.get("catalog.json");
  catalogHandle.text = JSON.stringify(catalog);
  const paths = [
    "catalog.json",
    "data/source_object.jsonl",
    "schemas/source_object.schema.json",
  ];
  const members = paths.map((path) => {
    const text = nestedFile(metadata, path).text;
    return {
      path,
      size_bytes: new TextEncoder().encode(text).length,
      sha256: digest(text),
    };
  });
  metadata.entries.get("manifest.json").text = JSON.stringify({
    snapshot_kind: "metadata",
    snapshot_id: "snapshot-01",
    tenant_code: "TENANT_A",
    catalog: { path: "catalog.json", sha256: members[0].sha256 },
    members,
  });
}

function signModelSnapshot(model, modelId, modelName, revision, snapshotId, dataset = null) {
  const paths = ["catalog.json"];
  let sections = [];
  if (dataset) {
    const rowsFile = `data/${dataset.name}.jsonl`;
    const schemaFile = `schemas/${dataset.name}.schema.json`;
    model.directory("data").file(`${dataset.name}.jsonl`, dataset.rows);
    model.directory("schemas").file(`${dataset.name}.schema.json`, JSON.stringify(dataset.schema));
    paths.push(rowsFile, schemaFile);
    sections = [
      {
        name: "model",
        datasets: [
          {
            name: dataset.name,
            record_type: dataset.name,
            row_count: 1,
            canonical_key: [],
            rows_file: rowsFile,
            schema_file: schemaFile,
          },
        ],
      },
    ];
  }
  const catalog = JSON.stringify({
    snapshot_kind: "model",
    model: {
      model_id: modelId,
      model_name: modelName,
      model_revision: revision,
    },
    sections,
  });
  model.file("catalog.json", catalog);
  const members = paths.map((path) => {
    const text = nestedFile(model, path).text;
    return {
      path,
      size_bytes: new TextEncoder().encode(text).length,
      sha256: digest(text),
    };
  });
  model.file(
    "manifest.json",
    JSON.stringify({
      snapshot_kind: "model",
      snapshot_id: snapshotId,
      model_id: modelId,
      model_name: modelName,
      model_revision: revision,
      catalog: { path: "catalog.json", sha256: members[0].sha256 },
      members,
    }),
  );
}

function buildSession() {
  const session = new MemoryDirectoryHandle("01");
  session.file(
    "session.json",
    JSON.stringify({
      current: "01",
      tasks: [["01", "metadata", "Edit metadata", "doing"]],
    }),
  );
  session.directory("tasks").file("01.json", '["Edit","Review"]');
  const metadata = session.directory("metadata").directory("metadata-snapshot");
  metadata.file("manifest.json");
  const catalog = {
    snapshot_kind: "metadata",
    sections: [
      {
        name: "operational",
        datasets: [
          {
            name: "source_object",
            record_type: "source_object",
            row_count: 1,
            canonical_key: ["tenant_code", "system_code", "object_name"],
            rows_file: "data/source_object.jsonl",
            schema_file: "schemas/source_object.schema.json",
          },
        ],
      },
    ],
  };
  metadata.file("catalog.json");
  metadata.directory("data").file(
    "source_object.jsonl",
    '{"tenant_code":"T","system_code":"CRM","object_name":"Customer","is_active":true}\n',
  );
  metadata.directory("schemas").file(
    "source_object.schema.json",
    JSON.stringify({
      type: "object",
      additionalProperties: false,
      properties: { object_name: { type: "string" } },
      required: ["object_name"],
      "x-gds-change-set-eligible": true,
      "x-gds-references": [],
    }),
  );
  session.directory("metadata-change-set");
  session.directory("model");
  session.directory("model-change-set");
  session.directory("code");
  signSnapshot(metadata, catalog);
  return { session, metadata, catalog };
}

test("Refresh rereads replaced Snapshot catalog", async () => {
  const { session, metadata, catalog } = buildSession();
  const workspace = await workspaceModule.connect(session);
  assert.equal(workspace.area("metadata").datasets[0].row_count, 1);

  catalog.sections[0].datasets[0].row_count = 2;
  signSnapshot(metadata, catalog);
  await workspace.refresh();

  assert.equal(workspace.area("metadata").datasets[0].row_count, 2);
});

test("Refresh rejects a catalog that no longer matches its manifest SHA-256", async () => {
  const { session, metadata, catalog } = buildSession();
  const workspace = await workspaceModule.connect(session);

  catalog.sections[0].datasets[0].row_count = 2;
  metadata.entries.get("catalog.json").text = JSON.stringify(catalog);

  await assert.rejects(workspace.refresh(), /catalog does not match its Snapshot SHA-256/);
});

test("Dataset load rejects rows that no longer match the manifest SHA-256", async () => {
  const { session, metadata } = buildSession();
  const workspace = await workspaceModule.connect(session);
  const rows = nestedFile(metadata, "data/source_object.jsonl");
  rows.text = rows.text.replace("Customer", "customer");

  await assert.rejects(
    workspace.loadDataset("metadata", "source_object"),
    /source_object rows does not match its Snapshot SHA-256/,
  );
});

test("Save accepts a JSON draft, marks review, and detects external edits", async () => {
  const { session } = buildSession();
  const workspace = await workspaceModule.connect(session);
  const loaded = await workspace.loadDataset("metadata", "source_object");
  assert.equal(loaded.pendingDigest, null);

  const saved = await workspace.saveDataset(
    "metadata",
    "source_object",
    '[{"object_name":"domain-invalid-but-json-valid"}]',
    null,
  );
  assert.equal(saved.records.length, 1);
  assert.equal(JSON.parse(session.entries.get("session.json").text).tasks[0][3], "review");

  const pending = session.entries
    .get("metadata-change-set")
    .entries.get("source_object.json");
  pending.text += " ";
  await assert.rejects(
    workspace.saveDataset("metadata", "source_object", "[]", saved.pendingDigest),
    /external-edit conflict/,
  );
});

test("stale Snapshots reject save, validation digest, and acceptance", async () => {
  const { session } = buildSession();
  const state = JSON.parse(session.entries.get("session.json").text);
  state.stale = ["metadata"];
  state.tasks[0][3] = "review";
  session.entries.get("session.json").text = JSON.stringify(state);
  const workspace = await workspaceModule.connect(session);

  await assert.rejects(
    workspace.saveDataset("metadata", "source_object", "[]", null),
    /metadata Snapshot is stale/,
  );
  await assert.rejects(workspace.changeSetDigest("metadata"), /metadata Snapshot is stale/);
  await assert.rejects(
    workspace.accept("metadata", "unused", { valid: true }, null),
    /metadata Snapshot is stale/,
  );
});

test("schemas not explicitly Change Set eligible cannot be saved or inventoried", async () => {
  const direct = buildSession();
  nestedFile(direct.metadata, "schemas/source_object.schema.json").text = JSON.stringify({
    type: "object",
    "x-gds-change-set-eligible": false,
  });
  signSnapshot(direct.metadata, direct.catalog);
  const directWorkspace = await workspaceModule.connect(direct.session);
  await assert.rejects(
    directWorkspace.saveDataset("metadata", "source_object", "[]", null),
    /source_object is not Change Set eligible/,
  );

  const existing = buildSession();
  nestedFile(existing.metadata, "schemas/source_object.schema.json").text = JSON.stringify({
    type: "object",
  });
  signSnapshot(existing.metadata, existing.catalog);
  existing.session.entries
    .get("metadata-change-set")
    .file("source_object.json", "[]\n");
  const existingWorkspace = await workspaceModule.connect(existing.session);
  await assert.rejects(
    existingWorkspace.loadArea("metadata"),
    /source_object is not Change Set eligible/,
  );
});

test("Change Set inventory rejects unknown and prohibited dataset files", async () => {
  const unknown = buildSession();
  unknown.session.entries.get("metadata-change-set").file("surprise.json", "[]");
  const unknownWorkspace = await workspaceModule.connect(unknown.session);
  await assert.rejects(
    unknownWorkspace.loadArea("metadata"),
    /Unknown metadata Change Set dataset surprise/,
  );

  const prohibited = buildSession();
  prohibited.session.entries.get("model-change-set").file("model_scope.json", "[]");
  const prohibitedWorkspace = await workspaceModule.connect(prohibited.session);
  await assert.rejects(
    prohibitedWorkspace.changeSetDigest("model"),
    /model_scope mutation is not exposed by Workbench/,
  );
});

test("Model Details remains Change Set eligible while Model Scope is read-only", async () => {
  const { session } = buildSession();
  const state = JSON.parse(session.entries.get("session.json").text);
  state.tasks = [["01", "model", "Edit Model Details", "doing"]];
  session.entries.get("session.json").text = JSON.stringify(state);
  signModelSnapshot(
    session.entries.get("model"),
    41,
    "Customer Model",
    8,
    "model-snapshot-01",
    {
      name: "model_details",
      rows: '{"model_purpose":"Current purpose"}\n',
      schema: {
        type: "object",
        additionalProperties: false,
        properties: { model_purpose: { type: "string" } },
        required: ["model_purpose"],
        "x-gds-change-set-eligible": true,
      },
    },
  );
  const workspace = await workspaceModule.connect(session);

  const saved = await workspace.saveDataset(
    "model",
    "model_details",
    '[{"model_purpose":"Updated purpose"}]',
    null,
  );

  assert.equal(saved.records[0].model_purpose, "Updated purpose");
  assert.ok(session.entries.get("model-change-set").entries.has("model_details.json"));
});

test("failed Refresh preserves the previously loaded workspace", async () => {
  const { session, metadata, catalog } = buildSession();
  const workspace = await workspaceModule.connect(session);

  catalog.sections[0].datasets[0].row_count = 2;
  signSnapshot(metadata, catalog);
  const model = session.entries.get("model");
  model.file("manifest.json", JSON.stringify({ snapshot_kind: "model" }));
  model.file("catalog.json", JSON.stringify({ snapshot_kind: "model", sections: [] }));

  await assert.rejects(workspace.refresh(), /model Snapshot manifest has no member inventory/);
  assert.equal(workspace.area("metadata").datasets[0].row_count, 1);
});

test("acceptance rejects a Snapshot replaced after validation", async () => {
  const { session, metadata, catalog } = buildSession();
  const workspace = await workspaceModule.connect(session);
  const saved = await workspace.saveDataset(
    "metadata",
    "source_object",
    '[{"object_name":"Customer"}]',
    null,
  );
  const snapshot = workspace.area("metadata");
  const validation = {
    area: "metadata",
    digest: await workspace.changeSetDigest("metadata"),
    snapshot_id: snapshot.manifest.snapshot_id,
    snapshot_revision: snapshot.manifest.model_revision ?? null,
    snapshot_digest: snapshot.manifestDigest,
    valid: true,
    issues: [],
  };

  catalog.sections[0].datasets[0].row_count = 2;
  signSnapshot(metadata, catalog);

  await assert.rejects(
    workspace.accept("metadata", validation.digest, validation, null),
    /Snapshot changed after validation/,
  );
  assert.equal(saved.records.length, 1);
});

test("Workbench binds one Model per session and preserves it on mismatch", async () => {
  const { session } = buildSession();
  const model = session.entries.get("model");
  signModelSnapshot(model, 41, "Customer Model", 8, "model-snapshot-01");

  const workspace = await workspaceModule.connect(session);

  assert.deepEqual(workspace.state.model, [41, "Customer Model"]);
  assert.deepEqual(JSON.parse(session.entries.get("session.json").text).model, [
    41,
    "Customer Model",
  ]);

  signModelSnapshot(model, 42, "Other Model", 1, "model-snapshot-02");
  await assert.rejects(workspace.refresh(), /start a new session for Model 42/);
  assert.deepEqual(workspace.state.model, [41, "Customer Model"]);
});
