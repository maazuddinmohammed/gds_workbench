(function (root, factory) {
  "use strict";
  let core = root.GDSCore;
  if (typeof module === "object" && module.exports) core = require("../core.js");
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSModelValidation = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  const OBJECT_FIELDS = [
    "tenant_code", "system_code", "connection_code", "object_schema", "object_name",
  ];
  const ATTRIBUTE_FIELDS = [...OBJECT_FIELDS, "attribute_name"];

  function normalized(value) { return core.normalize("model", "value", value); }
  function tuple(values) { return core.stableStringify(values.map(normalized)); }
  function physicalKey(record, attribute = false) {
    return tuple((attribute ? ATTRIBUTE_FIELDS : OBJECT_FIELDS).map((field) => record?.[field]));
  }
  function prefixedPhysicalKey(record, prefix, attribute = false) {
    return tuple((attribute ? ATTRIBUTE_FIELDS : OBJECT_FIELDS)
      .map((field) => record?.[`${prefix}_${field}`]));
  }
  function entityKey(record) {
    let type = record?.modeled_entity_type;
    if (!type) type = Object.hasOwn(record || {}, "logical_entity_name")
      ? "logical_entity" : "dimensional_entity";
    const name = record?.modeled_entity_name ?? record?.[
      type === "logical_entity" ? "logical_entity_name" : "dimensional_entity_name"
    ];
    return tuple([type, name]);
  }
  function attributeKey(record) {
    let type = record?.modeled_entity_type;
    if (!type) type = Object.hasOwn(record || {}, "logical_attribute_name")
      ? "logical_entity" : "dimensional_entity";
    const entity = record?.modeled_entity_name ?? record?.[
      type === "logical_entity" ? "logical_entity_name" : "dimensional_entity_name"
    ];
    const attribute = record?.modeled_attribute_name ?? record?.[
      type === "logical_entity" ? "logical_attribute_name" : "dimensional_attribute_name"
    ];
    return tuple([type, entity, attribute]);
  }
  function mappingObjectKey(record) {
    return tuple([record.modeled_entity_type, record.modeled_entity_name, record.source_system_code]);
  }
  function artifactKey(record) {
    return tuple([record.modeled_entity_type, record.modeled_entity_name, record.artifact_name]);
  }
  function validationGroupKey(record) {
    return tuple([record.tenant_code, record.system_code, record.validation_group_name]);
  }
  function recordType(value) {
    return value.schema?.["x-gds-record-type"] || value.definition?.record_type || value.definition?.name;
  }
  function records(datasets, name, source = "records") {
    return datasets?.get(name)?.[source] || [];
  }
  function active(record, field = null) {
    return field ? record?.[field] === "active" : core.active(record) !== false;
  }
  function issue(issues, code, dataset, field, message, record = null) {
    issues.push({ code, dataset, record, field, message });
  }

  function candidateGroups(model, metadata) {
    const groups = new Map();
    function add(area, datasets) {
      if (!(datasets instanceof Map)) return;
      for (const value of datasets.values()) {
        const type = recordType(value);
        if (typeof type !== "string" || !type) continue;
        if (!groups.has(type)) groups.set(type, []);
        groups.get(type).push({
          area,
          records: value.records || value.effective || value.baseline || [],
        });
      }
    }
    add("model", model);
    add("metadata", metadata);
    return groups;
  }

  function validateReferences(model, metadata) {
    const targets = candidateGroups(model, metadata);
    const issues = [];
    for (const [datasetName, value] of model) {
      const references = value.schema?.["x-gds-references"];
      if (references === undefined) continue;
      if (!Array.isArray(references)) {
        issue(issues, "invalid_reference_contract", datasetName, null,
          "Reference metadata must be an array.");
        continue;
      }
      value.records.forEach((record, recordIndex) => {
        for (const reference of references) {
          const columns = reference?.columns;
          const targetColumns = reference?.target_columns;
          const candidates = targets.get(reference?.target_record_type) || [];
          if (!Array.isArray(columns) || !columns.length || !Array.isArray(targetColumns) ||
              columns.length !== targetColumns.length || !candidates.length) {
            issue(issues, "invalid_reference_contract", datasetName, null,
              `Invalid reference to ${reference?.target_record_type || "unknown"}.`, recordIndex + 1);
            continue;
          }
          const values = columns.map((field) => record[field]);
          const nullCount = values.filter((item) => item === null || item === undefined).length;
          if (nullCount === values.length && reference.nullable === true) continue;
          if (nullCount > 0) {
            issue(issues, "partial_null_reference", datasetName, columns[0],
              `Reference to ${reference.target_record_type} is incomplete.`, recordIndex + 1);
            continue;
          }
          const found = candidates.some((candidate) => {
            const wanted = core.stableStringify(values.map((item, index) =>
              core.normalize(candidate.area, targetColumns[index], item)));
            return candidate.records.some((target) =>
              core.stableStringify(targetColumns.map((field) =>
                core.normalize(candidate.area, field, target[field]))) === wanted);
          });
          if (!found) issue(issues, "broken_reference", datasetName, columns[0],
            `Referenced ${reference.target_record_type} was not found.`, recordIndex + 1);
        }
      });
    }
    return issues;
  }

  function nestedKey(record) {
    if (record?.submodel_name !== undefined) return tuple(["submodel", record.submodel_name]);
    if (record?.support_source_type === "assertion") {
      return tuple(["assertion", record.assertion_record?.modeling_assertion_record_key]);
    }
    const source = record?.support_source_type === "attribute"
      ? record.source_attribute : record?.source_object;
    return tuple([record?.support_source_type, ...(record?.support_source_type === "attribute"
      ? ATTRIBUTE_FIELDS : OBJECT_FIELDS).map((field) => source?.[field])]);
  }
  function locked(record) {
    return Object.entries(record || {}).some(([field, value]) =>
      value === true && (field === "is_locked" || field.endsWith("_is_locked")));
  }
  function validateNestedLocks(model) {
    const issues = [];
    for (const [name, value] of model) {
      const baseline = new Map();
      for (const record of value.baseline || []) {
        baseline.set(core.stableStringify(core.key("model", value.definition, record)), record);
      }
      for (const changed of value.pending || []) {
        let existing;
        try {
          existing = baseline.get(core.stableStringify(core.key("model", value.definition, changed)));
        } catch (_error) { continue; }
        if (!existing) continue;
        for (const field of ["supports", "submodels", "sources"]) {
          const changedItems = new Map((changed[field] || []).map((item) => [nestedKey(item), item]));
          for (const item of existing[field] || []) {
            const replacement = changedItems.get(nestedKey(item));
            if (replacement && locked(item) &&
                core.stableStringify(item) !== core.stableStringify(replacement)) {
              issue(issues, "record_locked", name, field,
                `A locked applied nested ${field} record cannot be changed.`);
            }
          }
        }
      }
    }
    return issues;
  }

  function attributesFor(attributeKeys, objectSet) {
    return new Set([...attributeKeys].filter((key) =>
      objectSet.has(core.stableStringify(JSON.parse(key).slice(0, 5)))));
  }

  function buildPhysicalCatalog(model, metadata, context) {
    if (!(metadata instanceof Map) || typeof context?.tenantCode !== "string") return null;
    const objects = [];
    const attributes = [];
    const systems = [];
    for (const value of metadata.values()) {
      const type = recordType(value);
      const source = value.records || value.effective || value.baseline || [];
      if (type === "object") objects.push(...source.filter((record) => record.is_active !== false));
      else if (type === "attribute") attributes.push(...source.filter((record) => record.is_active !== false));
      else if (type === "system") systems.push(...source.filter((record) => record.is_active !== false));
    }
    const objectKeys = new Set(objects.map((record) => physicalKey(record)));
    const attributeKeys = new Set(attributes
      .filter((record) => objectKeys.has(physicalKey(record)))
      .map((record) => physicalKey(record, true)));
    const byZone = (zone) => new Set(objects
      .filter((record) => normalized(record.zone_code) === zone)
      .map((record) => physicalKey(record)));
    const logicalTargets = byZone("silver");
    const dimensionalTargets = byZone("gold");
    const inputObjects = new Set(objects
      .filter((record) => ["source", "bronze"].includes(normalized(record.zone_code)))
      .map((record) => physicalKey(record)));

    const baseline = (name) => records(model, name, "baseline");
    const activeLogicalEntities = new Set(baseline("logical_entity")
      .filter((record) => active(record, "logical_entity_status")).map(entityKey));
    const activeDependencies = new Set(baseline("mapping_dependency")
      .filter((record) => active(record, "mapping_source_system_dependency_status") &&
        systems.some((system) => normalized(system.system_code) === normalized(record.source_system_code)))
      .map((record) => tuple([record.modeled_entity_type, record.source_system_code])));
    const activeObjectBindings = new Map(baseline("model_object_binding")
      .filter((record) => record.modeled_entity_type === "logical_entity" &&
        active(record, "model_object_binding_status"))
      .map((record) => [entityKey(record), physicalKey(record)]));
    const activeMappingObjects = baseline("mapping_object").filter((record) =>
      record.modeled_entity_type === "logical_entity" && active(record, "object_mapping_status") &&
      record.mapping_transformation_document !== null &&
      activeLogicalEntities.has(entityKey(record)) &&
      activeDependencies.has(tuple([record.modeled_entity_type, record.source_system_code])) &&
      activeObjectBindings.has(entityKey(record)));
    const dimensionalSourceObjects = new Set(activeMappingObjects.map((record) =>
      activeObjectBindings.get(entityKey(record))));
    const activeAttributeBindings = new Map(baseline("model_attribute_binding")
      .filter((record) => record.modeled_entity_type === "logical_entity" &&
        active(record, "model_attribute_binding_status"))
      .map((record) => {
        const object = activeObjectBindings.get(entityKey(record));
        return [attributeKey(record), object ? tuple([...JSON.parse(object), record.attribute_name]) : null];
      }).filter(([, target]) => target));
    const mappedAttributes = new Set(baseline("mapping_attribute")
      .filter((record) => active(record, "attribute_mapping_status") &&
        record.attribute_mapping_transformation_document !== null &&
        activeMappingObjects.some((parent) => mappingObjectKey(parent) === mappingObjectKey(record)))
      .map(attributeKey));
    const dimensionalSourceAttributes = new Set([...activeAttributeBindings]
      .filter(([key]) => mappedAttributes.has(key)).map(([, target]) => target));

    return {
      tenant: normalized(context.tenantCode),
      otherModelNames: new Set((context.model?.other_active_model_names || []).map(normalized)),
      activeSystems: new Set(systems.map((record) => normalized(record.system_code))),
      objects: objectKeys,
      attributes: attributeKeys,
      inputObjects,
      inputAttributes: attributesFor(attributeKeys, inputObjects),
      dimensionalSourceObjects,
      dimensionalSourceAttributes,
      logicalTargets,
      logicalTargetAttributes: attributesFor(attributeKeys, logicalTargets),
      dimensionalTargets,
      dimensionalTargetAttributes: attributesFor(attributeKeys, dimensionalTargets),
    };
  }

  function scopeIssue(issues, dataset, field, message) {
    issue(issues, "model_input_reference_invalid", dataset, field, message);
  }
  function requireSystem(catalog, value, dataset, field, issues) {
    if (!catalog.activeSystems.has(normalized(value))) {
      scopeIssue(issues, dataset, field, "Referenced System is not active.");
    }
  }
  function sourcePhysical(source) {
    if (source?.support_source_type === "object") return [source.source_object, false];
    if (source?.support_source_type === "attribute") return [source.source_attribute, true];
    return null;
  }

  function sameSet(left, right) {
    return left.size === right.size && [...left].every((value) => right.has(value));
  }

  function validateBindings(model, catalog, issues) {
    const entityTargets = new Map();
    const allEntityTargets = new Map();
    const usedObjects = new Set();
    for (const record of records(model, "model_object_binding")) {
      const entity = entityKey(record);
      const target = physicalKey(record);
      const eligible = record.modeled_entity_type === "logical_entity"
        ? catalog.logicalTargets : catalog.dimensionalTargets;
      if (!eligible.has(target)) scopeIssue(issues, "model_object_binding", "object_name",
        "Bound target Object is not eligible for its modeled layer.");
      allEntityTargets.set(entity, target);
      if (!active(record, "model_object_binding_status")) continue;
      if (usedObjects.has(target)) issue(issues, "binding_target_conflict",
        "model_object_binding", "object_name",
        "An active physical Object can bind to only one modeled Entity.");
      usedObjects.add(target);
      entityTargets.set(entity, target);
    }
    const attributeTargets = new Map();
    const usedAttributes = new Set();
    for (const record of records(model, "model_attribute_binding")) {
      const entity = entityKey(record);
      const object = allEntityTargets.get(entity);
      if (!object) {
        issue(issues, "reference_not_found", "model_attribute_binding", "model_object_binding",
          "Referenced record is not present in the future Model graph.");
        continue;
      }
      const target = tuple([...JSON.parse(object), record.attribute_name]);
      const eligible = record.modeled_entity_type === "logical_entity"
        ? catalog.logicalTargetAttributes : catalog.dimensionalTargetAttributes;
      if (!eligible.has(target)) scopeIssue(issues, "model_attribute_binding", "attribute_name",
        "Bound target Attribute is not eligible for its modeled layer.");
      if (!active(record, "model_attribute_binding_status")) continue;
      if (!entityTargets.has(entity)) {
        issue(issues, "inactive_parent", "model_attribute_binding", "modeled_entity_name",
          "An active Attribute Binding requires an active Object Binding.");
        continue;
      }
      if (usedAttributes.has(target)) issue(issues, "binding_target_conflict",
        "model_attribute_binding", "attribute_name",
        "An active physical Attribute can bind to only one modeled Attribute.");
      usedAttributes.add(target);
      attributeTargets.set(attributeKey(record), target);
    }
    const activeAttributes = new Set([
      ...records(model, "logical_attribute")
        .filter((record) => active(record, "logical_attribute_status")).map(attributeKey),
      ...records(model, "dimensional_attribute")
        .filter((record) => active(record, "dimensional_attribute_status")).map(attributeKey),
    ]);
    for (const [entity, object] of entityTargets) {
      const entityParts = JSON.parse(entity);
      const belongs = (key) => JSON.parse(key).slice(0, 2)
        .every((part, index) => part === entityParts[index]);
      const modeled = new Set([...attributeTargets].filter(([key]) => belongs(key)).map(([key]) => key));
      const expectedModeled = new Set([...activeAttributes].filter(belongs));
      if (!sameSet(modeled, expectedModeled)) issue(issues, "binding_coverage_missing",
        "model_attribute_binding", "modeled_attribute_name",
        "An active Object Binding requires one active Binding for every active modeled Attribute.");
      const eligible = entityParts[0] === "logical_entity"
        ? catalog.logicalTargetAttributes : catalog.dimensionalTargetAttributes;
      const expectedPhysical = new Set([...eligible].filter((key) =>
        core.stableStringify(JSON.parse(key).slice(0, 5)) === object));
      const boundPhysical = new Set([...attributeTargets]
        .filter(([key]) => belongs(key)).map(([, target]) => target));
      if (!sameSet(boundPhysical, expectedPhysical)) issue(issues, "binding_coverage_missing",
        "model_attribute_binding", "attribute_name",
        "An active Object Binding requires one active Binding for every active physical Attribute.");
    }
    return { entityTargets, attributeTargets };
  }

  function splitSql(sql) {
    const statements = [];
    let start = 0;
    let quote = null;
    let lineComment = false;
    let blockComment = false;
    for (let index = 0; index < sql.length; index += 1) {
      const character = sql[index];
      const next = sql[index + 1];
      if (lineComment) {
        if (character === "\n") lineComment = false;
      } else if (blockComment) {
        if (character === "*" && next === "/") {
          blockComment = false;
          index += 1;
        }
      } else if (quote) {
        if (character === quote && sql[index + 1] === quote) index += 1;
        else if (character === quote) quote = null;
      } else if (character === "-" && next === "-") {
        lineComment = true;
        index += 1;
      } else if (character === "/" && next === "*") {
        blockComment = true;
        index += 1;
      } else if (["'", '"', "`"].includes(character)) quote = character;
      else if (character === ";") {
        const value = sql.slice(start, index).trim();
        if (value) statements.push(value);
        start = index + 1;
      }
    }
    const final = sql.slice(start).trim();
    if (final) statements.push(final);
    return quote || blockComment ? null : statements;
  }

  function maskSql(sql) {
    let result = "";
    let quote = null;
    let lineComment = false;
    let blockComment = false;
    for (let index = 0; index < sql.length; index += 1) {
      const character = sql[index];
      const next = sql[index + 1];
      if (lineComment) {
        result += character === "\n" ? "\n" : " ";
        if (character === "\n") lineComment = false;
      } else if (blockComment) {
        result += " ";
        if (character === "*" && next === "/") {
          result += " ";
          blockComment = false;
          index += 1;
        }
      } else if (quote === "'") {
        result += " ";
        if (character === "'" && next === "'") {
          result += " ";
          index += 1;
        } else if (character === "'") quote = null;
      } else if (quote) {
        result += character;
        if (character === quote && next === quote) {
          result += next;
          index += 1;
        } else if (character === quote) quote = null;
      } else if (character === "-" && next === "-") {
        result += "  ";
        lineComment = true;
        index += 1;
      } else if (character === "/" && next === "*") {
        result += "  ";
        blockComment = true;
        index += 1;
      } else {
        result += character;
        if (["'", '"', "`"].includes(character)) quote = character;
      }
    }
    return result;
  }

  function unquoteIdentifier(value) {
    if ((value.startsWith("`") && value.endsWith("`")) ||
        (value.startsWith('"') && value.endsWith('"'))) return value.slice(1, -1);
    return value;
  }

  function identifierParts(value) {
    const parts = [];
    let start = 0;
    let quote = null;
    for (let index = 0; index < value.length; index += 1) {
      const character = value[index];
      if (quote) {
        if (character === quote) quote = null;
      } else if (["`", '"'].includes(character)) quote = character;
      else if (character === ".") {
        parts.push(unquoteIdentifier(value.slice(start, index)).toLowerCase());
        start = index + 1;
      }
    }
    parts.push(unquoteIdentifier(value.slice(start)).toLowerCase());
    return parts;
  }

  function identifierKey(value) { return core.stableStringify(identifierParts(value)); }

  function physicalRelationsAreSafe(sql, temporaryRelations) {
    const masked = maskSql(sql);
    if (/\b(?:from|join)\s*(?:$|where\b|group\b|order\b|having\b|limit\b)/i.test(masked)) {
      return false;
    }
    const localRelations = new Set(temporaryRelations);
    const cte = /(?:\bwith\b|,)\s*(`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)\s+as\s*\(/gi;
    for (const match of masked.matchAll(cte)) localRelations.add(identifierKey(match[1]));
    const relation = /\b(?:from|join)\s+((?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)(?:\.(?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)){0,2})/gi;
    for (const match of masked.matchAll(relation)) {
      const remainder = masked.slice(match.index + match[0].length).trimStart();
      if (remainder.startsWith("(")) continue;
      if (identifierParts(match[1]).length === 3 || localRelations.has(identifierKey(match[1]))) continue;
      return false;
    }
    const described = /\bdescribe(?:\s+table)?\s+((?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)(?:\.(?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)){0,2})/i.exec(masked);
    return !described || identifierParts(described[1]).length === 3;
  }

  function validateReadSql(sql) {
    if (typeof sql !== "string") return { valid: false, finalReturnsRows: false };
    const statements = splitSql(sql);
    if (!statements || !statements.length || statements.length > 25) {
      return { valid: false, finalReturnsRows: false };
    }
    const temporaryRelations = new Set();
    let finalReturnsRows = false;
    for (const statement of statements) {
      const masked = maskSql(statement).trim();
      const rowReturning = /^(select|with|values|describe|show)\b/i.test(masked);
      if (/\b(secret|try_secret)\s*\(/i.test(masked) ||
          /\b(insert|update|delete|merge|drop|alter|truncate|copy|grant|revoke|call|execute|into)\b/i.test(masked)) {
        return { valid: false, finalReturnsRows: false };
      }
      if (rowReturning) {
        if (/^(select|with)\b/i.test(masked) &&
            (!physicalRelationsAreSafe(masked, temporaryRelations) ||
              (/^with\b/i.test(masked) && !/\bas\s*\(/i.test(masked)) ||
              /^select\s+from\b/i.test(masked))) {
          return { valid: false, finalReturnsRows: false };
        }
        if (/^describe\b/i.test(masked) && !physicalRelationsAreSafe(masked, temporaryRelations)) {
          return { valid: false, finalReturnsRows: false };
        }
        finalReturnsRows = true;
        continue;
      }
      const create = /^create\s+(?:or\s+replace\s+)?temp(?:orary)?\s+(view|table)\s+(`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)(?=\s|\(|$)([\s\S]*)$/i.exec(masked);
      if (!create || /\b(?:using|location|clone)\b/i.test(create[3])) {
        return { valid: false, finalReturnsRows: false };
      }
      const query = /^\s+as\s+([\s\S]+)$/i.exec(create[3]);
      if (create[1].toLowerCase() === "view" && !query) {
        return { valid: false, finalReturnsRows: false };
      }
      if (query && (!/^(select|with|values)\b/i.test(query[1].trim()) ||
          !physicalRelationsAreSafe(query[1], temporaryRelations))) {
        return { valid: false, finalReturnsRows: false };
      }
      temporaryRelations.add(identifierKey(create[2]));
      finalReturnsRows = false;
    }
    return { valid: true, finalReturnsRows };
  }

  function validatePhysicalScope(model, catalog) {
    const issues = [];
    const details = records(model, "model_details");
    if (details.length !== 1) issue(issues, "model_details_invalid", "model_details", null,
      "The future Model must contain exactly one Model details record.");
    else if (catalog.otherModelNames.has(normalized(details[0].model_name))) issue(issues,
      "model_name_conflict", "model_details", "model_name",
      "Another active Model in this Tenant already uses this name.");
    const activeInputs = new Set();
    for (const record of records(model, "model_input_scope")) {
      const key = physicalKey(record);
      if (!catalog.objects.has(key)) scopeIssue(issues, "model_input_scope", "object_name",
        "Referenced physical Object is not available to this Model Tenant.");
      else if (!catalog.inputObjects.has(key)) scopeIssue(issues, "model_input_scope", "object_name",
        "Model Input Scope accepts only Source or Bronze Objects.");
      else if (record.is_active) activeInputs.add(key);
    }
    const activeInputAttributes = attributesFor(catalog.inputAttributes, activeInputs);
    for (const record of records(model, "profiling_profile"))
      if (!activeInputAttributes.has(physicalKey(record, true))) scopeIssue(issues,
        "profiling_profile", "attribute_name", "Profile Attribute is not in active Model Input Scope.");
    for (const record of records(model, "analysis_result"))
      for (const endpoint of ["from", "to"])
        if (!activeInputAttributes.has(prefixedPhysicalKey(record, endpoint, true))) scopeIssue(
          issues, "analysis_result", `${endpoint}_attribute_name`,
          "Analysis Attribute is not in active Model Input Scope.");
    for (const record of records(model, "modeling_assertion_document")) {
      if (record.tenant_code !== null && normalized(record.tenant_code) !== catalog.tenant)
        scopeIssue(issues, "modeling_assertion_document", "tenant_code",
          "Assertion document Tenant does not own this Model.");
      if (record.system_code !== null) requireSystem(catalog, record.system_code,
        "modeling_assertion_document", "system_code", issues);
    }
    const requireSource = (source, dataset, objects, attributes, message) => {
      const physical = sourcePhysical(source);
      if (!physical) return;
      const [target, isAttribute] = physical;
      if (!(isAttribute ? attributes : objects).has(physicalKey(target, isAttribute)))
        scopeIssue(issues, dataset, isAttribute ? "source_attribute" : "source_object", message);
    };
    for (const name of ["conceptual_object", "conceptual_relationship"])
      for (const record of records(model, name))
        for (const source of record.supports || []) requireSource(source, name, activeInputs,
          activeInputAttributes, "Physical support is not in active Model Input Scope.");
    for (const name of ["logical_entity", "logical_attribute"])
      for (const record of records(model, name))
        for (const source of record.sources || []) requireSource(source, name, activeInputs,
          activeInputAttributes, name === "logical_entity"
            ? "Logical source Object is not in active Model Input Scope."
            : "Logical source Attribute is not in active Model Input Scope.");

    const bindings = validateBindings(model, catalog, issues);
    const dimensionalObjects = new Set(catalog.dimensionalSourceObjects);
    const dimensionalAttributes = new Set(catalog.dimensionalSourceAttributes);
    for (const record of records(model, "mapping_object")) {
      if (active(record, "object_mapping_status") && record.modeled_entity_type === "logical_entity") {
        const target = bindings.entityTargets.get(entityKey(record));
        if (target) dimensionalObjects.add(target);
      }
    }
    for (const record of records(model, "mapping_attribute")) {
      if (active(record, "attribute_mapping_status") && record.modeled_entity_type === "logical_entity") {
        const target = bindings.attributeTargets.get(attributeKey(record));
        if (target) dimensionalAttributes.add(target);
      }
    }
    for (const name of ["dimensional_entity", "dimensional_attribute"])
      for (const record of records(model, name))
        for (const source of record.sources || []) requireSource(source, name, dimensionalObjects,
          dimensionalAttributes, "Dimensional source requires an active Silver Logical contribution.");

    for (const name of ["mapping_dependency", "mapping_object", "mapping_attribute",
      "generated_code_source_system"])
      for (const record of records(model, name)) requireSystem(catalog, record.source_system_code,
        name, "source_system_code", issues);
    for (const name of ["validation_group", "validation_check"]) {
      for (const record of records(model, name)) {
        if (normalized(record.tenant_code) !== catalog.tenant) scopeIssue(issues, name, "tenant_code",
          "Validation record Tenant does not own this Model.");
        requireSystem(catalog, record.system_code, name, "system_code", issues);
        if (name === "validation_check" && record.is_active) {
          const query = validateReadSql(record.validation_query_sql);
          if (!query.valid) issue(issues,
            "validation_query_invalid", name, "validation_query_sql",
            "Validation query is not governed read-only Databricks SQL.");
          else if (record.validation_comparison_operator !== "executes_successfully" &&
              !query.finalReturnsRows) issue(issues, "validation_query_result_invalid", name,
            "validation_query_sql", "Validation query must end with a row-returning statement.");
          if (record.validation_comparison_query_sql !== null) {
            const comparison = validateReadSql(record.validation_comparison_query_sql);
            if (!comparison.valid) issue(issues, "validation_query_invalid", name,
              "validation_comparison_query_sql",
              "Validation comparison query is not governed read-only Databricks SQL.");
            else if (!comparison.finalReturnsRows) issue(issues,
              "validation_query_result_invalid", name, "validation_comparison_query_sql",
              "Validation query must end with a row-returning statement.");
          }
        }
      }
    }
    return issues;
  }

  function validateAssertionSource(source, layer, dataset, assertions, issues) {
    if (source.support_source_type !== "assertion") return;
    const assertion = assertions.get(normalized(
      source.assertion_record?.modeling_assertion_record_key));
    if (!assertion) issue(issues, "reference_not_found", dataset,
      "modeling_assertion_record_key", "Referenced record is not present in the future Model graph.");
    else if (!(assertion.modeling_assertion_applicable_layers || []).includes(layer)) issue(issues,
      "assertion_layer_invalid", dataset, "modeling_assertion_record_key",
      "Referenced Assertion does not apply to this modeling layer.");
  }

  function validateBackendReferences(model) {
    const issues = [];
    const documents = new Set(records(model, "modeling_assertion_document")
      .map((record) => normalized(record.modeling_assertion_document_name)));
    const assertions = new Map(records(model, "modeling_assertion_record")
      .map((record) => [normalized(record.modeling_assertion_record_key), record]));
    for (const record of records(model, "modeling_assertion_record"))
      if (!documents.has(normalized(record.modeling_assertion_document_name))) issue(issues,
        "reference_not_found", "modeling_assertion_record", "modeling_assertion_document_name",
        "Referenced record is not present in the future Model graph.");
    const conceptual = new Set(records(model, "conceptual_object")
      .map((record) => normalized(record.conceptual_object_name)));
    for (const record of records(model, "conceptual_object"))
      for (const source of record.supports || []) validateAssertionSource(source, "conceptual",
        "conceptual_object", assertions, issues);
    for (const record of records(model, "conceptual_relationship")) {
      if (!conceptual.has(normalized(record.from_conceptual_object_name)) ||
          !conceptual.has(normalized(record.to_conceptual_object_name))) issue(issues,
        "reference_not_found", "conceptual_relationship", "conceptual_object_name",
        "Referenced record is not present in the future Model graph.");
      for (const source of record.supports || []) validateAssertionSource(source, "conceptual",
        "conceptual_relationship", assertions, issues);
    }
    for (const layer of ["logical", "dimensional"]) {
      const submodels = new Set(records(model, `${layer}_submodel`)
        .map((record) => normalized(record[`${layer}_submodel_name`])));
      const entities = new Set(records(model, `${layer}_entity`)
        .map((record) => normalized(record[`${layer}_entity_name`])));
      const attributes = new Set(records(model, `${layer}_attribute`).map((record) =>
        tuple([record[`${layer}_entity_name`], record[`${layer}_attribute_name`]])));
      for (const record of records(model, `${layer}_entity`)) {
        if ((record.submodels || []).some((item) => !submodels.has(normalized(item.submodel_name))))
          issue(issues, "reference_not_found", `${layer}_entity`, "submodel_name",
            "Referenced record is not present in the future Model graph.");
        for (const source of record.sources || []) validateAssertionSource(source, layer,
          `${layer}_entity`, assertions, issues);
      }
      for (const record of records(model, `${layer}_attribute`)) {
        if (!entities.has(normalized(record[`${layer}_entity_name`]))) issue(issues,
          "reference_not_found", `${layer}_attribute`, `${layer}_entity_name`,
          "Referenced record is not present in the future Model graph.");
        for (const source of record.sources || []) validateAssertionSource(source, layer,
          `${layer}_attribute`, assertions, issues);
      }
      for (const record of records(model, `${layer}_relationship`)) {
        const endpoints = ["from", "to"].map((prefix) => tuple([
          record[`${prefix}_${layer}_entity_name`], record[`${prefix}_${layer}_attribute_name`],
        ]));
        if (endpoints.some((endpoint) => !attributes.has(endpoint))) issue(issues,
          "reference_not_found", `${layer}_relationship`, `${layer}_attribute_name`,
          "Referenced record is not present in the future Model graph.");
      }
    }
    const entities = new Set([
      ...records(model, "logical_entity").map(entityKey),
      ...records(model, "dimensional_entity").map(entityKey),
    ]);
    const attributes = new Set([
      ...records(model, "logical_attribute").map(attributeKey),
      ...records(model, "dimensional_attribute").map(attributeKey),
    ]);
    const objectBindings = new Set(records(model, "model_object_binding").map(entityKey));
    const attributeBindings = new Set(records(model, "model_attribute_binding").map(attributeKey));
    for (const record of records(model, "model_object_binding"))
      if (!entities.has(entityKey(record))) issue(issues, "reference_not_found",
        "model_object_binding", "modeled_entity_name",
        "Referenced record is not present in the future Model graph.");
    for (const record of records(model, "model_attribute_binding")) {
      if (!objectBindings.has(entityKey(record))) issue(issues, "reference_not_found",
        "model_attribute_binding", "model_object_binding",
        "Referenced record is not present in the future Model graph.");
      if (!attributes.has(attributeKey(record))) issue(issues, "reference_not_found",
        "model_attribute_binding", "modeled_attribute_name",
        "Referenced record is not present in the future Model graph.");
    }
    const dependencies = new Set(records(model, "mapping_dependency")
      .map((record) => tuple([record.modeled_entity_type, record.source_system_code])));
    const mappings = new Set(records(model, "mapping_object").map(mappingObjectKey));
    for (const record of records(model, "mapping_object")) {
      if (!objectBindings.has(entityKey(record))) issue(issues, "reference_not_found",
        "mapping_object", "model_object_binding",
        "Referenced record is not present in the future Model graph.");
      if (!dependencies.has(tuple([record.modeled_entity_type, record.source_system_code])))
        issue(issues, "reference_not_found", "mapping_object", "mapping_dependency",
          "Referenced record is not present in the future Model graph.");
    }
    for (const record of records(model, "mapping_attribute")) {
      if (!mappings.has(mappingObjectKey(record))) issue(issues, "reference_not_found",
        "mapping_attribute", "mapping_object",
        "Referenced record is not present in the future Model graph.");
      if (!attributeBindings.has(attributeKey(record))) issue(issues, "reference_not_found",
        "mapping_attribute", "model_attribute_binding",
        "Referenced record is not present in the future Model graph.");
    }
    const artifacts = new Set(records(model, "generated_code").map(artifactKey));
    for (const record of records(model, "generated_code"))
      if (!objectBindings.has(entityKey(record))) issue(issues, "reference_not_found",
        "generated_code", "model_object_binding",
        "Referenced record is not present in the future Model graph.");
    for (const record of records(model, "generated_code_source_system"))
      if (!artifacts.has(artifactKey(record))) issue(issues, "reference_not_found",
        "generated_code_source_system", "generated_code",
        "Referenced record is not present in the future Model graph.");
    const groups = new Set(records(model, "validation_group").map(validationGroupKey));
    for (const record of records(model, "validation_check"))
      if (!groups.has(validationGroupKey(record))) issue(issues, "reference_not_found",
        "validation_check", "validation_group_name",
        "Referenced record is not present in the future Model graph.");
    return issues;
  }

  function validateActiveDependencies(model) {
    const issues = [];
    const invalid = (dataset, field, message) => issue(issues,
      "active_dependency_invalid", dataset, field, message);
    const activeEntities = new Set([
      ...records(model, "logical_entity").filter((record) =>
        active(record, "logical_entity_status")).map(entityKey),
      ...records(model, "dimensional_entity").filter((record) =>
        active(record, "dimensional_entity_status")).map(entityKey),
    ]);
    const activeAttributes = new Set([
      ...records(model, "logical_attribute").filter((record) =>
        active(record, "logical_attribute_status")).map(attributeKey),
      ...records(model, "dimensional_attribute").filter((record) =>
        active(record, "dimensional_attribute_status")).map(attributeKey),
    ]);
    const objectBindings = new Set(records(model, "model_object_binding")
      .filter((record) => active(record, "model_object_binding_status")).map(entityKey));
    const attributeBindings = new Set(records(model, "model_attribute_binding")
      .filter((record) => active(record, "model_attribute_binding_status")).map(attributeKey));
    for (const entity of objectBindings) if (!activeEntities.has(entity)) invalid(
      "model_object_binding", "modeled_entity_name",
      "Active Object Binding requires an active modeled Entity.");
    for (const attribute of attributeBindings) {
      const entity = core.stableStringify(JSON.parse(attribute).slice(0, 2));
      if (!activeAttributes.has(attribute) || !objectBindings.has(entity)) invalid(
        "model_attribute_binding", "modeled_attribute_name",
        "Active Attribute Binding requires active modeled and Object bindings.");
    }
    const dependencies = new Set(records(model, "mapping_dependency")
      .filter((record) => active(record, "mapping_source_system_dependency_status"))
      .map((record) => tuple([record.modeled_entity_type, record.source_system_code])));
    const activeMappings = new Set();
    const mappingSystems = new Map();
    for (const record of records(model, "mapping_object")) {
      if (!active(record, "object_mapping_status")) continue;
      const entity = entityKey(record);
      const system = normalized(record.source_system_code);
      if (!objectBindings.has(entity) ||
          !dependencies.has(tuple([record.modeled_entity_type, record.source_system_code])) ||
          record.mapping_transformation_document === null) {
        invalid("mapping_object", "mapping_transformation_document",
          "Active Mapping Object requires active Binding, dependency, and transformation.");
        continue;
      }
      activeMappings.add(mappingObjectKey(record));
      if (!mappingSystems.has(entity)) mappingSystems.set(entity, new Set());
      mappingSystems.get(entity).add(system);
    }
    const activeMappingAttributes = new Set();
    for (const record of records(model, "mapping_attribute")) {
      if (!active(record, "attribute_mapping_status")) continue;
      if (!activeMappings.has(mappingObjectKey(record)) ||
          !attributeBindings.has(attributeKey(record)) ||
          record.attribute_mapping_transformation_document === null) {
        invalid("mapping_attribute", "model_attribute_binding",
          "Active Mapping Attribute requires active Mapping and Attribute Binding.");
        continue;
      }
      const [type, entity, attribute] = JSON.parse(attributeKey(record));
      activeMappingAttributes.add(tuple([type, entity, record.source_system_code, attribute]));
    }
    for (const [entity, systems] of mappingSystems) {
      const names = [...attributeBindings].filter((attribute) =>
        core.stableStringify(JSON.parse(attribute).slice(0, 2)) === entity)
        .map((attribute) => JSON.parse(attribute)[2]);
      for (const system of systems) if (names.some((name) =>
        !activeMappingAttributes.has(tuple([...JSON.parse(entity), system, name])))) invalid(
        "mapping_attribute", "modeled_attribute_name",
        "Active Mapping must cover every active bound target Attribute per System.");
    }
    const artifacts = new Map(records(model, "generated_code")
      .filter((record) => active(record, "generated_code_status"))
      .map((record) => [artifactKey(record), record]));
    const assignments = new Map();
    for (const record of artifacts.values()) if (!objectBindings.has(entityKey(record))) invalid(
      "generated_code", "model_object_binding",
      "Active Code artifact requires an active Object Binding.");
    for (const record of records(model, "generated_code_source_system")) {
      if (!active(record, "generated_code_source_system_status")) continue;
      const entity = entityKey(record);
      const system = normalized(record.source_system_code);
      if (!artifacts.has(artifactKey(record)) || !mappingSystems.get(entity)?.has(system)) {
        invalid("generated_code_source_system", "source_system_code",
          "Active Code source assignment requires active Code and Mapping.");
        continue;
      }
      const key = tuple([...JSON.parse(entity), system]);
      assignments.set(key, (assignments.get(key) || 0) + 1);
    }
    for (const [entity, systems] of mappingSystems) {
      if (![...artifacts.values()].some((record) => entityKey(record) === entity)) continue;
      for (const system of systems)
        if (assignments.get(tuple([...JSON.parse(entity), system])) !== 1) invalid(
          "generated_code_source_system", "source_system_code",
          "Each mapped source System must be assigned to exactly one active artifact.");
    }
    const groups = new Set(records(model, "validation_group")
      .filter((record) => record.is_active).map(validationGroupKey));
    const mappingSystemValues = new Set([...mappingSystems.values()].flatMap((value) => [...value]));
    for (const record of records(model, "validation_group"))
      if (record.is_active && !mappingSystemValues.has(normalized(record.system_code))) invalid(
        "validation_group", "system_code",
        "Active Validation Group requires active Mapping for its source System.");
    for (const record of records(model, "validation_check"))
      if (record.is_active && !groups.has(validationGroupKey(record))) invalid(
        "validation_check", "validation_group_name",
        "Active Validation Check requires an active Validation Group.");
    return issues;
  }

  function validateGraph(model, metadata = null, context = {}) {
    const issues = validateReferences(model, metadata);
    const completeGraph = model.has("model_details") && model.has("model_input_scope");
    if (!completeGraph) return issues;
    issues.push(...validateNestedLocks(model));
    const catalog = buildPhysicalCatalog(model, metadata, context);
    if (!catalog) issue(issues, "validation_context_missing", "model_input_scope", null,
      "A current Metadata Snapshot and Model Tenant are required for local Model validation.");
    else issues.push(...validatePhysicalScope(model, catalog));
    issues.push(...validateBackendReferences(model));
    issues.push(...validateActiveDependencies(model));
    return issues;
  }

  return {
    buildPhysicalCatalog,
    validateActiveDependencies,
    validateBackendReferences,
    validateGraph,
    validateNestedLocks,
    validatePhysicalScope,
    validateReferences,
    validateReadSql,
  };
});
