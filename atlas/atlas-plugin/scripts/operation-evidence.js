"use strict";

// Decode transport once; never repair transcripts or persist raw tool envelopes.
const fs = require("node:fs");
const {stableStringify} = require("../workbench/core.js");
const {object, uuid} = require("./workspace-state.js");

function readResponse(file) {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 16 * 1024 * 1024) throw Error("Response must be a bounded regular JSON file.");
  let value;
  try { value = JSON.parse(fs.readFileSync(file, "utf8")); }
  catch { throw Error("Response file must contain exactly one JSON document, without prose or concatenated results."); }
  if (!object(value) || value.isError === true) throw Error("Expected a successful structured tool response.");
  const structured = value.structuredContent;
  if (structured !== undefined || Array.isArray(value.content)) {
    let text;
    if (value.content !== undefined) {
      if (!Array.isArray(value.content) || value.content.length !== 1 || value.content[0]?.type !== "text" || typeof value.content[0].text !== "string") throw Error("Tool response requires one JSON text block.");
      try { text = JSON.parse(value.content[0].text); }
      catch { throw Error("Tool response text must contain exactly one JSON document."); }
    }
    if (structured !== undefined && text !== undefined && stableStringify(structured) !== stableStringify(text)) throw Error("Tool response payloads conflict.");
    value = structured ?? text;
  }
  if (!object(value) || value.isError === true) throw Error("Expected a successful JSON response object.");
  return value;
}

function alias(value, canonical, alternatives) {
  const values = [canonical, ...alternatives].filter((name) => Object.hasOwn(value, name)).map((name) => value[name]);
  if (values.some((item) => stableStringify(item) !== stableStringify(values[0]))) throw Error(`Conflicting ${canonical} fields.`);
  return values[0];
}

function serverResponse(value, area, owner, modelId) {
  const other = area === "metadata" ? "model_change_set_id" : "metadata_change_set_id";
  const id = alias(value, "change_set_id", [`${area}_change_set_id`]);
  const ownerId = area === "metadata" ? alias(value, "tenant_id", ["owner_tenant_id"]) : value.model_id;
  if (value.schema_version !== "1.0" || value[other] !== undefined || (value.area !== undefined && value.area !== area) ||
      (value.owner_tenant_id !== undefined && value.owner_tenant_id !== owner.id) ||
      ownerId !== (area === "metadata" ? owner.id : modelId) || typeof id !== "string" || !uuid.test(id) ||
      !Number.isSafeInteger(value.draft_revision) || value.draft_revision < 0) throw Error("Server response does not match the owner, Model or Change Set contract.");
  return {...value, change_set_id: id, ...(area === "metadata" ? {tenant_id: ownerId} : {})};
}

function stageReceipt(value) {
  if (!object(value)) return value;
  const result = {...value};
  for (const [canonical, old] of Object.entries({schema_version:"schemaVersion", task_id:"taskId", operation_id:"operationId",
    owner_tenant_id:"ownerTenantId", owner_root:"ownerRoot", change_set_id:"changeSetId", starting_revision:"startingRevision",
    draft_revision:"resultingRevision", accepted_digest:"acceptedDigest", stage_fingerprint:"stageFingerprint", fingerprint_verified:"fingerprintVerified"})) {
    const normalized = alias(value, canonical, [old]);
    if (normalized !== undefined) result[canonical] = normalized;
    delete result[old];
  }
  if (result.datasets !== undefined) {
    if (!Array.isArray(result.datasets) || result.datasets.some((row) => !object(row))) throw Error("Invalid Stage dataset receipt.");
    result.datasets = result.datasets.map((row) => {
      const count = alias(row, "record_count", ["recordCount"]);
      if (!Number.isSafeInteger(count) || count < 0) throw Error("Invalid Stage dataset count.");
      return {dataset: row.dataset, record_count: count};
    });
  }
  return result;
}

module.exports = {readResponse, serverResponse, stageReceipt};
