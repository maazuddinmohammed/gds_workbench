(function (root, factory) {
  "use strict";
  const node = typeof module === "object" && module.exports;
  const api = factory(node ? require("../metadata.js") : root.GDSMetadata,
    node ? require("../model.js") : root.GDSModel,
    node ? require("../model-quality.js") : root.GDSModelQuality,
    node ? require("./model-policy.js") : root.AtlasModelPolicy,
    node ? require("./sql.js") : root.AtlasSql);
  if (node) module.exports = api;
  root.AtlasValidation = api;
})(globalThis, function (metadata, model, modelQuality, modelPolicy, sql) {
  "use strict";

  // The browser and CLI use this same assembly. Validators remain pure and never read files.
  function run(area, loaded, metadataLoaded = null, options = {}) {
    if (!["metadata", "model"].includes(area) || !(loaded instanceof Map)) throw new Error("Validation needs a Metadata or Model dataset map.");
    const raw = (area === "metadata" ? metadata : model).validate(loaded, metadataLoaded, options);
    for (const owner of options.missingMetadataOwners || []) raw.push({code: "metadata_owner_snapshot_missing", dataset: "model", severity: [...loaded].some(([name,value]) => name !== "model_details" && value.pending?.length) ? "error" : "warning",
      message: `Applied Metadata for owner ${owner} is unavailable; physical context completeness needs review.`});
    const checks = [
      { id: "local.schema", status: "ran" }, { id: "local.identity", status: "ran" },
      { id: "local.state", status: "ran" }, { id: "local.scope", status: "ran" },
      { id: "local.references", status: "ran" },
    ];
    // Structural failures are already actionable; avoid interpreting malformed records as policy evidence.
    if (area === "model" && !raw.some(issue => ["schema", "canonical_key", "effective_overlay"].includes(issue.code))) {
      raw.push(...modelPolicy.validate(loaded, metadataLoaded, options), ...sql.validateCodeRecords(loaded));
      checks.push({ id: "model.authoring-policy", status: "ran" });
    } else if (area === "model") checks.push({ id: "model.authoring-policy", status: "not_run", reason: "Repair structural errors first." });
    let quality = null;
    if (area === "model" && options.includeQuality !== false) {
      quality = modelQuality.evaluateQuality(loaded, options.decisions ?? null, {
        noteFiles: options.noteFiles || new Map(), metadataMap: metadataLoaded,
      });
      raw.push(...quality.errors.map(issue => ({ ...issue, severity: "error" })),
        ...quality.warnings.map(issue => ({ ...issue, severity: "warning" })));
      checks.push({ id: "local.evidence", status: quality.required ? "ran" : "not_required" });
    } else checks.push({ id: "local.evidence", status: "not_run", reason: area === "metadata" ? "Modeling evidence is not applicable." : "Structural DBML checks only." });
    checks.push({ id: "local.meaning", status: "review_required", reason: "Business meaning requires agent and user review." },
      { id: "server.authorization", status: "server_only" }, { id: "server.validation", status: "server_only" });
    const issues = raw.slice(0, 200).map(issue => ({
      severity: issue.severity || "error", dataset: issue.dataset || area,
      record: issue.record ?? null, code: issue.code || "validation",
      fields: issue.fields || (issue.field ? [issue.field] : []),
      message: String(issue.message || issue.target || issue.endpoint || issue.field || issue.code || "Validation failed."),
    }));
    return { valid: !raw.some(issue => (issue.severity || "error") === "error"),
      issues, issueCount: raw.length, truncated: raw.length > issues.length, checks, quality };
  }
  return { run };
});
