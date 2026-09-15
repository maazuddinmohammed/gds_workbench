(function (root, factory) {
  "use strict";
  let core = root.GDSCore;
  let cryptoApi = root.crypto;
  if (typeof module === "object" && module.exports) {
    core = require("./core.js");
    cryptoApi = require("node:crypto").webcrypto;
  }
  const api = factory(core, cryptoApi);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSWorkspace = api;
})(typeof globalThis === "object" ? globalThis : this, function (core, cryptoApi) {
  "use strict";

  const encoder = new TextEncoder();
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  async function sha256Bytes(bytes) {
    const digest = await cryptoApi.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)]
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("");
  }

  async function readFile(handle) {
    const file = await handle.getFile();
    const bytes = new Uint8Array(await file.arrayBuffer());
    return {
      bytes,
      text: new TextDecoder("utf-8", { fatal: true }).decode(bytes),
      digest: await sha256Bytes(bytes),
    };
  }

  async function optionalFile(directory, name) {
    try {
      return await directory.getFileHandle(name);
    } catch (error) {
      if (error?.name === "NotFoundError") return null;
      throw error;
    }
  }

  async function optionalDirectory(directory, name) {
    try {
      return await directory.getDirectoryHandle(name);
    } catch (error) {
      if (error?.name === "NotFoundError") return null;
      throw error;
    }
  }

  function parseJson(text, label) {
    try {
      return JSON.parse(text);
    } catch (_error) {
      throw new Error(`${label} is not valid JSON.`);
    }
  }

  function safeSegments(relativePath) {
    if (
      typeof relativePath !== "string" ||
      !relativePath ||
      relativePath.includes("\\") || /[:\u0000-\u001f\u007f]/.test(relativePath) ||
      relativePath.startsWith("/")
    ) {
      throw new Error("Snapshot catalog contains an unsafe path.");
    }
    const segments = relativePath.split("/");
    if (segments.some((segment) => !segment || segment === "." || segment === "..")) {
      throw new Error("Snapshot catalog contains an unsafe path.");
    }
    return segments;
  }

  async function fileAt(root, relativePath) {
    const segments = safeSegments(relativePath);
    let directory = root;
    for (const segment of segments.slice(0, -1)) {
      directory = await directory.getDirectoryHandle(segment);
    }
    return directory.getFileHandle(segments.at(-1));
  }

  function manifestMembers(manifest, area) {
    if (!Array.isArray(manifest?.members)) {
      throw new Error(`${area} Snapshot manifest has no member inventory.`);
    }
    const members = new Map();
    for (const member of manifest.members) {
      if (
        !member ||
        typeof member !== "object" ||
        typeof member.path !== "string" ||
        typeof member.sha256 !== "string" ||
        !/^[0-9a-f]{64}$/.test(member.sha256) ||
        !Number.isInteger(member.size_bytes) ||
        member.size_bytes < 0 ||
        members.has(member.path)
      ) {
        throw new Error(`${area} Snapshot manifest member inventory is invalid.`);
      }
      safeSegments(member.path);
      members.set(member.path, member);
    }
    const catalogMember = members.get("catalog.json");
    if (
      manifest.catalog?.path !== "catalog.json" ||
      typeof manifest.catalog.sha256 !== "string" ||
      manifest.catalog.sha256 !== catalogMember?.sha256
    ) {
      throw new Error(`${area} Snapshot catalog manifest entry is invalid.`);
    }
    return members;
  }

  async function verifiedMember(snapshot, relativePath, label) {
    const member = snapshot.members.get(relativePath);
    if (!member) throw new Error(`${label} is not authorized by the Snapshot manifest.`);
    const file = await readFile(await fileAt(snapshot.root, relativePath));
    if (file.bytes.length !== member.size_bytes) {
      throw new Error(`${label} does not match its Snapshot size.`);
    }
    if (file.digest !== member.sha256) {
      throw new Error(`${label} does not match its Snapshot SHA-256.`);
    }
    return file;
  }

  async function verifiedSchema(snapshot, definition) {
    const file = await verifiedMember(
      snapshot,
      definition.schema_file,
      `${definition.name} schema`,
    );
    return parseJson(file.text, `${definition.name} schema`);
  }

  async function requireChangeSetEligible(snapshot, definition) {
    const schema = await verifiedSchema(snapshot, definition);
    if (schema?.["x-gds-change-set-eligible"] !== true) {
      throw new Error(`${definition.name} is not Change Set eligible.`);
    }
    return schema;
  }

  async function snapshotCandidate(directory) {
    const manifest = await optionalFile(directory, "manifest.json");
    const catalog = await optionalFile(directory, "catalog.json");
    return manifest && catalog ? { directory, manifest, catalog } : null;
  }

  async function locateSnapshot(session, area) {
    const areaDirectory = await optionalDirectory(session, area);
    if (!areaDirectory) return null;
    const directory = await optionalDirectory(areaDirectory, `${area}-snapshot`);
    if (!directory) return null;
    const candidate = await snapshotCandidate(directory);
    if (!candidate) throw new Error(`${area} Snapshot requires manifest.json and catalog.json in ${area}/${area}-snapshot.`);
    const manifestFile = await readFile(candidate.manifest);
    const manifest = parseJson(manifestFile.text, `${area} Snapshot manifest`);
    const members = manifestMembers(manifest, area);
    const snapshot = { root: candidate.directory, manifest, members };
    const catalogFile = await verifiedMember(snapshot, "catalog.json", `${area} Snapshot catalog`);
    const catalog = parseJson(catalogFile.text, `${area} Snapshot catalog`);
    if (manifest.snapshot_kind !== area || catalog.snapshot_kind !== area) {
      throw new Error(`${area} Snapshot kind does not match its session area.`);
    }
    if (!Array.isArray(catalog.sections)) throw new Error(`${area} catalog sections are invalid.`);
    if (area === "model") {
      const model = catalog.model;
      if (
        !model ||
        Array.isArray(model) ||
        typeof model !== "object" ||
        !Number.isSafeInteger(manifest.model_id) ||
        manifest.model_id <= 0 ||
        typeof manifest.model_name !== "string" ||
        !manifest.model_name.trim() ||
        manifest.model_name.length > 255 ||
        !Number.isSafeInteger(manifest.model_revision) ||
        manifest.model_revision < 0 ||
        model.model_id !== manifest.model_id ||
        model.model_name !== manifest.model_name ||
        model.model_revision !== manifest.model_revision
      ) {
        throw new Error("Model identity does not match between Snapshot manifest and catalog.");
      }
    }
    const datasets = [];
    const names = new Set();
    for (const section of catalog.sections) {
      if (!Array.isArray(section.datasets)) throw new Error(`${area} catalog datasets are invalid.`);
      for (const dataset of section.datasets) {
        if (
          !dataset ||
          typeof dataset.name !== "string" ||
          names.has(dataset.name) ||
          !Array.isArray(dataset.canonical_key) ||
          typeof dataset.rows_file !== "string" ||
          typeof dataset.schema_file !== "string"
        ) {
          throw new Error(`${area} catalog contains an invalid or duplicate dataset.`);
        }
        safeSegments(dataset.rows_file);
        safeSegments(dataset.schema_file);
        if (!members.has(dataset.rows_file) || !members.has(dataset.schema_file)) {
          throw new Error(`${area} catalog references a member not authorized by its manifest.`);
        }
        names.add(dataset.name);
        datasets.push({ ...dataset, section: section.name });
      }
    }
    return {
      root: candidate.directory,
      manifestHandle: candidate.manifest,
      manifest,
      manifestDigest: manifestFile.digest,
      members,
      catalog,
      datasets,
      byName: new Map(datasets.map((dataset) => [dataset.name, dataset])),
    };
  }

  async function writeText(handle, text) {
    const writable = await handle.createWritable({ keepExistingData: false });
    try {
      await writable.write(text);
      await writable.close();
    } catch (error) {
      try {
        await writable.abort();
      } catch (_abortError) {
        // Preserve the original write failure.
      }
      throw error;
    }
  }

  function validateSession(state) {
    const object = value => value && typeof value === "object" && !Array.isArray(value);
    const identity = value => object(value) && Number.isSafeInteger(value.id) && value.id > 0 &&
      typeof value.code === "string" && value.code.trim();
    if (!object(state) || state.schema_version !== "1.0" || !identity(state.tenant) ||
        (state.model != null && (!object(state.model) || !Number.isSafeInteger(state.model.id) || state.model.id <= 0 ||
          typeof state.model.name !== "string" || !state.model.name.trim())) ||
        (state.active_task != null && (typeof state.active_task !== "string" || !UUID.test(state.active_task))) ||
        (state.sql !== undefined && (!object(state.sql) || !["never", "essential", "proactive"].includes(state.sql.policy) ||
          (state.sql.environment !== undefined && !["dev", "qa", "stg", "prod"].includes(state.sql.environment))))) {
      throw new Error(".atlas/session.json has an invalid shape. Initialize this directory with Atlas.");
    }
    if (state.metadata_owners !== undefined) {
      if (!object(state.metadata_owners)) throw new Error("Metadata owners must be a map of verified Tenant identities.");
      for (const [key, owner] of Object.entries(state.metadata_owners)) {
        if (!identity(owner) || key !== String(owner.id) || owner.root !== (owner.id === state.tenant.id ? "." : `metadata-owners/tenant-${owner.id}`) ||
            (owner.id === state.tenant.id && core.normalize("metadata", "tenant_code", owner.code) !== core.normalize("metadata", "tenant_code", state.tenant.code))) {
          throw new Error("Metadata owner identity or workspace root is invalid.");
        }
      }
    }
    if (state.refresh_required !== undefined && (!Array.isArray(state.refresh_required) || state.refresh_required.some(item =>
      !object(item) || !["metadata", "model"].includes(item.area) || !Number.isSafeInteger(item.owner_tenant_id) ||
      typeof item.reason !== "string" || !item.reason))) throw new Error("Known Snapshot invalidations have an invalid shape.");
    return state;
  }

  function validateValidationReport(value, area) {
    const validIssue = (issue) =>
      issue &&
      !Array.isArray(issue) &&
      typeof issue === "object" &&
      new Set(["error", "warning"]).has(issue.severity) &&
      typeof issue.dataset === "string" &&
      issue.dataset.length > 0 &&
      (issue.record === null || (Number.isSafeInteger(issue.record) && issue.record > 0)) &&
      typeof issue.code === "string" &&
      issue.code.length > 0 &&
      Array.isArray(issue.fields) &&
      issue.fields.every((field) => typeof field === "string" && field.length > 0) &&
      typeof issue.message === "string" &&
      issue.message.length > 0;
    if (
      !value ||
      Array.isArray(value) ||
      typeof value !== "object" ||
      value.schema_version !== "1.0" ||
      value.area !== area ||
      !new Set(["agent", "workbench"]).has(value.run_by) ||
      typeof value.generated_at !== "string" ||
      !value.generated_at ||
      typeof value.digest !== "string" ||
      !/^[0-9a-f]{64}$/.test(value.digest) ||
      !value.snapshot ||
      Array.isArray(value.snapshot) ||
      typeof value.snapshot !== "object" ||
      typeof value.snapshot.id !== "string" ||
      !value.snapshot.id ||
      (value.snapshot.revision !== null &&
        (!Number.isSafeInteger(value.snapshot.revision) || value.snapshot.revision < 0)) ||
      typeof value.snapshot.manifest_digest !== "string" ||
      !/^[0-9a-f]{64}$/.test(value.snapshot.manifest_digest) ||
      typeof value.valid !== "boolean" ||
      !Number.isSafeInteger(value.issue_count) ||
      value.issue_count < 0 ||
      typeof value.truncated !== "boolean" ||
      !Array.isArray(value.issues) ||
      value.issues.length > 200 ||
      value.issue_count < value.issues.length ||
      value.issues.some((issue) => !validIssue(issue))
    ) {
      throw new Error(`${area} local validation report has an invalid shape.`);
    }
    return value;
  }

  class Workspace {
    constructor(handle) {
      this.handle = handle;
      this.state = null;
      this.sessionDigest = null;
      this.areas = new Map();
      this.areaErrors = new Map();
      this.ownerId = null;
      this.task = null;
    }

    async dataRoot(area, selectedOwner = null) {
      if (area !== "metadata") return this.handle;
      const owner = selectedOwner || this.owner();
      let directory = this.handle;
      if (owner.root !== ".") for (const segment of safeSegments(owner.root)) directory = await directory.getDirectoryHandle(segment);
      return directory;
    }

    owner(area = "metadata") {
      if (area === "model") return { ...this.state.tenant, root: "." };
      return this.state.metadata_owners?.[this.ownerId] || { ...this.state.tenant, root: "." };
    }

    async selectOwner(id) {
      if (String(id) !== String(this.state.tenant.id) && !this.state.metadata_owners?.[id]) throw new Error("Unknown Metadata owner.");
      this.ownerId = String(id);
      return this.refresh();
    }

    async refresh() {
      const atlas = await optionalDirectory(this.handle, ".atlas");
      if (!atlas) throw new Error("This directory is not initialized. Run Atlas initialization or open another working directory.");
      const sessionFile = await readFile(await atlas.getFileHandle("session.json"));
      this.state = validateSession(parseJson(sessionFile.text, ".atlas/session.json"));
      this.sessionDigest = sessionFile.digest;
      if (!this.ownerId || (this.ownerId !== String(this.state.tenant.id) && !this.state.metadata_owners?.[this.ownerId])) this.ownerId = String(this.state.tenant.id);
      this.task = null;
      if (this.state.active_task) {
        const tasks = await optionalDirectory(atlas, "tasks");
        const file = tasks && await optionalFile(tasks, `${this.state.active_task}.json`);
        if (file) {
          const task = parseJson((await readFile(file)).text, "Active task");
          if (task?.schema_version !== "1.0" || typeof task.outcome !== "string" || !task.outcome.trim()) throw new Error("The active task has an invalid shape.");
          this.task = task;
        }
      }
      const nextAreas = new Map(), errors = new Map();
      for (const area of ["metadata", "model"]) {
        try {
          const snapshot = await locateSnapshot(await this.dataRoot(area), area);
          if (snapshot) {
            const owner = this.owner(area);
            const code = snapshot.manifest.tenant_code ?? snapshot.catalog.model?.tenant_code;
            if (typeof code !== "string" || core.normalize("metadata", "tenant_code", code) !== core.normalize("metadata", "tenant_code", owner.code)) throw new Error(`${area} Snapshot Tenant does not match the selected owner.`);
            if (snapshot.manifest.tenant_id !== undefined && snapshot.manifest.tenant_id !== owner.id) throw new Error(`${area} Snapshot Tenant ID does not match the selected owner.`);
            if (area === "model" && (!this.state.model || this.state.model.id !== snapshot.manifest.model_id || this.state.model.name !== snapshot.manifest.model_name)) throw new Error("Model Snapshot identity conflicts with .atlas/session.json. Resolve it through Atlas.");
          }
          nextAreas.set(area, snapshot);
        } catch (error) { nextAreas.set(area, null); errors.set(area, error.message); }
      }
      this.areas = nextAreas;
      this.areaErrors = errors;
      return this;
    }

    isStale(area) {
      return this.state?.refresh_required?.some(item => item.area === area && item.owner_tenant_id === this.owner(area).id) || false;
    }

    async assertSessionUnchanged() {
      const file = await readFile(await fileAt(this.handle, ".atlas/session.json"));
      if (file.digest !== this.sessionDigest) throw new Error("Workspace context changed externally. Reload local files before continuing.");
    }

    inputBinding(area, owner, snapshot, draftDigest) {
      const prefix = area === "metadata" && owner.root !== "." ? `${owner.root}/` : "";
      return { area, owner_tenant_id: owner.id, snapshot_id: snapshot.manifest.snapshot_id,
        manifest_path: `${prefix}${area}/${area}-snapshot/manifest.json`, manifest_sha256: snapshot.manifestDigest,
        ...(area === "model" ? { model_revision: snapshot.manifest.model_revision } : {}),
        ...(draftDigest === undefined ? {} : { draft_digest: draftDigest }) };
    }

    async captureInputs(area) {
      await this.assertSessionUnchanged();
      this.requireFresh(area);
      const snapshot = this.areas.get(area);
      if (!snapshot) throw new Error(this.areaErrors.get(area) || `${area} Snapshot is unavailable.`);
      if ((await readFile(snapshot.manifestHandle)).digest !== snapshot.manifestDigest) throw new Error(`${area} Snapshot changed externally. Reload local files.`);
      const inputs = [this.inputBinding(area, this.owner(area), snapshot, await this.localChangeSetDigest(area))];
      let taskBinding = null;
      if (this.state.active_task) {
        const taskPath = `.atlas/tasks/${this.state.active_task}.json`, taskFile = await readFile(await fileAt(this.handle, taskPath));
        const task = parseJson(taskFile.text, "Active task"), declared = task.inputs?.snapshots || [];
        if (!Array.isArray(declared)) throw new Error("Task Snapshot bindings must be an array.");
        taskBinding = { path: taskPath, snapshot_selection: core.stableStringify(declared) };
        for (const input of declared) {
          if (!input || !["metadata", "model"].includes(input.area)) throw new Error("Invalid task Snapshot binding.");
          const owner = input.area === "model" || input.owner_tenant_id === this.state.tenant.id ? { ...this.state.tenant, root: "." } : this.state.metadata_owners?.[String(input.owner_tenant_id)];
          if (!owner) throw new Error("Task Snapshot owner is not registered.");
          const context = await locateSnapshot(await this.dataRoot(input.area, owner), input.area);
          if (!context) throw new Error("A task-bound Snapshot is missing.");
          const actual = this.inputBinding(input.area, owner, context);
          if (Object.keys(actual).some(field => actual[field] !== input[field])) throw new Error("Task Snapshot input changed; review its selection before validation.");
          if (!inputs.some(existing => existing.manifest_path === actual.manifest_path)) inputs.push(actual);
        }
      }
      const binding = { session_digest: this.sessionDigest, inputs, task_binding: taskBinding };
      await this.assertInputsUnchanged(binding);
      return binding;
    }

    async loadModelMetadata() {
      const owners = new Map([[this.state.tenant.id, { ...this.state.tenant, root: "." }],
        ...Object.values(this.state.metadata_owners || {}).map(owner => [owner.id, owner])]);
      const loaded = new Map(), inputs = [], missing = [];
      for (const owner of owners.values()) {
        if (this.state.refresh_required?.some(item => item.area === "metadata" && item.owner_tenant_id === owner.id)) throw new Error(`Metadata for ${owner.code} needs refresh before Model validation.`);
        let snapshot;
        try { snapshot = await locateSnapshot(await this.dataRoot("metadata", owner), "metadata"); }
        catch (error) { if (error.name !== "NotFoundError") throw error; }
        if (!snapshot) { missing.push(owner.id); continue; }
        if (core.normalize("metadata", "tenant_code", snapshot.manifest.tenant_code) !== core.normalize("metadata", "tenant_code", owner.code)) throw new Error("Metadata Snapshot owner conflicts with the registered Tenant.");
        if (snapshot.manifest.tenant_id !== undefined && snapshot.manifest.tenant_id !== owner.id) throw new Error("Metadata Snapshot Tenant ID conflicts with the registered owner.");
        inputs.push(this.inputBinding("metadata", owner, snapshot));
        for (const definition of snapshot.datasets) {
          const file = await verifiedMember(snapshot, definition.rows_file, `${definition.name} rows`);
          const schema = await verifiedSchema(snapshot, definition);
          const rows = file.text.split(/\r?\n/).filter(line => line.trim()).map((line, index) => parseJson(line, `${definition.name} row ${index + 1}`));
          const previous = loaded.get(definition.name);
          if (previous && core.stableStringify(previous.definition.canonical_key) !== core.stableStringify(definition.canonical_key)) throw new Error("Owner Snapshots use incompatible canonical keys.");
          const merged = new Map((previous?.baseline || []).map(row => [core.stableStringify(core.key("metadata", definition, row)), row]));
          for (const row of rows) {
            const key = core.stableStringify(core.key("metadata", definition, row)), existing = merged.get(key);
            if (existing && core.stableStringify(existing) !== core.stableStringify(row)) throw new Error("Owner Snapshots disagree on a shared record; resolve ownership/version before Model validation.");
            merged.set(key, row);
          }
          const baseline = [...merged.values()];
          loaded.set(definition.name, {definition, schema, baseline, effective: baseline, pending: []});
        }
      }
      return { loaded, inputs, missing };
    }

    async assertInputsUnchanged(binding) {
      await this.assertSessionUnchanged();
      if (binding.session_digest !== this.sessionDigest) throw new Error("Workspace context changed during the operation.");
      if (binding.task_binding) {
        const task = parseJson((await readFile(await fileAt(this.handle, binding.task_binding.path))).text, "Active task");
        if (core.stableStringify(task.inputs?.snapshots || []) !== binding.task_binding.snapshot_selection) throw new Error("Task context changed during the operation; run it again.");
      }
      for (const input of binding.inputs) {
        const owner = input.area === "model" || input.owner_tenant_id === this.state.tenant.id ? { ...this.state.tenant, root: "." } : this.state.metadata_owners?.[String(input.owner_tenant_id)];
        if (!owner || input.area === "model" && input.owner_tenant_id !== this.state.tenant.id) throw new Error("Snapshot input owner is no longer registered.");
        if (this.state.refresh_required?.some(item => item.area === input.area && item.owner_tenant_id === owner.id)) throw new Error("Snapshot input requires refresh.");
        const expectedPath = `${input.area === "metadata" && owner.root !== "." ? `${owner.root}/` : ""}${input.area}/${input.area}-snapshot/manifest.json`;
        if (input.manifest_path !== expectedPath || (await readFile(await fileAt(this.handle, expectedPath))).digest !== input.manifest_sha256 ||
            input.draft_digest !== undefined && (input.area === "metadata" && owner.id !== this.owner().id || await this.localChangeSetDigest(input.area) !== input.draft_digest)) throw new Error("Saved inputs changed during the operation. Reload and run it again.");
      }
    }

    area(name) {
      const value = this.areas.get(name);
      return value || { manifest: null, catalog: null, datasets: [], byName: new Map() };
    }

    requireFresh(area) {
      if (this.isStale(area)) {
        throw new Error(`${area} Snapshot is stale; refresh it before local changes.`);
      }
    }

    async loadDataset(area, datasetName) {
      const snapshot = this.areas.get(area);
      if (!snapshot) throw new Error(`${area} Snapshot is not available.`);
      const definition = snapshot.byName.get(datasetName);
      if (!definition) throw new Error(`Unknown ${area} dataset ${datasetName}.`);
      const rowsFile = await verifiedMember(
        snapshot,
        definition.rows_file,
        `${datasetName} rows`,
      );
      const baseline = rowsFile.text
        .split(/\r?\n/)
        .filter((line) => line.trim())
        .map((line, index) => parseJson(line, `${datasetName} row ${index + 1}`));
      const schema = await verifiedSchema(snapshot, definition);
      const changeSet = await optionalDirectory(await this.dataRoot(area), `${area}-change-set`);
      const pendingHandle = changeSet && await optionalFile(changeSet, `${datasetName}.json`);
      let pending = [];
      let pendingDigest = null;
      if (pendingHandle) {
        const pendingFile = await readFile(pendingHandle);
        pending = parseJson(pendingFile.text, `${datasetName} pending file`);
        if (!Array.isArray(pending)) throw new Error(`${datasetName} pending file must be an array.`);
        pendingDigest = pendingFile.digest;
      }
      let effective = baseline;
      let overlayError = null;
      try {
        effective = core.overlay(area, definition, baseline, pending);
      } catch (error) {
        overlayError = error.message;
      }
      return {
        definition,
        schema,
        baseline,
        pending,
        effective,
        overlayError,
        pendingDigest,
      };
    }

    async saveDataset(area, datasetName, draftText, expectedDigest) {
      this.requireFresh(area);
      await this.inspectChangeSet(area);
      const snapshot = this.areas.get(area);
      const definition = snapshot?.byName.get(datasetName);
      if (!definition) throw new Error(`Unknown ${area} dataset ${datasetName}.`);
      await requireChangeSetEligible(snapshot, definition);
      const records = parseJson(draftText, "Editor draft");
      if (!Array.isArray(records)) throw new Error("Editor draft must be a JSON array.");
      if (!this.task || !this.state.active_task) throw new Error("An active Atlas task is required before editing.");
      const binding = await this.captureInputs(area);
      const changeSet = await (await this.dataRoot(area)).getDirectoryHandle(`${area}-change-set`, { create: true });
      let pendingHandle = await optionalFile(changeSet, `${datasetName}.json`);
      const actualDigest = pendingHandle ? (await readFile(pendingHandle)).digest : null;
      if (actualDigest !== expectedDigest) throw new Error("Local Change Set external-edit conflict; reload before saving. Your unsaved input is preserved.");
      // Protect existing baseline and parent locks even when records are edited through a form.
      const loaded = await this.loadArea(area);
      const value = loaded.get(datasetName);
      const before = new Map(value.baseline.map(record => [core.stableStringify(core.key(area, definition, record)), record]));
      const parentDataset = datasetName.endsWith("_attribute") ? datasetName.replace(/_attribute$/, "_object") : null;
      const parents = parentDataset ? loaded.get(parentDataset) : null;
      for (const record of records) {
        const original = before.get(core.stableStringify(core.key(area, definition, record)));
        const locked = Object.entries(original || {}).some(([field, value]) => (field === "is_locked" || field.endsWith("_is_locked")) && value === true);
        if (locked && (area === "metadata" || core.stableStringify(record) !== core.stableStringify(original))) throw new Error("Locked Snapshot records cannot be changed.");
        if (parents && parents.baseline.some(parent => parent.is_locked && core.stableStringify(core.key(area, parents.definition, parent)) === core.stableStringify(core.key(area, parents.definition, record))) && core.stableStringify(record) !== core.stableStringify(original)) throw new Error("The parent Object is locked; its Attributes cannot be changed.");
      }
      await this.assertInputsUnchanged(binding);
      const text = `${JSON.stringify(records, null, 2)}\n`;
      pendingHandle = pendingHandle || (await changeSet.getFileHandle(`${datasetName}.json`, { create: true }));
      await writeText(pendingHandle, text);
      return { records, pendingDigest: await sha256Bytes(encoder.encode(text)) };
    }

    async inspectChangeSet(area) {
      const directory = await optionalDirectory(await this.dataRoot(area), `${area}-change-set`);
      if (!directory) return [];
      const files = [];
      for await (const entry of directory.values()) {
        if (entry.kind !== "file" || !entry.name.endsWith(".json")) {
          throw new Error("Local Change Set contains an unsupported entry.");
        }
        const datasetName = entry.name.slice(0, -5);
        if (!this.area(area).byName.has(datasetName)) {
          throw new Error(`Unknown ${area} Change Set dataset ${datasetName}.`);
        }
        await requireChangeSetEligible(this.area(area), this.area(area).byName.get(datasetName));
        files.push(entry);
      }
      files.sort((left, right) => left.name.localeCompare(right.name));
      return files;
    }

    async localChangeSetDigest(area) {
      const files = await this.inspectChangeSet(area);
      const parts = [];
      let total = 0;
      for (const entry of files) {
        const file = await readFile(entry);
        const prefix = encoder.encode(`${entry.name}\0${file.bytes.length}\0`);
        parts.push(prefix, file.bytes);
        total += prefix.length + file.bytes.length;
      }
      const combined = new Uint8Array(total);
      let offset = 0;
      for (const part of parts) {
        combined.set(part, offset);
        offset += part.length;
      }
      return sha256Bytes(combined);
    }

    async changeSetDigest(area) {
      this.requireFresh(area);
      return this.localChangeSetDigest(area);
    }

    async validationReportDirectory(create = false) {
      if (!this.state.active_task) {
        if (create) throw new Error("An active Atlas task is required to retain validation evidence.");
        return null;
      }
      let directory = this.handle;
      for (const name of [".atlas", "tasks", `${this.state.active_task}.evidence`]) {
        const next = create ? await directory.getDirectoryHandle(name, { create: true }) : await optionalDirectory(directory, name);
        if (!next) return null;
        directory = next;
      }
      return directory;
    }

    async loadOperation(area) {
      const pointer = area === "metadata" ? this.state.operations?.metadata?.[String(this.owner(area).id)] : this.state.operations?.model;
      if (!pointer) return null;
      safeSegments(pointer);
      if (!/^\.atlas\/tasks\/[A-Za-z0-9_-]+\.evidence\/[A-Za-z0-9_.-]+\.json$/.test(pointer)) throw new Error("Operation evidence must be retained inside its task evidence directory.");
      const file = await readFile(await fileAt(this.handle, pointer));
      if (file.bytes.length > 1024 * 1024) throw new Error("Operation evidence exceeds its local size limit.");
      const value = parseJson(file.text, "Operation evidence");
      if (value.schema_version !== "1.0" || value.area !== area || value.owner?.id !== this.owner(area).id ||
          core.normalize("metadata", "tenant_code", value.owner?.code) !== core.normalize("metadata", "tenant_code", this.owner(area).code)) throw new Error("Operation evidence belongs to another owner or area.");
      const digest = this.areas.get(area) ? await this.localChangeSetDigest(area) : null;
      let historical = value.local_digest !== digest;
      if (!UUID.test(value.id || "") || !UUID.test(value.task_id || "") || pointer !== `.atlas/tasks/${value.task_id}.evidence/${value.id}.json` ||
          value.owner.root !== this.owner(area).root || !/^[0-9a-f]{64}$/.test(value.local_digest || "")) throw new Error("Operation evidence identity/path is invalid.");
      for (const input of value.inputs || []) {
        try { if ((await readFile(await fileAt(this.handle, input.manifest_path))).digest !== input.manifest_sha256) historical = true; }
        catch { historical = true; }
      }
      let status = "Local operation";
      if (value.validation?.outcome === "valid") status = "Locally validated";
      if (value.acknowledgement?.source === "conversation") status = "Reviewed batch";
      if (value.stage?.fingerprintVerified === true) status = "Staged receipt recorded";
      if (value.server_validation?.valid === true) status = "Server validation recorded";
      if (value.server_validation?.valid === false) status = "Server validation failed";
      if (value.apply?.applied === true && value.apply.status === "applied") status = "Applied receipt recorded";
      if (value.stage_attempt?.status === "unknown") status = "Stage outcome unknown · inspect before retrying";
      return { path: pointer, id: value.id, status, historical,
        uncertain: value.stage_attempt?.status === "unknown", revision: value.draft?.revision ?? null };
    }

    async loadValidationReport(area) {
      if (!new Set(["metadata", "model"]).has(area)) {
        throw new Error("Validation report area must be metadata or model.");
      }
      const directory = await this.validationReportDirectory(false);
      if (!directory) return null;
      const handle = await optionalFile(directory, `${area}-${this.owner(area).id}-validation.json`);
      if (!handle) return null;
      const report = validateValidationReport(
        parseJson((await readFile(handle)).text, `${area} local validation report`),
        area,
      );
      const snapshot = this.areas.get(area);
      const currentDigest = await this.localChangeSetDigest(area);
      let otherInputsChanged = false;
      try {
        if (Array.isArray(report.inputs)) await this.assertInputsUnchanged({ session_digest: this.sessionDigest, inputs: report.inputs });
        await this.assertEvidenceUnchanged(report.evidence_files);
      } catch { otherInputsChanged = true; }
      return {
        ...report,
        path: `.atlas/tasks/${this.state.active_task}.evidence/${area}-${this.owner(area).id}-validation.json`,
        stale: otherInputsChanged || report.owner_tenant_id !== this.owner(area).id ||
          this.isStale(area) ||
          !snapshot ||
          report.snapshot.id !== snapshot.manifest.snapshot_id ||
          report.snapshot.manifest_digest !== snapshot.manifestDigest ||
          report.digest !== currentDigest,
      };
    }

    async loadQualityEvidence() {
      const directory = await this.validationReportDirectory(false);
      const decisionsFile = directory && await optionalFile(directory, "modeling-decisions.json");
      const path = `.atlas/tasks/${this.state.active_task}.evidence/modeling-decisions.json`;
      const decisionsRead = decisionsFile ? await readFile(decisionsFile) : null;
      if (decisionsRead?.bytes.length > 1024 * 1024) throw new Error("Modeling decisions exceed the local evidence limit.");
      const decisions = decisionsRead ? parseJson(decisionsRead.text, "Modeling decisions") : null;
      const files = [{ path, sha256: decisionsRead?.digest || null }], noteFiles = new Map();
      const entries = [...(Array.isArray(decisions?.entities) ? decisions.entities : []), ...(Array.isArray(decisions?.relationships) ? decisions.relationships : [])];
      for (const entry of entries) for (const ref of Array.isArray(entry?.evidence) ? entry.evidence : []) {
        if (typeof ref?.note !== "string" || noteFiles.has(ref.note)) continue;
        safeSegments(ref.note);
        if (!ref.note.endsWith(".md") || ref.note.startsWith(".atlas/temp/")) throw new Error("Evidence notes must be retained workspace-relative Markdown files.");
        try {
          const note = await readFile(await fileAt(this.handle, ref.note));
          if (note.bytes.length > 64 * 1024 || !note.text.trim()) throw new Error("Evidence note is empty or exceeds 64 KiB.");
          noteFiles.set(ref.note, { sha256: note.digest }); files.push({ path: ref.note, sha256: note.digest });
        } catch (error) { if (error.name !== "NotFoundError") throw error; files.push({ path: ref.note, sha256: null }); }
      }
      return { decisions, noteFiles, files };
    }

    async assertEvidenceUnchanged(files = []) {
      for (const expected of files) {
        let digest = null;
        try { digest = (await readFile(await fileAt(this.handle, expected.path))).digest; }
        catch (error) { if (error.name !== "NotFoundError") throw error; }
        if (digest !== expected.sha256) throw new Error("Modeling evidence changed during validation. Run it again.");
      }
    }

    async saveValidationReport(area, validation) {
      if (!validation?.binding) throw new Error("Validation requires a captured input binding.");
      await this.assertInputsUnchanged(validation.binding);
      await this.assertEvidenceUnchanged(validation.evidenceFiles);
      const digest = await this.changeSetDigest(area);
      if (!validation || validation.digest !== digest) {
        throw new Error("Local validation report digest does not match the current Change Set.");
      }
      const snapshot = this.areas.get(area);
      if (!snapshot) throw new Error(`${area} Snapshot is not available.`);
      const report = validateValidationReport(
        {
          schema_version: "1.0",
          area,
          owner_tenant_id: this.owner(area).id,
          checks: validation.checks || [],
          evidence_files: validation.evidenceFiles || [],
          inputs: validation.binding?.inputs || [],
          run_by: "workbench",
          generated_at: new Date().toISOString(),
          digest,
          snapshot: {
            id: snapshot.manifest.snapshot_id,
            revision: snapshot.manifest.model_revision ?? null,
            manifest_digest: snapshot.manifestDigest,
          },
          valid: validation.valid,
          issue_count: validation.issueCount,
          truncated: validation.truncated,
          issues: validation.issues,
        },
        area,
      );
      const directory = await this.validationReportDirectory(true);
      await this.assertInputsUnchanged(validation.binding);
      await this.assertEvidenceUnchanged(validation.evidenceFiles);
      const handle = await directory.getFileHandle(`${area}-${this.owner(area).id}-validation.json`, { create: true });
      await writeText(handle, `${JSON.stringify(report, null, 2)}\n`);
      return { ...report, path: `.atlas/tasks/${this.state.active_task}.evidence/${area}-${this.owner(area).id}-validation.json`, stale: false };
    }

    async saveDbmlDocuments(documents, options = {}) {
      this.requireFresh("model");
      if (!options.binding) throw new Error("DBML export requires captured Snapshot and Change Set inputs.");
      await this.assertInputsUnchanged(options.binding);
      if (!Array.isArray(documents) || !documents.length || documents.length > 1002) {
        throw new Error("Generated DBML file inventory is invalid.");
      }
      const names = new Set();
      let totalBytes = 0;
      for (const document of documents) {
        const size = encoder.encode(document?.content || "").length;
        if (
          !document ||
          typeof document !== "object" ||
          typeof document.path !== "string" ||
          !/^[A-Za-z0-9_][A-Za-z0-9_.-]*\.dbml$/.test(document.path) ||
          names.has(document.path.toLowerCase()) ||
          typeof document.content !== "string" ||
          size < 1 ||
          size > 12 * 1024 * 1024
        ) {
          throw new Error("Generated DBML member is invalid.");
        }
        names.add(document.path.toLowerCase());
        totalBytes += size;
      }
      if (totalBytes > 16 * 1024 * 1024) {
        throw new Error("Generated DBML files exceed their aggregate byte limit.");
      }
      const snapshot = this.areas.get("model");
      if (!snapshot?.catalog?.model) throw new Error("Model Snapshot identity is unavailable.");
      const directory = await this.handle.getDirectoryHandle("model-dbml", { create: true });
      const previousHandle = await optionalFile(directory, "manifest.json");
      let previousFiles = [];
      if (previousHandle) {
        const previous = parseJson((await readFile(previousHandle)).text, "Generated DBML manifest");
        if (Array.isArray(previous.files)) {
          previousFiles = previous.files
            .map((item) => item?.path)
            .filter((name) => typeof name === "string" && /^[A-Za-z0-9_][A-Za-z0-9_.-]*\.dbml$/.test(name));
        }
      }
      const originals = new Map();
      const touched = new Set(["manifest.json", ...previousFiles, ...documents.map(document => document.path)]);
      let backup = await this.handle.getDirectoryHandle(".atlas");
      backup = await backup.getDirectoryHandle("temp", { create: true });
      const token = [...cryptoApi.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2, "0")).join("");
      backup = await backup.getDirectoryHandle(`dbml-${token}-previous`, { create: true });
      for (const name of touched) {
        const existing = await optionalFile(directory, name);
        if (existing) {
          const file = await readFile(existing);
          originals.set(name, file.text);
          await writeText(await backup.getFileHandle(name, { create: true }), file.text);
        }
      }
      await this.assertInputsUnchanged(options.binding);
      try {
      const files = [];
      for (const document of documents) {
        const bytes = encoder.encode(document.content);
        await writeText(
          await directory.getFileHandle(document.path, { create: true }),
          document.content,
        );
        files.push({
          path: document.path,
          layer: document.layer,
          view: document.view,
          submodel_name: document.submodel_name,
          table_count: document.table_count,
          relationship_count: document.relationship_count,
          size_bytes: bytes.length,
          sha256: await sha256Bytes(bytes),
        });
      }
      const currentNames = new Set(files.map((item) => item.path));
      for (const name of previousFiles) {
        if (!currentNames.has(name)) await directory.removeEntry(name);
      }
      await this.assertInputsUnchanged(options.binding);
      const manifest = {
        schema_version: "1.0",
        snapshot_kind: "dbml",
        source: "local_effective_model",
        generated_by: "workbench",
        model: {
          id: snapshot.catalog.model.model_id,
          name: snapshot.catalog.model.model_name,
          revision: snapshot.catalog.model.model_revision,
        },
        draft_digest: options.binding.inputs.find(item => item.area === "model").draft_digest,
        inputs: options.binding.inputs,
        model_type: options.modelType || "full",
        include_submodels: options.includeSubmodels !== false,
        files,
      };
      await writeText(
        await directory.getFileHandle("manifest.json", { create: true }),
        `${JSON.stringify(manifest, null, 2)}\n`,
      );
      await this.assertInputsUnchanged(options.binding);
      return {
        directory: "model-dbml",
        manifest: "model-dbml/manifest.json",
        file_count: files.length,
        draft_digest: manifest.draft_digest,
        files: files.map((item) => item.path),
      };
      } catch (error) {
        try {
          for (const name of touched) {
            if (originals.has(name)) await writeText(await directory.getFileHandle(name, { create: true }), originals.get(name));
            else if (await optionalFile(directory, name)) await directory.removeEntry(name);
          }
        } catch {
          throw new Error(`DBML export failed; retained previous files are in .atlas/temp/dbml-${token}-previous. Restore them before using the export.`);
        }
        throw error;
      }

    }

    async loadArea(area) {
      await this.inspectChangeSet(area);
      const loaded = new Map();
      for (const definition of this.area(area).datasets) {
        loaded.set(definition.name, await this.loadDataset(area, definition.name));
      }
      return loaded;
    }
  }

  async function connect(handle) {
    if (!handle || handle.kind !== "directory") throw new Error("Select an Atlas working directory containing .atlas.");
    return new Workspace(handle).refresh();
  }

  return { Workspace, connect, safeSegments, sha256Bytes, validateSession };
});
