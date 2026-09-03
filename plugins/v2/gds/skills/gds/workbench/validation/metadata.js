(function (root, factory) {
  "use strict";
  let core = root.GDSCore;
  if (typeof module === "object" && module.exports) core = require("../core.js");
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSMetadataValidation = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  function validateReferences(datasets) {
    const byType = new Map();
    for (const value of datasets.values()) {
      const type = value.definition.record_type || value.definition.name;
      if (!byType.has(type)) byType.set(type, []);
      byType.get(type).push(...value.records);
    }
    const issues = [];
    for (const value of datasets.values()) {
      const references = Array.isArray(value.schema["x-gds-references"])
        ? value.schema["x-gds-references"]
        : [];
      value.records.forEach((record, recordIndex) => {
        for (const reference of references) {
          const target = byType.get(reference.target_record_type);
          if (!target) {
            issues.push({
              code: "invalid_reference_contract",
              dataset: value.definition.name,
              record: recordIndex + 1,
            });
            continue;
          }
          const values = reference.columns.map((field) => record[field]);
          const nulls = values.filter((item) => item === null || item === undefined).length;
          if (nulls > 0 && reference.nullable === true) continue;
          if (nulls > 0) {
            issues.push({
              code: "partial_null_reference",
              dataset: value.definition.name,
              record: recordIndex + 1,
            });
            continue;
          }
          const wanted = core.stableStringify(
            values.map((item, index) =>
              core.normalize("metadata", reference.target_columns[index], item),
            ),
          );
          const found = target.some(
            (candidate) =>
              core.stableStringify(
                reference.target_columns.map((field) =>
                  core.normalize("metadata", field, candidate[field]),
                ),
              ) === wanted,
          );
          if (!found) {
            issues.push({
              code: "broken_reference",
              dataset: value.definition.name,
              record: recordIndex + 1,
              target: reference.target_record_type,
            });
          }
        }
      });
    }
    return issues;
  }

  const OBJECT_KEY = [
    "tenant_code", "system_code", "connection_code", "object_schema", "object_name",
  ];

  function key(fields, record) {
    return core.stableStringify(
      fields.map((field) => core.normalize("metadata", field, record?.[field])),
    );
  }

  function recordsByType(datasets, source) {
    const records = new Map();
    for (const value of datasets.values()) {
      const type = value.definition.record_type || value.definition.name;
      if (!records.has(type)) records.set(type, []);
      records.get(type).push(...(value[source] || []));
    }
    return records;
  }

  function validateLocks(datasets) {
    const baseline = recordsByType(datasets, "baseline");
    const locked = new Set(
      (baseline.get("object") || [])
        .filter((record) => record.is_locked === true)
        .map((record) => key(OBJECT_KEY, record)),
    );
    const issues = [];
    for (const [dataset, value] of datasets) {
      const type = value.definition.record_type || value.definition.name;
      if (!["object", "attribute"].includes(type)) continue;
      (value.pending || []).forEach((record, index) => {
        if (!locked.has(key(OBJECT_KEY, record))) return;
        issues.push({
          code: "object_locked",
          dataset,
          record: index + 1,
          field: "object_name",
          message: "Object is locked; neither it nor its Attributes can be changed.",
        });
      });
    }
    return issues;
  }

  function validateTenantScope(datasets, tenantCode) {
    const objectContract = [...datasets.values()].find((value) => {
      const type = value.definition.record_type || value.definition.name;
      return type === "object" &&
        value.schema?.properties?.source_tenant_code &&
        value.schema?.properties?.zone_code;
    });
    if (!objectContract) return [];
    if (typeof tenantCode !== "string" || !tenantCode) {
      return [{
        code: "validation_context_missing",
        dataset: "metadata",
        message: "Metadata Snapshot does not identify its Tenant.",
      }];
    }
    const tenant = core.normalize("metadata", "tenant_code", tenantCode);
    const dataset = (name) => datasets.get(name) || { baseline: [], pending: [], effective: [] };
    const ownedConnections = new Set(
      (dataset("connection").baseline || [])
        .filter((record) => core.normalize("metadata", "tenant_code", record.tenant_code) === tenant)
        .map((record) => key(["tenant_code", "system_code", "connection_code"], record)),
    );
    const gdsConnections = new Set(
      (dataset("tenant").baseline || [])
        .filter((record) =>
          core.normalize("metadata", "tenant_code", record.tenant_code) === tenant &&
          record.gds_connection_tenant_code !== null &&
          record.gds_connection_system_code !== null &&
          record.gds_connection_code !== null,
        )
        .map((record) => key(
          ["tenant_code", "system_code", "connection_code"],
          {
            tenant_code: record.gds_connection_tenant_code,
            system_code: record.gds_connection_system_code,
            connection_code: record.gds_connection_code,
          },
        )),
    );
    const objects = new Map();
    for (const value of datasets.values()) {
      const type = value.definition.record_type || value.definition.name;
      if (type !== "object") continue;
      for (const record of value.effective || []) objects.set(key(OBJECT_KEY, record), record);
    }
    const ownerDatasets = new Set([
      "copy_group", "member_group", "copy_group_control", "copy", "process_group", "process",
    ]);
    const referencedObjects = (name, type, record) => {
      if (type === "object") return [[record, "object_name"]];
      if (type === "attribute") {
        const target = objects.get(key(OBJECT_KEY, record));
        return target ? [[target, "object_name"]] : [];
      }
      if (["ingestion_object_mapping", "ingestion_attribute_mapping", "copy"].includes(name)) {
        return ["source", "target"].flatMap((prefix) => {
          const fields = OBJECT_KEY.map((field) => `${prefix}_${field}`);
          const target = objects.get(key(OBJECT_KEY, Object.fromEntries(
            OBJECT_KEY.map((field, index) => [field, record[fields[index]]]),
          )));
          return target ? [[target, `${prefix}_object_name`]] : [];
        });
      }
      if (name === "process") {
        const target = objects.get(key(OBJECT_KEY, {
          tenant_code: record.object_tenant_code,
          system_code: record.object_system_code,
          connection_code: record.object_connection_code,
          object_schema: record.object_schema,
          object_name: record.object_name,
        }));
        return target ? [[target, "object_name"]] : [];
      }
      return [];
    };
    const mutable = (record) => {
      if (core.normalize("metadata", "source_tenant_code", record.source_tenant_code) !== tenant) {
        return false;
      }
      const connection = key(["tenant_code", "system_code", "connection_code"], record);
      const zone = core.normalize("metadata", "zone_code", record.zone_code);
      return zone === "source"
        ? ownedConnections.has(connection)
        : ["bronze", "silver", "gold"].includes(zone) && gdsConnections.has(connection);
    };
    const issues = [];
    for (const [name, value] of datasets) {
      const type = value.definition.record_type || value.definition.name;
      (value.pending || []).forEach((record, index) => {
        if (
          ownerDatasets.has(name) &&
          core.normalize("metadata", "tenant_code", record.tenant_code) !== tenant
        ) {
          issues.push({
            code: "tenant_scope_mismatch", dataset: name, record: index + 1,
            field: "tenant_code", message: "Record is not owned by the locked Tenant.",
          });
          return;
        }
        const invalid = referencedObjects(name, type, record).find(([target]) => !mutable(target));
        if (invalid) issues.push({
          code: "tenant_scope_mismatch", dataset: name, record: index + 1,
          field: invalid[1], message: "Referenced Object is not owned by the locked Tenant.",
        });
      });
    }
    return issues;
  }

  function validateUniqueConstraints(datasets) {
    const groups = new Map();
    for (const value of datasets.values()) {
      const type = value.definition.record_type || value.definition.name;
      if (!groups.has(type)) groups.set(type, []);
      groups.get(type).push(value);
    }
    const issues = [];
    for (const values of groups.values()) {
      const constraints = new Map();
      for (const value of values) {
        for (const constraint of Array.isArray(value.schema["x-gds-unique-constraints"])
          ? value.schema["x-gds-unique-constraints"]
          : []) {
          if (Array.isArray(constraint) && constraint.every((field) => typeof field === "string")) {
            constraints.set(core.stableStringify(constraint), constraint);
          }
        }
      }
      for (const constraint of constraints.values()) {
        const seen = new Set();
        for (const value of values) {
          value.records.forEach((record, index) => {
            const constraintKey = core.stableStringify(
              constraint.map((field) => core.normalize("metadata", field, record[field])),
            );
            if (seen.has(constraintKey)) {
              issues.push({
                code: "duplicate_unique_constraint",
                dataset: value.definition.name,
                record: index + 1,
                message: `Effective zone datasets duplicate (${constraint.join(", ")}).`,
              });
            } else seen.add(constraintKey);
          });
        }
      }
    }
    return issues;
  }

  return { validateLocks, validateReferences, validateTenantScope, validateUniqueConstraints };
});
