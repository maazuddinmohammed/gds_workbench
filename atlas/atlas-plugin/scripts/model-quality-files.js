"use strict";

// Local evidence binding is separate from the server's byte-exact Change Set digest.
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const modelingDatasets = new Set([
  "conceptual_object", "conceptual_relationship", "logical_entity", "logical_attribute",
  "logical_relationship", "analysis_result", "modeling_assertion_document", "modeling_assertion_record",
]);
const hash = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");

function readEvidenceFile(session, relative, limit = 1024 * 1024) {
  if (typeof relative !== "string" || !relative || relative.includes("\\") ||
      path.isAbsolute(relative) || relative.split("/").some((part) => !part || part === "." || part === "..")) {
    throw Error("Modeling evidence path must be relative to the session.");
  }
  let current = session;
  const parts = relative.split("/");
  for (let index = 0; index < parts.length; index++) {
    current = path.join(current, parts[index]);
    const stat = fs.lstatSync(current);
    if (stat.isSymbolicLink() || (index < parts.length - 1 ? !stat.isDirectory() : !stat.isFile())) {
      throw Error("Modeling evidence must use regular session files.");
    }
    if (index === parts.length - 1 && stat.size > limit) throw Error("Modeling evidence exceeds its byte limit.");
  }
  const bytes = fs.readFileSync(current);
  if (bytes.length > limit) throw Error("Modeling evidence exceeds its byte limit.");
  return {path: relative, sha256: hash(bytes), bytes};
}

function readDecisions(session, task) {
  const relative = `.atlas/tasks/${task}.evidence/modeling-decisions.json`;
  let file;
  try { file = readEvidenceFile(session, relative); }
  catch (error) {
    if (error.code === "ENOENT") return {decisions: null, files: [{path: relative, sha256: null}], noteFiles: {}};
    throw error;
  }
  let decisions;
  try { decisions = JSON.parse(file.bytes.toString("utf8")); }
  catch { throw Error("Modeling decisions must be valid JSON."); }
  const files = [{path: relative, sha256: file.sha256}];
  const noteFiles = {};
  // The evaluator validates record shapes. Only discover explicit note references here.
  const entries = [
    ...(Array.isArray(decisions?.entities) ? decisions.entities : []),
    ...(Array.isArray(decisions?.relationships) ? decisions.relationships : []),
  ];
  for (const entry of entries) {
    for (const reference of Array.isArray(entry?.evidence) ? entry.evidence : []) {
      if (typeof reference?.note !== "string" || Object.hasOwn(noteFiles, reference.note)) continue;
      if (!reference.note.endsWith(".md") || reference.note.startsWith(".atlas/temp/")) {
        throw Error("Decision notes must be durable workspace Markdown files.");
      }
      try {
        const note = readEvidenceFile(session, reference.note, 64 * 1024);
        if (!note.bytes.toString("utf8").trim()) throw Error("Decision evidence note is empty.");
        noteFiles[reference.note] = {sha256: note.sha256};
        files.push({path: note.path, sha256: note.sha256});
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
        // A missing reference is an actionable diagnostic, not a crash or a fabricated note.
        files.push({path: reference.note, sha256: null});
      }
    }
  }
  return {decisions, files, noteFiles};
}

module.exports = {modelingDatasets, readEvidenceFile, readDecisions, hash};
