(function (root, factory) {
  "use strict";
  let unicode = root.GDSUnicode;
  if (typeof module === "object" && module.exports) unicode = require("./unicode.js");
  const api = factory(unicode);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSCore = api;
})(typeof globalThis === "object" ? globalThis : this, function (unicode) {
  "use strict";

  function stableStringify(value) {
    if (value === null || typeof value !== "object") return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }

  function normalize(area, field, value) {
    if (typeof value !== "string") return value;
    const trimmed = value.replace(/^ +| +$/g, "");
    if (area === "model") {
      return unicode?.casefold ? unicode.casefold(trimmed) : trimmed.toLowerCase();
    }
    if (/(_code|_name|_schema)$/.test(field)) {
      return unicode?.lower ? unicode.lower(trimmed) : trimmed.toLowerCase();
    }
    return value;
  }

  function key(area, definition, record) {
    if (!Array.isArray(definition.canonical_key)) {
      throw new Error(`${definition.name} canonical key is invalid.`);
    }
    return definition.canonical_key.map((field) => {
      if (!Object.prototype.hasOwnProperty.call(record, field)) {
        throw new Error(`${definition.name}.${field} is required.`);
      }
      return normalize(area, field, record[field]);
    });
  }

  function overlay(area, definition, baseline, pending) {
    const records = new Map(
      baseline.map((record) => [stableStringify(key(area, definition, record)), record]),
    );
    for (const record of pending) {
      records.set(stableStringify(key(area, definition, record)), record);
    }
    return [...records.values()].sort((left, right) => {
      const leftKey = stableStringify(key(area, definition, left));
      const rightKey = stableStringify(key(area, definition, right));
      return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
    });
  }

  function active(record) {
    if (typeof record.is_active === "boolean") return record.is_active;
    if (typeof record.status === "string") return record.status === "active";
    const statusField = Object.keys(record).find((field) => field.endsWith("_status"));
    if (statusField && typeof record[statusField] === "string") {
      return record[statusField] === "active";
    }
    return null;
  }

  function reviewActions(area, definition, baseline, pending) {
    const originals = new Map(
      baseline.map((record) => [stableStringify(key(area, definition, record)), record]),
    );
    return pending.map((record) => {
      const naturalKey = key(area, definition, record);
      const original = originals.get(stableStringify(naturalKey));
      let action = "added";
      if (original) {
        if (stableStringify(original) === stableStringify(record)) action = "unchanged";
        else if (active(original) === true && active(record) === false) action = "deactivated";
        else if (active(original) === false && active(record) === true) action = "reactivated";
        else action = "changed";
      }
      return {
        action,
        key: Object.fromEntries(
          definition.canonical_key.map((field, index) => [field, naturalKey[index]]),
        ),
        record,
      };
    });
  }

  return { active, key, normalize, overlay, reviewActions, stableStringify };
});
