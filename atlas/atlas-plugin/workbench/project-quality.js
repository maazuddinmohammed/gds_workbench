(function (root, factory) {
  "use strict";
  const core = typeof module === "object" && module.exports ? require("./core.js") : root.GDSCore;
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSProjectQuality = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  const OBJECT_FIELDS = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"];
  const ATTRIBUTE_FIELDS = [...OBJECT_FIELDS, "attribute_name"];
  const COUNTS = ["source_non_null", "source_distinct", "target_non_null", "target_distinct",
    "source_missing_target", "unused_target", "duplicate_target_key"];
  const normalize = (value) => core.normalize("project", "value", value);
  const tuple = (values) => core.stableStringify(values.map(normalize));
  const physical = (record, attribute = false, prefix = "") => tuple(
    (attribute ? ATTRIBUTE_FIELDS : OBJECT_FIELDS).map((field) => record?.[`${prefix}${field}`]));
  const active = (record) => core.active(record) === true;
  const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const exactFields = (value, fields) => object(value) &&
    Object.keys(value).length === fields.length && fields.every((field) => Object.hasOwn(value, field));
  const prose = (value) => typeof value === "string" && value.trim().length > 0 && value.length <= 8000;

  function invalidProjectInput(dataset) {
    return { required: true, status: "needs_evidence", errors: [{ code: "project_quality_input_invalid", dataset, key: null,
      message: "Fix structural validation errors before reviewing quality: modeling records need complete, nonblank canonical keys and valid record arrays." }],
      warnings: [], error_count: 1, warning_count: 0, truncated: false, metrics: {},
      template: { schema_version: "1.0", entities: [], relationships: [] }, note_paths: [] };
  }

  function evaluateQuality(projectMap, decisions, { noteFiles = new Map(), metadataMap = null } = {}) {
    if (!(projectMap instanceof Map)) return invalidProjectInput("project");
    const errors = [], warnings = [], notes = new Set(), rows = new Map(), indexes = new Map(), changes = new Map();
    const issue = (list, code, dataset, key, message) => list.push({ code, dataset, key, message });
    const keyObject = (dataset, record) => Object.fromEntries(projectMap.get(dataset).definition.canonical_key
      .map((field) => [field, record[field]]));
    const key = (dataset, record) => core.stableStringify(core.key("project", projectMap.get(dataset).definition, record));
    const rowList = (dataset) => rows.get(dataset) || [];
    const relevantDatasets = new Set(["logical_entity", "logical_attribute", "logical_relationship",
      "analysis_result", "context_record", "context_group", "project_input_scope", "subject_area", "subject_area_table"]);
    for (const [dataset, state] of projectMap) {
      if (!relevantDatasets.has(dataset)) continue;
      const fields = state?.definition?.canonical_key;
      if (!Array.isArray(fields) || !fields.length || fields.some((field) => typeof field !== "string") ||
          [state?.baseline, state?.pending, state?.effective].some((records) => records !== undefined &&
            (!Array.isArray(records) || records.some((record) => !object(record) || fields.some((field) =>
              typeof record[field] !== "string" || !record[field].trim()) ||
              (record.sources !== undefined &&
                (!Array.isArray(record.sources) || record.sources.some((source) => !object(source)))))))) return invalidProjectInput(dataset);
      const effective = state.effective || state.baseline || [];
      rows.set(dataset, effective);
      if (!state.definition?.canonical_key) continue;
      const baseline = new Map((state.baseline || []).map((record) => [key(dataset, record), record]));
      indexes.set(dataset, new Map(effective.map((record) => [key(dataset, record), record])));
      changes.set(dataset, (state.pending || []).filter((record) =>
        core.stableStringify(baseline.get(key(dataset, record))) !== core.stableStringify(record)));
    }
    for (const analysis of rowList("analysis_result").filter(active)) {
      if (!["one_to_one", "one_to_many", "many_to_one", "many_to_many"].includes(analysis.inferred_cardinality)) continue;
      const counts = COUNTS.map((name) => analysis[`validation_${name}_count`]);
      const [sourceCount, sourceDistinct, targetCount, targetDistinct, missing, unused, duplicates] = counts;
      if (!/^\d+\.\d+\.\d+$/.test(analysis.validation_policy_version || "") ||
          !counts.every((count) => Number.isSafeInteger(count) && count >= 0) ||
          sourceCount <= 0 || targetCount <= 0 || sourceDistinct <= 0 || targetDistinct <= 0 ||
          sourceDistinct > sourceCount || targetDistinct > targetCount || missing > sourceDistinct || unused > targetDistinct ||
          sourceDistinct - missing !== targetDistinct - unused || duplicates !== targetCount - targetDistinct ||
          analysis.validation_result !== (missing === 0 && duplicates === 0 ? "supported" : "unsupported")) continue;
      const observed = `${sourceCount > sourceDistinct ? "many" : "one"}_to_${targetCount > targetDistinct ? "many" : "one"}`;
      if (analysis.inferred_cardinality !== observed) issue(warnings, "analysis_inferred_cardinality_mismatch", "analysis_result",
        keyObject("analysis_result", analysis), "Inferred cardinality differs from measured endpoint uniqueness. Review population scope and grain; preserve both conclusions.");
    }
    const logicalIdentity = (record, prefix = "") => tuple([record?.[`${prefix}logical_entity_schema_name`], record?.[`${prefix}logical_entity_name`]]);
    const entities = rowList("logical_entity").filter(active);
    const attributes = rowList("logical_attribute").filter(active);
    const logical = rowList("logical_relationship").filter(active);
    const entityNames = new Map(entities.map((record) => [logicalIdentity(record), record]));
    const attributesByEntity = new Map(entities.map((record) => [logicalIdentity(record), []]));
    const attributeIndex = new Map();
    for (const record of attributes) {
      attributesByEntity.get(logicalIdentity(record))?.push(record);
      attributeIndex.set(tuple([record.logical_entity_schema_name, record.logical_entity_name, record.logical_attribute_name]), record);
    }
    const entityAttributes = (record, prefix = "") => attributesByEntity.get(logicalIdentity(record, prefix)) || [];
    const supports = (record) => new Set((record?.sources || [])
      .filter((source) => active(source) && source.support_source_type === "object")
      .map((source) => physical(source.source_object)));
    const lineage = (attribute) => new Set((attribute?.sources || [])
      .filter((source) => active(source) && source.support_source_type === "attribute")
      .map((source) => physical(source.source_attribute, true)));
    const endpointLineage = (relationship, endpoint) => {
      const entity = relationship[`${endpoint}_logical_entity_name`];
      const attribute = attributeIndex.get(tuple([relationship[`${endpoint}_logical_entity_schema_name`], entity, relationship[`${endpoint}_logical_attribute_name`]]));
      if (attribute?.logical_attribute_is_surrogate_key) {
        return new Set(entityAttributes(relationship, `${endpoint}_`).filter((item) => item.logical_attribute_is_natural_key)
          .flatMap((item) => [...lineage(item)]));
      }
      return lineage(attribute);
    };
    const analysisAlignment = (relationship, analysis) => {
      const from = endpointLineage(relationship, "from"), to = endpointLineage(relationship, "to");
      const source = physical(analysis, true, "from_"), target = physical(analysis, true, "to_");
      if (from.has(source) && to.has(target)) return "forward";
      if (from.has(target) && to.has(source)) return "reverse";
      return null;
    };

    const affected = { logical_entity: new Set(), logical_relationship: new Set() };
    const affectRelationship = (record) => {
      affected.logical_relationship.add(key("logical_relationship", record));
      for (const endpoint of ["from", "to"]) affected.logical_entity.add(logicalIdentity(record, `${endpoint}_`));
    };
    for (const dataset of ["logical_entity", "logical_attribute"]) for (const record of changes.get(dataset) || [])
      affected.logical_entity.add(logicalIdentity(record));
    for (const record of changes.get("logical_relationship") || []) affectRelationship(record);
    const changedEvidence = new Set(["analysis_result", "context_record", "context_group"]
      .flatMap((dataset) => (changes.get(dataset) || []).map((record) => `${dataset}:${key(dataset, record)}`)));
    const referencesChanged = (entry) => (Array.isArray(entry?.evidence) ? entry.evidence : []).some((ref) => {
      if (!indexes.has(ref?.dataset) || !object(ref.key)) return false;
      try {
        if (changedEvidence.has(`${ref.dataset}:${key(ref.dataset, ref.key)}`)) return true;
        const context = indexes.get(ref.dataset).get(key(ref.dataset, ref.key));
        return ref.dataset === "context_record" && context && changedEvidence.has(
          `context_group:${key("context_group", context)}`);
      } catch { return false; }
    });
    const affectedEntitySeeds = new Set(affected.logical_entity);
    for (const record of logical) {
      const cited = Array.isArray(decisions?.relationships) && decisions.relationships.find((entry) => {
        try { return entry.dataset === "logical_relationship" && key("logical_relationship", entry.key) === key("logical_relationship", record); }
        catch { return false; }
      });
      if (["from", "to"].some((endpoint) => affectedEntitySeeds.has(logicalIdentity(record, `${endpoint}_`))) ||
          (changes.get("analysis_result") || []).some((analysis) => analysisAlignment(record, analysis)) ||
          referencesChanged(cited)) affectRelationship(record);
    }
    for (const entry of Array.isArray(decisions?.entities) ? decisions.entities : []) {
      if (entry?.dataset === "logical_entity" && referencesChanged(entry)) affected.logical_entity.add(logicalIdentity(entry.key));
    }
    const template = { schema_version: "1.0", entities: [], relationships: [] };
    for (const record of entities) {
      if (!affected.logical_entity.has(logicalIdentity(record))) continue;
      template.entities.push({ dataset: "logical_entity", key: keyObject("logical_entity", record),
        identity_attributes: entityAttributes(record).filter((attribute) => attribute.logical_attribute_is_natural_key)
          .map((attribute) => attribute.logical_attribute_name),
        identity_mode: entityAttributes(record).some((attribute) => attribute.logical_attribute_is_natural_key) ? "natural" : "append_only",
        decision: "", evidence: [] });
    }
    for (const record of logical) if (affected.logical_relationship.has(key("logical_relationship", record)))
      template.relationships.push({ dataset: "logical_relationship", key: keyObject("logical_relationship", record), evidence: [], decision: "" });
    const required = template.entities.length > 0 || template.relationships.length > 0;

    const adjacency = new Map(entities.map((record) => [logicalIdentity(record), new Set()]));
    let selfEdges = 0, crossEdges = 0;
    for (const relationship of logical) {
      const from = logicalIdentity(relationship, "from_"), to = logicalIdentity(relationship, "to_");
      if (from === to) selfEdges += 1;
      else {
        crossEdges += 1;
        adjacency.get(from)?.add(to);
        adjacency.get(to)?.add(from);
      }
    }
    const components = [], visited = new Set();
    for (const name of adjacency.keys()) {
      if (visited.has(name)) continue;
      const component = [], queue = [name];
      while (queue.length) {
        const next = queue.pop();
        if (visited.has(next) || !adjacency.has(next)) continue;
        visited.add(next);
        const member = entityNames.get(next);
        component.push(`${member.logical_entity_schema_name}.${member.logical_entity_name}`);
        for (const neighbor of adjacency.get(next)) queue.push(neighbor);
      }
      components.push(component.sort());
    }
    const business = attributes.filter((record) => !record.logical_attribute_is_audit_column && !record.logical_attribute_is_surrogate_key);
    const singleSource = business.filter((record) => lineage(record).size === 1).length;
    const singleObject = entities.filter((record) => supports(record).size === 1).length;
    const logicalSourceObjects = new Set(entities.flatMap((record) => [...supports(record)]));
    const isolatedEntities = entities.filter((record) => adjacency.get(logicalIdentity(record)).size === 0)
      .map((record) => `${record.logical_entity_schema_name}.${record.logical_entity_name}`);
    const entitiesWithoutNaturalKey = entities.filter((record) => !entityAttributes(record)
      .some((attribute) => attribute.logical_attribute_is_natural_key)).map((record) => `${record.logical_entity_schema_name}.${record.logical_entity_name}`);
    const componentExamples = [];
    let remainingComponentNames = 200;
    for (const component of components) {
      if (!remainingComponentNames) break;
      const example = component.slice(0, remainingComponentNames);
      componentExamples.push(example);
      remainingComponentNames -= example.length;
    }
    const metadataAttributes = new Map(), bronzeObjects = new Set();
    if (metadataMap instanceof Map) for (const state of metadataMap.values())
      for (const record of state.effective || state.baseline || []) {
        if (record.attribute_name && record.attribute_inferred_data_type) metadataAttributes.set(physical(record, true), record);
        else if (!record.attribute_name && normalize(record.zone_code) === "bronze") bronzeObjects.add(physical(record));
      }
    // Subject Areas are optional focus windows over Input Scope Objects, never modeling evidence.
    // Once a Project has an active area, an active Bronze Input Scope Object outside every active
    // area is unassigned. Builds work one area at a time, so each area also reports how many of its
    // Objects are shared with another area and already support an active Logical Entity.
    const subjectAreas = rowList("subject_area").filter(active);
    const areaNames = new Set(subjectAreas.map((record) => normalize(record.subject_area_name)));
    const memberships = rowList("subject_area_table").filter((record) => active(record) && areaNames.has(normalize(record.subject_area_name)));
    const assignedTables = new Set(memberships.map((record) => physical(record)));
    const areaObjects = new Map(subjectAreas.map((record) => [normalize(record.subject_area_name), new Set()]));
    for (const record of memberships) areaObjects.get(normalize(record.subject_area_name)).add(physical(record));
    const objectAreas = new Map();
    for (const objects of areaObjects.values()) for (const object of objects) objectAreas.set(object, (objectAreas.get(object) || 0) + 1);
    const unassignedTables = !subjectAreas.length ? [] : rowList("project_input_scope").filter((record) =>
      active(record) && bronzeObjects.has(physical(record)) && !assignedTables.has(physical(record)));
    const emptyAreas = subjectAreas.filter((record) => !areaObjects.get(normalize(record.subject_area_name)).size);
    // Same default order as the web Build dialog: most shared Objects first, then larger areas, then name.
    const areaSummaries = subjectAreas.map((record) => {
      const objects = [...areaObjects.get(normalize(record.subject_area_name))];
      return { subject_area_name: record.subject_area_name, object_count: objects.length,
        shared_object_count: objects.filter((object) => objectAreas.get(object) > 1).length,
        modeled_object_count: objects.filter((object) => logicalSourceObjects.has(object)).length };
    }).sort((left, right) => right.shared_object_count - left.shared_object_count || right.object_count - left.object_count ||
      core.compareCodePoints(normalize(left.subject_area_name), normalize(right.subject_area_name)));
    const metrics = {
      logical_entities: entities.length,
      logical_relationships: logical.length, cross_entity_relationships: crossEdges, self_relationships: selfEdges,
      connected_components: components.length, components: componentExamples,
      isolated_entity_count: isolatedEntities.length, isolated_entities: isolatedEntities.slice(0, 200),
      logical_physical_support_objects: logicalSourceObjects.size, single_object_entities: singleObject,
      entity_source_support_ratio: { numerator: singleObject, denominator: entities.length },
      business_attributes: business.length, single_source_business_attributes: singleSource,
      single_source_attribute_ratio: { numerator: singleSource, denominator: business.length },
      audit_attributes: attributes.filter((record) => record.logical_attribute_is_audit_column).length,
      surrogate_attributes: attributes.filter((record) => record.logical_attribute_is_surrogate_key).length,
      framework_attributes: attributes.filter((record) => record.logical_attribute_is_audit_column || record.logical_attribute_is_surrogate_key).length,
      active_attributes: attributes.length,
      entities_without_natural_key_count: entitiesWithoutNaturalKey.length,
      entities_without_natural_key: entitiesWithoutNaturalKey.slice(0, 200),
      subject_areas: subjectAreas.length,
      unassigned_table_count: unassignedTables.length,
      unassigned_tables: unassignedTables.slice(0, 200).map((record) => keyObject("project_input_scope", record)),
      empty_subject_area_count: emptyAreas.length,
      empty_subject_areas: emptyAreas.slice(0, 200).map((record) => record.subject_area_name),
      subject_area_summaries: areaSummaries.slice(0, 200),
      metric_examples_truncated: entities.length > 200 || isolatedEntities.length > 200 || entitiesWithoutNaturalKey.length > 200 ||
        unassignedTables.length > 200 || emptyAreas.length > 200 || areaSummaries.length > 200,
    };
    if (entities.length && singleObject === entities.length && singleSource === business.length)
      issue(warnings, "source_shaped_project", "logical_entity", null,
        "All Entities have one physical Object support and all business Attributes have one physical source. Review grain and dependencies; this does not prove copying or require splitting.");
    if (metrics.isolated_entities.length) issue(warnings, "isolated_entities", "logical_entity", null,
      "Some Entities have no cross-entity relationship. Ask the user whether they are intentionally standalone or a supported relationship is missing; do not invent joins.");
    if (metrics.connected_components > 1) issue(warnings, "disconnected_components", "logical_entity", null,
      "Logical Entities form separate connected groups. Ask the user whether these groups are intentionally separate or evidence supports a relationship between them; do not invent joins.");
    if (unassignedTables.length) issue(warnings, "unassigned_tables", "subject_area_table", null,
      "Some active Bronze Input Scope Objects are in no active Subject Area. Place each one in an area or report why it stays unassigned.");
    if (emptyAreas.length) issue(warnings, "empty_subject_areas", "subject_area", null,
      "Some active Subject Areas have no active Object. Add their Objects or retire the empty areas.");
    for (const attribute of business) {
      const decimal = /^DECIMAL\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)$/i.exec(attribute.logical_attribute_data_type || "");
      if (decimal && Number(decimal[1]) === Number(decimal[2])) issue(warnings, "decimal_zero_integer_capacity", "logical_attribute",
        keyObject("logical_attribute", attribute), "DECIMAL precision equals scale; values of 1 or greater cannot fit. Confirm business capacity.");
      if ([...lineage(attribute)].some((source) => metadataAttributes.has(source) &&
          normalize(metadataAttributes.get(source).attribute_inferred_data_type) !== normalize(attribute.logical_attribute_data_type)))
        issue(warnings, "type_divergence", "logical_attribute", keyObject("logical_attribute", attribute),
          "The modeled type differs from current inferred Metadata. Review conversion evidence; divergence can be intentional.");
    }
    const hasDecisions = decisions !== null && decisions !== undefined;
    if (required && !hasDecisions) issue(warnings, "decision_review_required", "project", null,
      "Review modeled definitions, identity and relationship basis against the available evidence. A separate decision file is optional.");
    if (required && hasDecisions) {
      if (!exactFields(decisions, ["schema_version", "entities", "relationships"]) || decisions.schema_version !== "1.0" ||
          !Array.isArray(decisions.entities) || !Array.isArray(decisions.relationships)) {
        issue(errors, "decisions_missing_or_invalid", "project", null,
          "Provide schema_version 1.0 and the two entity/relationship decision arrays; metrics and pass flags are computed.");
      }
      const found = new Map();
      for (const section of ["entities", "relationships"]) for (const entry of Array.isArray(decisions?.[section]) ? decisions[section] : []) {
        const allowed = section === "entities" ? "logical_entity" : "logical_relationship";
        const dataset = entry?.dataset;
        const fields = ["dataset", "key", "decision", "evidence", ...(dataset === "logical_entity" ? ["identity_attributes", "identity_mode"] : [])];
        if (dataset !== allowed || !exactFields(entry, fields) || !indexes.has(dataset) ||
            !exactFields(entry.key, projectMap.get(dataset).definition.canonical_key)) {
          issue(errors, "decision_invalid", dataset || "project", entry?.key || null, "Decision fields or canonical key are invalid.");
          continue;
        }
        const identity = `${dataset}:${key(dataset, entry.key)}`;
        const record = indexes.get(dataset).get(key(dataset, entry.key));
        if (found.has(identity)) issue(errors, "decision_duplicate", dataset, entry.key, "Provide one decision for this canonical key.");
        found.set(identity, entry);
        if (!record || !active(record)) {
          issue(errors, "decision_unknown", dataset, entry.key, "Decision does not identify an active effective record.");
          continue;
        }
        if (!prose(entry.decision)) issue(errors, "decision_missing", dataset, entry.key,
          "Explain the identity/dependency decision in 1 to 8000 characters; its presence does not prove correctness.");
        if (!Array.isArray(entry.evidence) || !entry.evidence.length) issue(errors, "evidence_missing", dataset, entry.key, "Cite existing evidence for this decision.");
        let contextEvidence = false, noteEvidence = false, compositeAnalysis = false;
        const evidenceSeen = new Set();
        for (const reference of Array.isArray(entry.evidence) ? entry.evidence : []) {
          const referenceIdentity = core.stableStringify(reference);
          if (evidenceSeen.has(referenceIdentity)) issue(errors, "evidence_duplicate", dataset, entry.key, "Duplicate evidence reference.");
          evidenceSeen.add(referenceIdentity);
          if (exactFields(reference, ["note"])) {
            const name = reference.note;
            if (typeof name !== "string" || !name.endsWith(".md") || name.startsWith("/") || name.includes("\\") ||
                name.includes(":") || name.startsWith(".atlas/temp/") || /[\u0000-\u001f\u007f]/.test(name) || name.split("/").some((part) => !part || part === "." || part === ".."))
              issue(errors, "note_invalid", dataset, entry.key, "Evidence note must be a session-relative Markdown path.");
            else {
              notes.add(name);
              noteEvidence = noteFiles instanceof Map ? noteFiles.has(name) : object(noteFiles) && Object.hasOwn(noteFiles, name);
              if (section === "relationships") issue(warnings, "relationship_inferred", dataset, entry.key, "Relationship decision cites a retained business/metadata inference note, not SQL measurement.");
              if (!(noteFiles instanceof Map ? noteFiles.has(name) : object(noteFiles) && Object.hasOwn(noteFiles, name)))
                issue(errors, "note_missing", dataset, entry.key, "Referenced sanitized evidence note is missing.");
            }
            continue;
          }
          if (!exactFields(reference, ["dataset", "key"]) || !["analysis_result", "context_record"].includes(reference.dataset) ||
              !indexes.has(reference.dataset) || !exactFields(reference.key, projectMap.get(reference.dataset).definition.canonical_key)) {
            issue(errors, "evidence_invalid", dataset, entry.key, "Use an existing Analysis/Context canonical key or a retained inference note.");
            continue;
          }
          const evidence = indexes.get(reference.dataset).get(key(reference.dataset, reference.key));
          if (!evidence || !active(evidence)) {
            issue(errors, "evidence_inactive_or_missing", dataset, entry.key, "Evidence must identify an active effective record.");
            continue;
          }
          if (reference.dataset === "context_record") {
            const document = rowList("context_group").find((item) => normalize(item.context_group_name) === normalize(evidence.context_group_name));
            if (!active(document || {}))
              issue(errors, "context_not_applicable", dataset, entry.key, "Context requires an active group.");
            else contextEvidence = true;
          } else {
            const counts = COUNTS.map((name) => evidence[`validation_${name}_count`]);
            const [sourceCount, sourceDistinct, targetCount, targetDistinct, missing, unused, duplicates] = counts;
            const supported = /^\d+\.\d+\.\d+$/.test(evidence.validation_policy_version || "") &&
              evidence.validation_result === "supported" && counts.every((count) => Number.isSafeInteger(count) && count >= 0) &&
              sourceCount > 0 && targetCount > 0 && sourceDistinct > 0 && targetDistinct > 0 &&
              sourceDistinct <= sourceCount && targetDistinct <= targetCount && missing <= sourceCount && unused <= targetCount &&
              duplicates === 0 && targetCount === targetDistinct && missing === 0 &&
              sourceDistinct <= targetDistinct && unused === targetDistinct - sourceDistinct;
            const measured = counts.some(count => count !== null && count !== undefined) || evidence.validation_result != null || evidence.validation_policy_version != null;
            if (measured && !supported) issue(errors, "analysis_not_supported", dataset, entry.key,
              "Cited measured Analysis is incomplete or contradicts a supported reference. Retain valid measurements; do not describe them as inference.");
            if (!measured) issue(warnings, "analysis_inferred", dataset, entry.key,
              "Relationship relies on documented metadata/business inference; SQL measurements were not required or claimed.");
            if (section === "relationships" && !analysisAlignment(record, evidence)) issue(errors, "analysis_endpoint_mismatch", dataset, entry.key,
              "Analysis endpoints do not match the relationship's physical lineage.");
            if (section === "relationships" && supported) {
              compositeAnalysis = ["from", "to"].some((endpoint) => {
                const name = record[`${endpoint}_logical_entity_name`];
                const endpointAttribute = attributeIndex.get(tuple([record[`${endpoint}_logical_entity_schema_name`], name, record[`${endpoint}_logical_attribute_name`]]));
                return endpointAttribute?.logical_attribute_is_surrogate_key && entityAttributes(record, `${endpoint}_`)
                  .filter((attribute) => attribute.logical_attribute_is_natural_key).length > 1;
              });
              // Child -> parent: the Analysis must run from the child's foreign key to the parent's key.
              const cardinality = record.logical_relationship_cardinality;
              const forward = analysisAlignment(record, evidence) === "forward";
              if (!(forward && (cardinality === "many_to_one" || (cardinality === "one_to_one" && sourceCount === sourceDistinct))))
                issue(errors, "analysis_cardinality_mismatch", dataset, entry.key, "Declared cardinality is not supported by the cited directional uniqueness evidence.");
            }
          }
        }
        if (compositeAnalysis && !contextEvidence && !noteEvidence) issue(errors, "analysis_composite_identity", dataset, entry.key,
          "Individual-Attribute Analysis cannot prove lookup of a composite natural identity. Cite an applicable business Context or retained business decision note for the complete lookup; do not treat component counts as tuple proof.");
        if (dataset === "logical_entity") {
          const natural = entityAttributes(record).filter((attribute) => attribute.logical_attribute_is_natural_key)
            .map((attribute) => normalize(attribute.logical_attribute_name)).sort();
          const declared = Array.isArray(entry.identity_attributes) && entry.identity_attributes.every((name) => typeof name === "string" && name.trim())
            ? entry.identity_attributes.map(normalize).sort() : null;
          if (!declared || new Set(declared).size !== declared.length || core.stableStringify(declared) !== core.stableStringify(natural))
            issue(errors, "identity_attributes_mismatch", dataset, entry.key, "Identity must name the complete tuple of actual active natural-key Attributes.");
          if (natural.length && entry.identity_mode !== "natural") issue(errors, "identity_mode_invalid", dataset, entry.key, "An Entity with natural keys must use natural identity mode.");
          if (!natural.length) {
            if (entry.identity_mode !== "append_only" || (!contextEvidence && !noteEvidence)) issue(errors, "identity_evidence_missing", dataset, entry.key,
              "Without natural identity, append-only treatment requires an applicable active business Context or retained business decision note.");
            else issue(warnings, "append_only_identity", dataset, entry.key, "Append-only identity relies on documented business evidence; the generated surrogate does not establish deduplication.");
          }
        }
      }
      for (const section of ["entities", "relationships"]) for (const entry of template[section])
        if (!found.has(`${entry.dataset}:${key(entry.dataset, entry.key)}`)) issue(errors, "decision_missing", entry.dataset, entry.key,
          "The affected active record needs a current evidence-backed decision.");
    }
    return { required, status: !required ? "not_required" : errors.length ? "needs_evidence" : !hasDecisions ? "review_required" : "evidence_present",
      errors: errors.slice(0, 200), warnings: warnings.slice(0, 200),
      error_count: errors.length, warning_count: warnings.length, truncated: errors.length > 200 || warnings.length > 200,
      metrics, template, note_paths: [...notes].sort() };
  }

  return { evaluateQuality };
});
