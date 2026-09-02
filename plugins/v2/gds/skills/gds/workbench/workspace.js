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
      relativePath.includes("\\") ||
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
    const areaDirectory = await session.getDirectoryHandle(area);
    const candidates = [];
    const direct = await snapshotCandidate(areaDirectory);
    if (direct) candidates.push(direct);
    for await (const entry of areaDirectory.values()) {
      if (entry.kind !== "directory") continue;
      const candidate = await snapshotCandidate(entry);
      if (candidate) candidates.push(candidate);
    }
    if (candidates.length === 0) return null;
    if (candidates.length !== 1) {
      throw new Error(`Expected exactly one unzipped ${area} Snapshot.`);
    }
    const candidate = candidates[0];
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
    const invalidModel =
      state?.model !== undefined &&
      (!Array.isArray(state.model) ||
        state.model.length !== 2 ||
        !Number.isSafeInteger(state.model[0]) ||
        state.model[0] <= 0 ||
        typeof state.model[1] !== "string" ||
        !state.model[1].trim() ||
        state.model[1].length > 255);
    const invalidSqlPolicy =
      state?.sql !== undefined &&
      !new Set(["never", "essential", "as_needed"]).has(state.sql);
    if (
      !state ||
      typeof state !== "object" ||
      !Array.isArray(state.tasks) ||
      (state.current !== null && typeof state.current !== "string") ||
      invalidModel ||
      invalidSqlPolicy ||
      state.tasks.some(
        (task) =>
          !Array.isArray(task) ||
          task.length !== 4 ||
          task.some((value) => typeof value !== "string"),
      )
    ) {
      throw new Error("session.json has an invalid shape.");
    }
    return state;
  }

  class Workspace {
    constructor(handle) {
      this.handle = handle;
      this.state = null;
      this.sessionDigest = null;
      this.areas = new Map();
    }

    async refresh() {
      const sessionHandle = await this.handle.getFileHandle("session.json");
      const sessionFile = await readFile(sessionHandle);
      const nextState = validateSession(parseJson(sessionFile.text, "session.json"));
      const nextAreas = new Map();
      for (const area of ["metadata", "model"]) {
        const snapshot = await locateSnapshot(this.handle, area);
        nextAreas.set(area, snapshot);
      }
      const modelSnapshot = nextAreas.get("model");
      let nextSessionDigest = sessionFile.digest;
      if (modelSnapshot) {
        const model = [
          modelSnapshot.manifest.model_id,
          modelSnapshot.manifest.model_name,
        ];
        if (nextState.model && nextState.model[0] !== model[0]) {
          throw new Error(
            `Session is bound to Model ${nextState.model[0]}; start a new session for Model ${model[0]}.`,
          );
        }
        if (!nextState.model || nextState.model[1] !== model[1]) {
          nextState.model = model;
          const nextSessionText = `${JSON.stringify(nextState)}\n`;
          await writeText(sessionHandle, nextSessionText);
          nextSessionDigest = await sha256Bytes(encoder.encode(nextSessionText));
        }
      }
      this.state = nextState;
      this.sessionDigest = nextSessionDigest;
      this.areas = nextAreas;
      return this;
    }

    area(name) {
      const value = this.areas.get(name);
      return value || { manifest: null, catalog: null, datasets: [], byName: new Map() };
    }

    requireFresh(area) {
      if (this.state?.stale?.includes(area)) {
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
      const changeSet = await this.handle.getDirectoryHandle(`${area}-change-set`);
      const pendingHandle = await optionalFile(changeSet, `${datasetName}.json`);
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
      const task = this.state.tasks.find((item) => item[0] === this.state.current);
      if (!task || task[1] !== area) throw new Error(`A current ${area} task is required.`);
      if (!new Set(["doing", "review", "ready", "overridden", "staged"]).has(task[3])) {
        throw new Error(`Task state ${task[3]} does not permit local editing.`);
      }

      const changeSet = await this.handle.getDirectoryHandle(`${area}-change-set`);
      let pendingHandle = await optionalFile(changeSet, `${datasetName}.json`);
      let actualDigest = null;
      if (pendingHandle) actualDigest = (await readFile(pendingHandle)).digest;
      if (actualDigest !== expectedDigest) {
        throw new Error("Local Change Set external-edit conflict; Refresh before saving.");
      }
      const currentSession = await readFile(await this.handle.getFileHandle("session.json"));
      if (currentSession.digest !== this.sessionDigest) {
        throw new Error("session.json external-edit conflict; Refresh before saving.");
      }

      const text = `${JSON.stringify(records, null, 2)}\n`;
      pendingHandle = pendingHandle || (await changeSet.getFileHandle(`${datasetName}.json`, { create: true }));
      await writeText(pendingHandle, text);
      task[3] = "review";
      const nextSessionText = `${JSON.stringify(this.state)}\n`;
      await writeText(await this.handle.getFileHandle("session.json"), nextSessionText);
      this.sessionDigest = await sha256Bytes(encoder.encode(nextSessionText));
      return { records, pendingDigest: await sha256Bytes(encoder.encode(text)) };
    }

    async inspectChangeSet(area) {
      const directory = await this.handle.getDirectoryHandle(`${area}-change-set`);
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

    async changeSetDigest(area) {
      this.requireFresh(area);
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
    if (!handle || handle.kind !== "directory") throw new Error("Select one GDS session directory.");
    return new Workspace(handle).refresh();
  }

  return { Workspace, connect, safeSegments, sha256Bytes };
});
