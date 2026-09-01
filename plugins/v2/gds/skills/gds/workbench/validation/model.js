(function (root, factory) {
  "use strict";

  let core = root.GDSCore;
  if (typeof module === "object" && module.exports) core = require("../core.js");
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSModelValidation = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  const ANALYSIS_VALIDATION_FIELDS = [
    "validation_policy_version",
    "validation_result",
    "validation_source_non_null_count",
    "validation_source_distinct_count",
    "validation_target_non_null_count",
    "validation_target_distinct_count",
    "validation_source_missing_target_count",
    "validation_unused_target_count",
    "validation_duplicate_target_key_count",
  ];

  function records(datasets, name) {
    return datasets.get(name)?.records || [];
  }

  function changedRecords(datasets, name) {
    const value = datasets.get(name);
    return Array.isArray(value?.pending) ? value.pending : records(datasets, name);
  }

  function baselineRecords(datasets, name) {
    const value = datasets.get(name);
    if (Array.isArray(value?.baseline)) return value.baseline;
    return Array.isArray(value?.pending) && value.pending.length > 0 ? [] : records(datasets, name);
  }

  function normalized(value) {
    return core.normalize("model", "value", value);
  }

  function utf8Bytes(value) {
    return new TextEncoder().encode(value);
  }

  function sha256Text(value) {
    const constants = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
      0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
      0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
      0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
      0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
      0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
      0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
      0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
      0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ];
    const bytes = utf8Bytes(value);
    const padded = new Uint8Array(Math.ceil((bytes.length + 9) / 64) * 64);
    padded.set(bytes);
    padded[bytes.length] = 0x80;
    const view = new DataView(padded.buffer);
    const bits = bytes.length * 8;
    view.setUint32(padded.length - 8, Math.floor(bits / 0x100000000));
    view.setUint32(padded.length - 4, bits >>> 0);
    const hash = [
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];
    const rotate = (word, count) => (word >>> count) | (word << (32 - count));
    for (let offset = 0; offset < padded.length; offset += 64) {
      const words = new Uint32Array(64);
      for (let index = 0; index < 16; index += 1) {
        words[index] = view.getUint32(offset + index * 4);
      }
      for (let index = 16; index < 64; index += 1) {
        const low = rotate(words[index - 15], 7) ^ rotate(words[index - 15], 18) ^
          (words[index - 15] >>> 3);
        const high = rotate(words[index - 2], 17) ^ rotate(words[index - 2], 19) ^
          (words[index - 2] >>> 10);
        words[index] = (words[index - 16] + low + words[index - 7] + high) >>> 0;
      }
      let [a, b, c, d, e, f, g, h] = hash;
      for (let index = 0; index < 64; index += 1) {
        const sigma1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25);
        const choose = (e & f) ^ (~e & g);
        const first = (h + sigma1 + choose + constants[index] + words[index]) >>> 0;
        const sigma0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22);
        const majority = (a & b) ^ (a & c) ^ (b & c);
        const second = (sigma0 + majority) >>> 0;
        [a, b, c, d, e, f, g, h] = [
          (first + second) >>> 0, a, b, c, (d + first) >>> 0, e, f, g,
        ];
      }
      [a, b, c, d, e, f, g, h].forEach((word, index) => {
        hash[index] = (hash[index] + word) >>> 0;
      });
    }
    return hash.map((word) => word.toString(16).padStart(8, "0")).join("");
  }

  function names(datasets, dataset, field) {
    return new Set(records(datasets, dataset).map((record) => normalized(record[field])));
  }

  function pair(entity, attribute) {
    return core.stableStringify([normalized(entity), normalized(attribute)]);
  }

  function physicalObject(record) {
    return core.stableStringify(
      ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"].map(
        (field) => normalized(record?.[field]),
      ),
    );
  }

  function physicalAttribute(record) {
    return core.stableStringify(
      [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
        "attribute_name",
      ].map((field) => normalized(record?.[field])),
    );
  }

  function prefixedPhysicalObject(record, prefix) {
    return physicalObject(
      Object.fromEntries(
        ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"].map(
          (field) => [field, record?.[`${prefix}_${field}`]],
        ),
      ),
    );
  }

  function prefixedPhysicalAttribute(record, prefix) {
    return physicalAttribute(
      Object.fromEntries(
        [
          "tenant_code",
          "system_code",
          "connection_code",
          "object_schema",
          "object_name",
          "attribute_name",
        ].map((field) => [field, record?.[`${prefix}_${field}`]]),
      ),
    );
  }

  function activePhysicalAttributes(metadata) {
    if (!(metadata instanceof Map)) return null;
    const keys = new Set();
    for (const zone of ["source", "bronze", "silver", "gold"]) {
      for (const record of records(metadata, `${zone}_attribute`)) {
        if (record?.is_active !== false) keys.add(physicalAttribute(record));
      }
    }
    return keys;
  }

  function missing(issues, dataset, record, field) {
    issues.push({
      code: "reference_not_found",
      dataset,
      record: record + 1,
      field,
      message: "Referenced record is not present in the effective Model graph.",
    });
  }

  function sourceKey(source) {
    if (source?.support_source_type === "assertion") {
      return core.stableStringify([
        "assertion",
        normalized(source.assertion_record?.modeling_assertion_record_key),
      ]);
    }
    const physical = source?.source_object || source?.source_attribute || {};
    const values = [
      source?.support_source_type,
      ...["tenant_code", "system_code", "connection_code", "object_schema", "object_name"].map(
        (field) => normalized(physical[field]),
      ),
    ];
    if (source?.support_source_type === "attribute") {
      values.push(normalized(physical.attribute_name));
    }
    return core.stableStringify(values);
  }

  function validateNestedUniqueness(datasets, issues) {
    function check(dataset, record, index, field, key) {
      const values = Array.isArray(record[field]) ? record[field] : [];
      const seen = new Set();
      for (const value of values) {
        const nestedKey = key(value);
        if (seen.has(nestedKey)) {
          issues.push({
            code: "duplicate_nested_key",
            dataset,
            record: index + 1,
            field,
            message: `${field} contains a normalized duplicate.`,
          });
          return;
        }
        seen.add(nestedKey);
      }
    }

    records(datasets, "modeling_assertion_record").forEach((record, index) => {
      check(
        "modeling_assertion_record",
        record,
        index,
        "modeling_assertion_applicable_layers",
        normalized,
      );
    });
    for (const dataset of ["conceptual_object", "conceptual_relationship"]) {
      records(datasets, dataset).forEach((record, index) => {
        if (dataset === "conceptual_object") {
          check(dataset, record, index, "conceptual_object_aliases", normalized);
        }
        check(dataset, record, index, "supports", sourceKey);
      });
    }
    for (const layer of ["logical", "dimensional"]) {
      const entityDataset = `${layer}_entity`;
      records(datasets, entityDataset).forEach((record, index) => {
        check(entityDataset, record, index, "submodels", (membership) =>
          normalized(membership?.submodel_name),
        );
        check(entityDataset, record, index, "sources", sourceKey);
      });
      const attributeDataset = `${layer}_attribute`;
      records(datasets, attributeDataset).forEach((record, index) => {
        check(attributeDataset, record, index, "sources", sourceKey);
      });
    }
  }

  function validateRecordPolicies(datasets, issues) {
    function invalid(dataset, index, field, message) {
      issues.push({
        code: "record_policy_invalid",
        dataset,
        record: index + 1,
        field,
        message,
      });
    }

    function jsonBytes(value) {
      return new TextEncoder().encode(JSON.stringify(value)).length;
    }

    changedRecords(datasets, "generated_code").forEach((record, index) => {
      const content = record.generated_code_content;
      if (
        typeof content !== "string" ||
        [...content].some(
          (character) => character.codePointAt(0) < 32 && !new Set(["\t", "\n", "\r"]).has(character),
        )
      ) {
        invalid(
          "generated_code",
          index,
          "generated_code_content",
          "Generated Code contains an unsupported control character.",
        );
      } else if (sha256Text(content) !== record.generated_code_digest) {
        invalid(
          "generated_code",
          index,
          "generated_code_digest",
          "Generated Code digest does not match its content.",
        );
      }
    });

    changedRecords(datasets, "validation_group").forEach((record, index) => {
      if (
        record.validation_group_description != null &&
        utf8Bytes(record.validation_group_description).length > 16384
      ) {
        invalid(
          "validation_group",
          index,
          "validation_group_description",
          "Validation Group description is too large.",
        );
      }
    });

    function isoDateParts(value) {
      if (typeof value !== "string") return null;
      const match = /^(\d{4})(?:-(\d{2})-(\d{2})|(\d{2})(\d{2}))$/u.exec(value);
      const weekMatch = /^(\d{4})(?:-W(\d{2})(?:-(\d))?|W(\d{2})(\d)?)$/u.exec(value);
      if (!match && !weekMatch) return null;
      if (weekMatch) {
        const year = Number(weekMatch[1]);
        const week = Number(weekMatch[2] ?? weekMatch[4]);
        const weekday = Number(weekMatch[3] ?? weekMatch[5] ?? "1");
        if (year < 1 || year > 9999 || weekday < 1 || weekday > 7) return null;
        const first = new Date(0);
        first.setUTCHours(0, 0, 0, 0);
        first.setUTCFullYear(year, 0, 1);
        const firstWeekday = first.getUTCDay() === 0 ? 7 : first.getUTCDay();
        const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
        const maximumWeek = firstWeekday === 4 || (firstWeekday === 3 && leap) ? 53 : 52;
        if (week < 1 || week > maximumWeek) return null;
        const januaryFourth = new Date(0);
        januaryFourth.setUTCHours(0, 0, 0, 0);
        januaryFourth.setUTCFullYear(year, 0, 4);
        const januaryFourthWeekday = januaryFourth.getUTCDay() === 0
          ? 7
          : januaryFourth.getUTCDay();
        januaryFourth.setUTCDate(
          januaryFourth.getUTCDate() - januaryFourthWeekday + 1 + (week - 1) * 7 + weekday - 1,
        );
        const parts = [
          januaryFourth.getUTCFullYear(),
          januaryFourth.getUTCMonth() + 1,
          januaryFourth.getUTCDate(),
        ];
        return parts[0] >= 1 && parts[0] <= 9999 ? parts : null;
      }
      const year = Number(match[1]);
      const month = Number(match[2] ?? match[4]);
      const day = Number(match[3] ?? match[5]);
      if (year < 1 || year > 9999) return null;
      const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
      const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
      return month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1]
        ? [year, month, day]
        : null;
    }

    function isoDateSeparatorIndex(value) {
      const characters = [...value];
      if (characters.length === 7) return 7;
      if (characters.length < 8) return -1;
      if (characters[4] === "-") {
        if (characters[5] !== "W") return 10;
        if (characters.length > 8 && characters[8] === "-") {
          if (characters.length === 9) return -1;
          if (characters.length > 10 && /^[0-9]$/u.test(characters[10])) return 8;
          return 10;
        }
        return 8;
      }
      if (characters[4] !== "W") return 8;
      let index = 7;
      while (index < characters.length && /^[0-9]$/u.test(characters[index])) index += 1;
      if (index < 9) return index;
      return index % 2 === 0 ? 7 : 8;
    }

    function validIsoTime(value) {
      const match = /^(\d{2})(?:(?::(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)|(?:(\d{2})(?:(\d{2})(?:[.,](\d+))?)?))?(Z|[+-](?:\d{2}|\d{4}|\d{2}:\d{2}|\d{6}(?:[.,]\d+)?|\d{2}:\d{2}:\d{2}(?:[.,]\d+)?))?$/u.exec(value);
      if (!match) return null;
      const hour = Number(match[1]);
      const minute = Number(match[2] ?? match[5] ?? "0");
      const second = Number(match[3] ?? match[6] ?? "0");
      const fraction = match[4] ?? match[7] ?? "";
      if (minute > 59 || second > 59 || hour > 24) return null;
      const nextDay = hour === 24;
      if (nextDay && (minute !== 0 || second !== 0 || /[1-9]/u.test(fraction))) return null;
      const zone = match[8];
      if (zone && zone !== "Z") {
        const offset = zone.slice(1);
        let offsetMatch = /^(\d{2})$/u.exec(offset);
        if (!offsetMatch) {
          offsetMatch = /^(\d{2})(?::?(\d{2}))(?::?(\d{2})(?:[.,]\d+)?)?$/u.exec(offset);
        }
        if (!offsetMatch) return null;
        const hours = Number(offsetMatch[1]);
        const minutes = Number(offsetMatch[2] ?? "0");
        const seconds = Number(offsetMatch[3] ?? "0");
        if (hours * 3600 + minutes * 60 + seconds >= 86400) return null;
      }
      return { nextDay };
    }

    function validIsoTimestamp(value) {
      if (typeof value !== "string") return false;
      const characters = [...value];
      const separator = isoDateSeparatorIndex(value);
      if (separator < 0 || separator > characters.length) return false;
      const date = characters.slice(0, separator).join("");
      const dateParts = isoDateParts(date);
      if (dateParts === null) return false;
      if (separator === characters.length) return true;
      const time = characters.slice(separator + 1).join("");
      if (!time) return false;
      const parsedTime = validIsoTime(time);
      if (parsedTime === null) return false;
      return !(
        parsedTime.nextDay &&
        dateParts[0] === 9999 &&
        dateParts[1] === 12 &&
        dateParts[2] === 31
      );
    }

    function literalMatches(resultType, value) {
      if (resultType === "boolean") return typeof value === "boolean";
      if (resultType === "integer") return Number.isInteger(value);
      if (resultType === "decimal") return typeof value === "number" && Number.isFinite(value);
      if (resultType === "text") return typeof value === "string";
      if (resultType === "date") return isoDateParts(value) !== null;
      if (resultType === "timestamp") return validIsoTimestamp(value);
      return false;
    }

    changedRecords(datasets, "validation_check").forEach((record, index) => {
      if (
        (record.validation_check_description != null &&
          utf8Bytes(record.validation_check_description).length > 16384) ||
        (typeof record.validation_query_sql === "string" &&
          utf8Bytes(record.validation_query_sql).length > 100000) ||
        (record.validation_comparison_query_sql != null &&
          utf8Bytes(record.validation_comparison_query_sql).length > 100000) ||
        (record.validation_comparison_value != null &&
          jsonBytes(record.validation_comparison_value) > 65536)
      ) {
        invalid(
          "validation_check",
          index,
          "validation_payload",
          "Validation Check text or comparison value is too large.",
        );
      }
      const operator = record.validation_comparison_operator;
      const resultType = record.validation_result_data_type;
      const valueType = record.validation_comparison_value_type;
      const value = record.validation_comparison_value;
      const query = record.validation_comparison_query_sql;
      const literalOrQuery =
        (valueType === "literal" && value != null && query == null) ||
        (valueType === "query" && value == null && query != null);
      let shape = false;
      if (operator === "executes_successfully") {
        shape = resultType == null && valueType === "none" && value == null && query == null;
      } else if (new Set(["is_null", "is_not_null"]).has(operator)) {
        shape = resultType != null && valueType === "none" && value == null && query == null;
      } else if (new Set(["is_true", "is_false"]).has(operator)) {
        shape = resultType === "boolean" && valueType === "none" && value == null && query == null;
      } else if (new Set(["equal", "not_equal"]).has(operator)) {
        shape = resultType != null && literalOrQuery;
      } else if (
        new Set(["greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal"]).has(
          operator,
        )
      ) {
        shape = new Set(["integer", "decimal", "date", "timestamp"]).has(resultType) && literalOrQuery;
      } else if (new Set(["in", "not_in"]).has(operator)) {
        shape =
          resultType != null &&
          valueType === "literal_list" &&
          Array.isArray(value) &&
          value.length >= 1 &&
          value.length <= 10000 &&
          query == null;
      }
      if (!shape) {
        invalid(
          "validation_check",
          index,
          "validation_assertion",
          "Validation assertion shape is invalid.",
        );
      } else if (
        new Set(["literal", "literal_list"]).has(valueType) &&
        !(Array.isArray(value) ? value : [value]).every((item) => literalMatches(resultType, item))
      ) {
        invalid(
          "validation_check",
          index,
          "validation_comparison_value",
          "Validation comparison value does not match its result type.",
        );
      }
    });

    changedRecords(datasets, "profiling_profile").forEach((record, index) => {
      if (
        record.non_null_count + record.null_count !== record.row_count ||
        (record.blank_count != null && record.blank_count > record.non_null_count) ||
        (record.distinct_count != null && record.distinct_count > record.non_null_count) ||
        (record.min_data_length != null &&
          record.max_data_length != null &&
          record.min_data_length > record.max_data_length)
      ) {
        invalid(
          "profiling_profile",
          index,
          "profiling_counts",
          "Profiling counts or length bounds are inconsistent.",
        );
      }
    });

    changedRecords(datasets, "analysis_result").forEach((record, index) => {
      const validationValues = ANALYSIS_VALIDATION_FIELDS.map((field) => record[field]);
      if (
        validationValues.some((value) => value != null) &&
        validationValues.some((value) => value == null)
      ) {
        invalid(
          "analysis_result",
          index,
          "analysis_validation_group",
          "Analysis validation fields must all be present or all be absent.",
        );
      }
      const endpoint = (prefix) =>
        core.stableStringify(
          [
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
            "attribute_name",
          ].map((field) => normalized(record[`${prefix}_${field}`])),
        );
      if (endpoint("from") === endpoint("to")) {
        invalid("analysis_result", index, "analysis_endpoints", "Analysis endpoints must differ.");
      }
    });
    changedRecords(datasets, "conceptual_relationship").forEach((record, index) => {
      if (
        normalized(record.from_conceptual_object_name) ===
        normalized(record.to_conceptual_object_name)
      ) {
        invalid(
          "conceptual_relationship",
          index,
          "conceptual_relationship_endpoints",
          "Conceptual Relationship endpoints must differ.",
        );
      }
    });
    for (const layer of ["logical", "dimensional"]) {
      const dataset = `${layer}_relationship`;
      changedRecords(datasets, dataset).forEach((record, index) => {
        const endpoint = (prefix) =>
          pair(
            record[`${prefix}_${layer}_entity_name`],
            record[`${prefix}_${layer}_attribute_name`],
          );
        if (endpoint("from") === endpoint("to")) {
          invalid(
            dataset,
            index,
            `${layer}_relationship_endpoints`,
            `${layer} Relationship endpoints must differ.`,
          );
        }
      });
    }
    changedRecords(datasets, "logical_entity").forEach((record, index) => {
      if (
        (record.logical_entity_type === "other") !==
        (record.logical_entity_type_detail != null)
      ) {
        invalid(
          "logical_entity",
          index,
          "logical_entity_type_detail",
          "Logical Entity type detail is required only for other.",
        );
      }
    });
    changedRecords(datasets, "logical_attribute").forEach((record, index) => {
      const natural = record.logical_attribute_is_natural_key === true;
      const surrogate = record.logical_attribute_is_surrogate_key === true;
      const primary = record.logical_attribute_is_primary_key === true;
      if ((natural && surrogate) || ((primary || natural || surrogate) && record.logical_attribute_is_nullable === true)) {
        invalid(
          "logical_attribute",
          index,
          "logical_attribute_key_policy",
          "Logical key flags and nullability are inconsistent.",
        );
      }
    });
    changedRecords(datasets, "dimensional_entity").forEach((record, index) => {
      if (
        (record.dimensional_entity_type === "fact") !==
          (record.dimensional_fact_type != null) ||
        (new Set(["fact", "bridge"]).has(record.dimensional_entity_type) &&
          record.dimensional_entity_grain_definition == null)
      ) {
        invalid(
          "dimensional_entity",
          index,
          "dimensional_entity_policy",
          "Dimensional type, fact type, and grain are inconsistent.",
        );
      }
    });
    changedRecords(datasets, "dimensional_attribute").forEach((record, index) => {
      if (
        record.dimensional_attribute_key_role !== "none" &&
        !new Set(["key", "technical"]).has(record.dimensional_attribute_role)
      ) {
        invalid(
          "dimensional_attribute",
          index,
          "dimensional_attribute_key_role",
          "A Dimensional key role requires a key or technical Attribute.",
        );
      }
      const measure = [
        record.dimensional_attribute_additivity,
        record.dimensional_attribute_default_aggregation,
        record.dimensional_attribute_aggregation_basis,
      ];
      if (
        (record.dimensional_attribute_role === "measure" &&
          (measure[0] == null ||
            measure[1] == null ||
            (measure[0] !== "additive" && measure[2] == null))) ||
        (record.dimensional_attribute_role !== "measure" &&
          measure.some((value) => value != null))
      ) {
        invalid(
          "dimensional_attribute",
          index,
          "dimensional_attribute_measure_policy",
          "Dimensional measure policy fields are inconsistent.",
        );
      }
      if (
        record.dimensional_attribute_is_audit_column !==
        (record.dimensional_attribute_role === "audit")
      ) {
        invalid(
          "dimensional_attribute",
          index,
          "dimensional_attribute_audit_policy",
          "Dimensional audit flag and role must agree.",
        );
      }
    });
    changedRecords(datasets, "mapping_object").forEach((record, index) => {
      const authored = [
        record.artifact_type,
        record.artifact_generation_instructions,
        record.mapping_profile_key,
        record.mapping_profile_version,
        record.mapping_package_document,
        record.object_mapping_transformation_document,
      ];
      if (authored.some((value) => value == null) && authored.some((value) => value != null)) {
        invalid(
          "mapping_object",
          index,
          "mapping_authored_group",
          "Mapping authored fields must be entirely present or absent.",
        );
      }
      if (record.mapping_package_document != null && jsonBytes(record.mapping_package_document) > 524288) {
        invalid(
          "mapping_object",
          index,
          "mapping_package_document",
          "Mapping package document is too large.",
        );
      }
      const transformation = record.object_mapping_transformation_document;
      if (
        transformation != null &&
        (transformation.schema_version !== "1.0" ||
          !new Set(["direct", "derived"]).has(transformation.transformation_kind) ||
          jsonBytes(transformation) > 262144)
      ) {
        invalid(
          "mapping_object",
          index,
          "object_mapping_transformation_document",
          "Object Mapping transformation contract is invalid.",
        );
      }
    });
    changedRecords(datasets, "mapping_attribute").forEach((record, index) => {
      const transformation = record.attribute_mapping_transformation_document;
      if (
        transformation != null &&
        (transformation.schema_version !== "1.0" ||
          !new Set(["direct", "expression"]).has(transformation.transformation_kind) ||
          jsonBytes(transformation) > 65536)
      ) {
        invalid(
          "mapping_attribute",
          index,
          "attribute_mapping_transformation_document",
          "Attribute Mapping transformation contract is invalid.",
        );
      }
    });
  }

  function validateAssertionReference(issues, assertions, source, layer, dataset, index) {
    if (source?.support_source_type !== "assertion") return;
    const key = normalized(source.assertion_record?.modeling_assertion_record_key);
    const assertion = assertions.get(key);
    if (!assertion) {
      missing(issues, dataset, index, "modeling_assertion_record_key");
      return;
    }
    const layers = Array.isArray(assertion.modeling_assertion_applicable_layers)
      ? assertion.modeling_assertion_applicable_layers
      : [];
    if (!layers.includes(layer)) {
      issues.push({
        code: "assertion_layer_invalid",
        dataset,
        record: index + 1,
        field: "modeling_assertion_record_key",
        message: "Referenced Assertion does not apply to this modeling layer.",
      });
    }
  }

  function validateAssertions(datasets, issues) {
    const documents = names(
      datasets,
      "modeling_assertion_document",
      "modeling_assertion_document_name",
    );
    const assertions = new Map(
      records(datasets, "modeling_assertion_record").map((record) => [
        normalized(record.modeling_assertion_record_key),
        record,
      ]),
    );
    records(datasets, "modeling_assertion_record").forEach((record, index) => {
      if (!documents.has(normalized(record.modeling_assertion_document_name))) {
        missing(issues, "modeling_assertion_record", index, "modeling_assertion_document_name");
      }
    });
    for (const [dataset, layer, field] of [
      ["conceptual_object", "conceptual", "supports"],
      ["conceptual_relationship", "conceptual", "supports"],
      ["logical_entity", "logical", "sources"],
      ["logical_attribute", "logical", "sources"],
      ["dimensional_entity", "dimensional", "sources"],
      ["dimensional_attribute", "dimensional", "sources"],
    ]) {
      records(datasets, dataset).forEach((record, index) => {
        for (const source of Array.isArray(record[field]) ? record[field] : []) {
          validateAssertionReference(issues, assertions, source, layer, dataset, index);
        }
      });
    }
  }

  function validateConceptual(datasets, issues) {
    const conceptual = names(datasets, "conceptual_object", "conceptual_object_name");
    records(datasets, "conceptual_relationship").forEach((record, index) => {
      if (
        !conceptual.has(normalized(record.from_conceptual_object_name)) ||
        !conceptual.has(normalized(record.to_conceptual_object_name))
      ) {
        missing(issues, "conceptual_relationship", index, "conceptual_object_name");
      }
    });
  }

  function validateModeledLayer(datasets, layer, issues) {
    const entityDataset = `${layer}_entity`;
    const attributeDataset = `${layer}_attribute`;
    const relationshipDataset = `${layer}_relationship`;
    const entityField = `${layer}_entity_name`;
    const attributeField = `${layer}_attribute_name`;
    const submodels = names(datasets, `${layer}_submodel`, `${layer}_submodel_name`);
    const entities = names(datasets, entityDataset, entityField);
    const attributes = new Set();

    records(datasets, entityDataset).forEach((record, index) => {
      for (const membership of Array.isArray(record.submodels) ? record.submodels : []) {
        if (!submodels.has(normalized(membership.submodel_name))) {
          missing(issues, entityDataset, index, "submodel_name");
        }
      }
    });
    records(datasets, attributeDataset).forEach((record, index) => {
      if (!entities.has(normalized(record[entityField]))) {
        missing(issues, attributeDataset, index, entityField);
      }
      attributes.add(pair(record[entityField], record[attributeField]));
    });
    records(datasets, relationshipDataset).forEach((record, index) => {
      const endpoints = ["from", "to"].map((endpoint) =>
        pair(record[`${endpoint}_${entityField}`], record[`${endpoint}_${attributeField}`]),
      );
      if (endpoints.some((endpoint) => !attributes.has(endpoint))) {
        missing(issues, relationshipDataset, index, attributeField);
      }
    });
    return { entities, attributes };
  }

  function mappingObjectKey(record) {
    return core.stableStringify([
      physicalObject(record),
      normalized(record?.source_system_code),
      record?.modeled_entity_type,
      normalized(record?.modeled_entity_name),
    ]);
  }

  function validateMapping(datasets, logical, dimensional, issues) {
    const dependencies = new Set(
      records(datasets, "mapping_dependency").map((record) =>
        core.stableStringify([
          record.modeled_entity_type,
          normalized(record.source_system_code),
        ]),
      ),
    );
    const mappingObjects = new Set();
    records(datasets, "mapping_object").forEach((record, index) => {
      const dependency = core.stableStringify([
        record.modeled_entity_type,
        normalized(record.source_system_code),
      ]);
      if (!dependencies.has(dependency)) {
        missing(issues, "mapping_object", index, "mapping_dependency");
      }
      const entityNames =
        record.modeled_entity_type === "logical_entity"
          ? logical.entities
          : record.modeled_entity_type === "dimensional_entity"
            ? dimensional.entities
            : new Set();
      if (!entityNames.has(normalized(record.modeled_entity_name))) {
        missing(issues, "mapping_object", index, "modeled_entity_name");
      }
      mappingObjects.add(mappingObjectKey(record));
    });
    records(datasets, "mapping_attribute").forEach((record, index) => {
      if (!mappingObjects.has(mappingObjectKey(record))) {
        missing(issues, "mapping_attribute", index, "mapping_object");
      }
      const attributes =
        record.modeled_entity_type === "logical_entity"
          ? logical.attributes
          : record.modeled_entity_type === "dimensional_entity"
            ? dimensional.attributes
            : new Set();
      if (!attributes.has(pair(record.modeled_entity_name, record.modeled_attribute_name))) {
        missing(issues, "mapping_attribute", index, "modeled_attribute_name");
      }
    });
  }

  function validateAppliedLocks(datasets, issues) {
    for (const [dataset, value] of datasets) {
      if (
        !value?.definition ||
        !Array.isArray(value.definition.canonical_key) ||
        !Array.isArray(value.baseline) ||
        !Array.isArray(value.pending)
      ) {
        continue;
      }
      const applied = new Map(
        value.baseline.map((record) => [
          core.stableStringify(core.key("model", value.definition, record)),
          record,
        ]),
      );
      value.pending.forEach((record, index) => {
        const existing = applied.get(
          core.stableStringify(core.key("model", value.definition, record)),
        );
        if (
          existing &&
          Object.entries(existing).some(
            ([field, fieldValue]) =>
              (field === "is_locked" || field.endsWith("_is_locked")) && fieldValue === true,
          ) &&
          core.stableStringify(existing) !== core.stableStringify(record)
        ) {
          issues.push({
            code: "record_locked",
            dataset,
            record: index + 1,
            field: value.definition.canonical_key.join(","),
            message: "A locked applied record cannot be changed.",
          });
        }
      });
    }
  }

  function validateQa(datasets, issues) {
    const key = (record) =>
      core.stableStringify(
        ["tenant_code", "system_code", "validation_group_name"].map((field) =>
          normalized(record?.[field]),
        ),
      );
    const groups = new Map(records(datasets, "validation_group").map((record) => [key(record), record]));
    records(datasets, "validation_check").forEach((record, index) => {
      const group = groups.get(key(record));
      if (!group) {
        missing(issues, "validation_check", index, "validation_group_name");
      } else if (record.is_active === true && group.is_active !== true) {
        issues.push({
          code: "validation_group_inactive",
          dataset: "validation_check",
          record: index + 1,
          field: "validation_group_name",
          message: "An active Validation Check requires an active Validation Group.",
        });
      }
    });

    const mappingIsChanged = ["mapping_dependency", "mapping_object", "mapping_attribute"]
      .some((dataset) => changedRecords(datasets, dataset).length > 0);
    const codeIsChanged = changedRecords(datasets, "generated_code").length > 0;
    const qaIsChanged = ["validation_group", "validation_check"]
      .some((dataset) => changedRecords(datasets, dataset).length > 0);
    if (mappingIsChanged && codeIsChanged) {
      issues.push({
        code: "context_order_invalid",
        dataset: "generated_code",
        field: "mapping_context_digest",
        message: "Generated Code must be authored after its Mapping Change Set is applied.",
      });
    }
    if (qaIsChanged && (mappingIsChanged || codeIsChanged)) {
      issues.push({
        code: "context_order_invalid",
        dataset: "validation_group",
        field: "mapping_context_digest",
        message: "QA must be authored after its Mapping and Code Change Sets are applied.",
      });
    }

    const systemKey = (record) =>
      core.stableStringify(
        ["tenant_code", "system_code"].map((field) => normalized(record?.[field])),
      );
    const contexts = new Map(
      records(datasets, "qa_authoring_context").map((record) => [systemKey(record), record]),
    );
    const groupsRequiringContext = new Set(
      changedRecords(datasets, "validation_group")
        .filter((record) => record?.is_active === true)
        .map(key),
    );
    changedRecords(datasets, "validation_check")
      .filter((record) => record?.is_active === true)
      .forEach((record) => groupsRequiringContext.add(key(record)));
    for (const groupKey of groupsRequiringContext) {
      const group = groups.get(groupKey);
      if (!group || group.is_active !== true) continue;
      const context = contexts.get(systemKey(group));
      if (!context || group.mapping_context_digest !== context.mapping_context_digest) {
        issues.push({
          code: "context_digest_invalid",
          dataset: "validation_group",
          field: "mapping_context_digest",
          message: "Validation Group Mapping context digest is stale or invalid.",
        });
      }
      if (!context || group.code_context_digest !== context.code_context_digest) {
        issues.push({
          code: "context_digest_invalid",
          dataset: "validation_group",
          field: "code_context_digest",
          message: "Validation Group Code context digest is stale or invalid.",
        });
      }
    }
  }

  function validatePhysicalScope(datasets, scope, metadata, issues) {
    const physicalAttributes = activePhysicalAttributes(metadata);
    const appliedLogicalMappingAttributes = new Set(
      baselineRecords(datasets, "mapping_attribute")
        .filter(
          (record) =>
            record?.modeled_entity_type === "logical_entity" &&
            record?.attribute_mapping_status !== "inactive",
        )
        .map(physicalAttribute),
    );
    function requireScope(
      dataset,
      index,
      field,
      key,
      eligibilityField = null,
      message = "Referenced physical Object is not active in Model Scope.",
    ) {
      const scoped = scope.get(key);
      if (!scoped || (eligibilityField !== null && scoped[eligibilityField] !== true)) {
        issues.push({
          code: "model_scope_reference_invalid",
          dataset,
          record: index + 1,
          field,
          message,
        });
        return false;
      }
      return true;
    }

    function requireAttributeScope(
      dataset,
      index,
      field,
      objectKey,
      attributeKey,
      eligibilityField,
      message,
    ) {
      const objectIsEligible = requireScope(
        dataset,
        index,
        field,
        objectKey,
        eligibilityField,
        message,
      );
      if (physicalAttributes === null) {
        issues.push({
          code: "physical_attribute_context_missing",
          dataset,
          record: index + 1,
          field,
          message: "Fresh Metadata Attribute context is required for local validation.",
        });
      } else if (
        objectIsEligible &&
        (!physicalAttributes.has(attributeKey) ||
          (eligibilityField === "is_dimensional_source_eligible" &&
            !appliedLogicalMappingAttributes.has(attributeKey)))
      ) {
        issues.push({
          code: "model_scope_reference_invalid",
          dataset,
          record: index + 1,
          field,
          message,
        });
      }
    }

    for (const dataset of ["conceptual_object", "conceptual_relationship"]) {
      changedRecords(datasets, dataset).forEach((record, index) => {
        for (const support of Array.isArray(record.supports) ? record.supports : []) {
          if (support?.support_source_type === "object") {
            requireScope(
              dataset,
              index,
              "source_object",
              physicalObject(support.source_object),
              "is_bronze_source_eligible",
              "Referenced physical Object is not an eligible Bronze source.",
            );
          }
        }
      });
    }
    for (const layer of ["logical", "dimensional"]) {
      const eligibilityField =
        layer === "logical" ? "is_bronze_source_eligible" : "is_dimensional_source_eligible";
      const objectEligibilityMessage =
        layer === "logical"
          ? "Referenced physical Object is not an eligible Bronze source."
          : "Referenced physical Object is not an eligible Silver contribution from applied Logical Mapping.";
      const attributeEligibilityMessage =
        layer === "logical"
          ? "Referenced physical Attribute is not an eligible Bronze source."
          : "Referenced physical Attribute is not an eligible Silver contribution from applied Logical Mapping.";
      const entityDataset = `${layer}_entity`;
      changedRecords(datasets, entityDataset).forEach((record, index) => {
        for (const source of Array.isArray(record.sources) ? record.sources : []) {
          if (source?.support_source_type === "object") {
            requireScope(
              entityDataset,
              index,
              "source_object",
              physicalObject(source.source_object),
              eligibilityField,
              objectEligibilityMessage,
            );
          }
        }
      });
      const attributeDataset = `${layer}_attribute`;
      changedRecords(datasets, attributeDataset).forEach((record, index) => {
        for (const source of Array.isArray(record.sources) ? record.sources : []) {
          if (source?.support_source_type === "attribute") {
            requireAttributeScope(
              attributeDataset,
              index,
              "source_attribute",
              physicalObject(source.source_attribute),
              physicalAttribute(source.source_attribute),
              eligibilityField,
              attributeEligibilityMessage,
            );
          }
        }
      });
    }
    changedRecords(datasets, "profiling_profile").forEach((record, index) => {
      requireAttributeScope(
        "profiling_profile",
        index,
        "attribute_name",
        physicalObject(record),
        physicalAttribute(record),
        "is_bronze_source_eligible",
        "Referenced physical Attribute is not an eligible Bronze source.",
      );
    });
    changedRecords(datasets, "analysis_result").forEach((record, index) => {
      for (const endpoint of ["from", "to"]) {
        requireAttributeScope(
          "analysis_result",
          index,
          `${endpoint}_attribute_name`,
          prefixedPhysicalObject(record, endpoint),
          prefixedPhysicalAttribute(record, endpoint),
          "is_bronze_source_eligible",
          "Referenced physical Attribute is not an eligible Bronze source.",
        );
      }
    });
    for (const dataset of ["mapping_object", "mapping_attribute"]) {
      changedRecords(datasets, dataset).forEach((record, index) => {
        const eligibilityField =
          record.modeled_entity_type === "logical_entity"
            ? "is_logical_mapping_target_eligible"
            : "is_dimensional_mapping_target_eligible";
        if (dataset === "mapping_attribute") {
          requireAttributeScope(
            dataset,
            index,
            "attribute_name",
            physicalObject(record),
            physicalAttribute(record),
            eligibilityField,
            "Referenced Mapping target Attribute is not eligible for its modeled layer.",
          );
        } else {
          requireScope(
            dataset,
            index,
            "object_name",
            physicalObject(record),
            eligibilityField,
            "Referenced Mapping target Object is not eligible for its modeled layer.",
          );
        }
      });
    }
  }

  function validateGraph(datasets, metadata = null) {
    const issues = [];
    validateAppliedLocks(datasets, issues);
    validateNestedUniqueness(datasets, issues);
    validateRecordPolicies(datasets, issues);
    validateAssertions(datasets, issues);
    validateConceptual(datasets, issues);
    const logical = validateModeledLayer(datasets, "logical", issues);
    const dimensional = validateModeledLayer(datasets, "dimensional", issues);
    const scope = new Map(
      records(datasets, "model_scope")
        .filter((record) => record.is_active === true)
        .map((record) => [physicalObject(record), record]),
    );
    validatePhysicalScope(datasets, scope, metadata, issues);
    validateMapping(datasets, logical, dimensional, issues);
    validateQa(datasets, issues);
    return issues;
  }

  return { validateGraph };
});
