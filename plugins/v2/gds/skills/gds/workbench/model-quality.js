(function (root, factory) {
  "use strict";
  const core = typeof module === "object" && module.exports ? require("./core.js") : root.GDSCore;
  const api = factory(core);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSModelQuality = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";

  const OBJECT_FIELDS = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"];
  const ATTRIBUTE_FIELDS = [...OBJECT_FIELDS, "attribute_name"];
  const ENTITY_DATASETS = ["conceptual_object", "logical_entity"];
  const RELATIONSHIP_DATASETS = ["conceptual_relationship", "logical_relationship"];
  const COUNTS = ["source_non_null", "source_distinct", "target_non_null", "target_distinct",
    "source_missing_target", "unused_target", "duplicate_target_key"];
  const normalize = (value) => core.normalize("model", "value", value);
  const tuple = (values) => core.stableStringify(values.map(normalize));
  const physical = (record, attribute = false, prefix = "") => tuple(
    (attribute ? ATTRIBUTE_FIELDS : OBJECT_FIELDS).map((field) => record?.[`${prefix}${field}`]));
  const active = (record) => core.active(record) === true;
  const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const exactFields = (value, fields) => object(value) &&
    Object.keys(value).length === fields.length && fields.every((field) => Object.hasOwn(value, field));
  const prose = (value) => typeof value === "string" && value.trim().length > 0 && value.length <= 8000;

  function invalidModelInput(dataset) {
    return { required: true, status: "needs_evidence", errors: [{ code: "model_quality_input_invalid", dataset, key: null,
      message: "Fix structural validation errors before reviewing quality: modeling records need complete, nonblank canonical keys and valid record arrays." }],
      warnings: [], error_count: 1, warning_count: 0, truncated: false, metrics: {},
      template: { schema_version: "1.0", entities: [], relationships: [] }, note_paths: [] };
  }

  function evaluateQuality(modelMap, decisions, { noteFiles = new Map(), metadataMap = null } = {}) {
    if (!(modelMap instanceof Map)) return invalidModelInput("model");
    const errors = [], warnings = [], notes = new Set(), rows = new Map(), indexes = new Map(), changes = new Map();
    const issue = (list, code, dataset, key, message) => list.push({ code, dataset, key, message });
    const keyObject = (dataset, record) => Object.fromEntries(modelMap.get(dataset).definition.canonical_key
      .map((field) => [field, record[field]]));
    const key = (dataset, record) => core.stableStringify(core.key("model", modelMap.get(dataset).definition, record));
    const rowList = (dataset) => rows.get(dataset) || [];
    const relevantDatasets = new Set([...ENTITY_DATASETS, ...RELATIONSHIP_DATASETS, "logical_attribute",
      "analysis_result", "modeling_assertion_record", "modeling_assertion_document"]);
    for (const [dataset, state] of modelMap) {
      if (!relevantDatasets.has(dataset)) continue;
      const fields = state?.definition?.canonical_key;
      if (!Array.isArray(fields) || !fields.length || fields.some((field) => typeof field !== "string") ||
          [state?.baseline, state?.pending, state?.effective].some((records) => records !== undefined &&
            (!Array.isArray(records) || records.some((record) => !object(record) || fields.some((field) =>
              typeof record[field] !== "string" || !record[field].trim()) ||
              ["sources", "supports"].some((field) => record[field] !== undefined &&
                (!Array.isArray(record[field]) || record[field].some((source) => !object(source)))) ||
              (record.modeling_assertion_applicable_layers !== undefined &&
                !Array.isArray(record.modeling_assertion_applicable_layers)))))) return invalidModelInput(dataset);
      const effective = state.effective || state.baseline || [];
      rows.set(dataset, effective);
      if (!state.definition?.canonical_key) continue;
      const baseline = new Map((state.baseline || []).map((record) => [key(dataset, record), record]));
      indexes.set(dataset, new Map(effective.map((record) => [key(dataset, record), record])));
      changes.set(dataset, (state.pending || []).filter((record) =>
        core.stableStringify(baseline.get(key(dataset, record))) !== core.stableStringify(record)));
    }
    const entities = rowList("logical_entity").filter(active);
    const concepts = rowList("conceptual_object").filter(active);
    const attributes = rowList("logical_attribute").filter(active);
    const logical = rowList("logical_relationship").filter(active);
    const conceptual = rowList("conceptual_relationship").filter(active);
    const entityNames = new Map(entities.map((record) => [normalize(record.logical_entity_name), record]));
    const conceptNames = new Map(concepts.map((record) => [normalize(record.conceptual_object_name), record]));
    const attributesByEntity = new Map(entities.map((record) => [normalize(record.logical_entity_name), []]));
    const attributeIndex = new Map();
    for (const record of attributes) {
      attributesByEntity.get(normalize(record.logical_entity_name))?.push(record);
      attributeIndex.set(tuple([record.logical_entity_name, record.logical_attribute_name]), record);
    }
    const entityAttributes = (name) => attributesByEntity.get(normalize(name)) || [];
    const supports = (record) => new Set((record?.sources || record?.supports || [])
      .filter((source) => active(source) && source.support_source_type === "object")
      .map((source) => physical(source.source_object)));
    const lineage = (attribute) => new Set((attribute?.sources || [])
      .filter((source) => active(source) && source.support_source_type === "attribute")
      .map((source) => physical(source.source_attribute, true)));
    const endpointLineage = (relationship, endpoint) => {
      const entity = relationship[`${endpoint}_logical_entity_name`];
      const attribute = attributeIndex.get(tuple([entity, relationship[`${endpoint}_logical_attribute_name`]]));
      if (attribute?.logical_attribute_is_surrogate_key) {
        return new Set(entityAttributes(entity).filter((item) => item.logical_attribute_is_natural_key)
          .flatMap((item) => [...lineage(item)]));
      }
      return lineage(attribute);
    };
    const analysisAlignment = (dataset, relationship, analysis) => {
      const from = dataset === "logical_relationship" ? endpointLineage(relationship, "from")
        : supports(conceptNames.get(normalize(relationship.from_conceptual_object_name)));
      const to = dataset === "logical_relationship" ? endpointLineage(relationship, "to")
        : supports(conceptNames.get(normalize(relationship.to_conceptual_object_name)));
      const source = physical(analysis, dataset === "logical_relationship", "from_");
      const target = physical(analysis, dataset === "logical_relationship", "to_");
      if (from.has(source) && to.has(target)) return "forward";
      if (from.has(target) && to.has(source)) return "reverse";
      return null;
    };

    const affected = { conceptual_object: new Set(), logical_entity: new Set(),
      conceptual_relationship: new Set(), logical_relationship: new Set() };
    const affectRelationship = (dataset, record) => {
      affected[dataset].add(key(dataset, record));
      const conceptualLayer = dataset === "conceptual_relationship";
      const entityDataset = conceptualLayer ? "conceptual_object" : "logical_entity";
      const field = conceptualLayer ? "conceptual_object_name" : "logical_entity_name";
      for (const endpoint of ["from", "to"]) affected[entityDataset].add(normalize(record[`${endpoint}_${field}`]));
    };
    for (const dataset of ENTITY_DATASETS) for (const record of changes.get(dataset) || [])
      affected[dataset].add(normalize(record[dataset === "logical_entity" ? "logical_entity_name" : "conceptual_object_name"]));
    for (const record of changes.get("logical_attribute") || [])
      affected.logical_entity.add(normalize(record.logical_entity_name));
    for (const dataset of RELATIONSHIP_DATASETS) for (const record of changes.get(dataset) || [])
      affectRelationship(dataset, record);
    const changedEvidence = new Set(["analysis_result", "modeling_assertion_record", "modeling_assertion_document"]
      .flatMap((dataset) => (changes.get(dataset) || []).map((record) => `${dataset}:${key(dataset, record)}`)));
    const referencesChanged = (entry) => (Array.isArray(entry?.evidence) ? entry.evidence : []).some((ref) => {
      if (!indexes.has(ref?.dataset) || !object(ref.key)) return false;
      try {
        if (changedEvidence.has(`${ref.dataset}:${key(ref.dataset, ref.key)}`)) return true;
        const assertion = indexes.get(ref.dataset).get(key(ref.dataset, ref.key));
        return ref.dataset === "modeling_assertion_record" && assertion && changedEvidence.has(
          `modeling_assertion_document:${key("modeling_assertion_document", assertion)}`);
      } catch { return false; }
    });
    const affectedEntitySeeds = { conceptual_object: new Set(affected.conceptual_object), logical_entity: new Set(affected.logical_entity) };
    for (const dataset of RELATIONSHIP_DATASETS) for (const record of rowList(dataset).filter(active)) {
      const entityDataset = dataset === "logical_relationship" ? "logical_entity" : "conceptual_object";
      const field = dataset === "logical_relationship" ? "logical_entity_name" : "conceptual_object_name";
      const cited = Array.isArray(decisions?.relationships) && decisions.relationships.find((entry) => {
        try { return entry.dataset === dataset && key(dataset, entry.key) === key(dataset, record); }
        catch { return false; }
      });
      if (["from", "to"].some((endpoint) => affectedEntitySeeds[entityDataset].has(normalize(record[`${endpoint}_${field}`]))) ||
          (changes.get("analysis_result") || []).some((analysis) => analysisAlignment(dataset, record, analysis)) ||
          referencesChanged(cited)) affectRelationship(dataset, record);
    }
    for (const entry of Array.isArray(decisions?.entities) ? decisions.entities : []) {
      if (ENTITY_DATASETS.includes(entry?.dataset) && referencesChanged(entry)) {
        const field = entry.dataset === "logical_entity" ? "logical_entity_name" : "conceptual_object_name";
        affected[entry.dataset].add(normalize(entry.key?.[field]));
      }
    }
    const template = { schema_version: "1.0", entities: [], relationships: [] };
    for (const dataset of ENTITY_DATASETS) for (const record of rowList(dataset).filter(active)) {
      const name = record[dataset === "logical_entity" ? "logical_entity_name" : "conceptual_object_name"];
      if (!affected[dataset].has(normalize(name))) continue;
      template.entities.push({ dataset, key: keyObject(dataset, record), ...(dataset === "logical_entity" ? {
        identity_attributes: entityAttributes(name).filter((attribute) => attribute.logical_attribute_is_natural_key)
          .map((attribute) => attribute.logical_attribute_name),
        identity_mode: entityAttributes(name).some((attribute) => attribute.logical_attribute_is_natural_key) ? "natural" : "append_only",
      } : {}), decision: "", evidence: [] });
    }
    for (const dataset of RELATIONSHIP_DATASETS) for (const record of rowList(dataset).filter(active))
      if (affected[dataset].has(key(dataset, record))) template.relationships.push({
        dataset, key: keyObject(dataset, record), evidence: [], decision: "",
      });
    const required = template.entities.length > 0 || template.relationships.length > 0;

    const adjacency = new Map(entities.map((record) => [normalize(record.logical_entity_name), new Set()]));
    let selfEdges = 0, crossEdges = 0;
    for (const relationship of logical) {
      const from = normalize(relationship.from_logical_entity_name), to = normalize(relationship.to_logical_entity_name);
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
        component.push(entityNames.get(next).logical_entity_name);
        for (const neighbor of adjacency.get(next)) queue.push(neighbor);
      }
      components.push(component.sort());
    }
    const business = attributes.filter((record) => !record.logical_attribute_is_audit_column && !record.logical_attribute_is_surrogate_key);
    const singleSource = business.filter((record) => lineage(record).size === 1).length;
    const singleObject = entities.filter((record) => supports(record).size === 1).length;
    const sourceObjects = new Set([...entities, ...concepts].flatMap((record) => [...supports(record)]));
    const isolatedEntities = entities.filter((record) => adjacency.get(normalize(record.logical_entity_name)).size === 0)
      .map((record) => record.logical_entity_name);
    const entitiesWithoutNaturalKey = entities.filter((record) => !entityAttributes(record.logical_entity_name)
      .some((attribute) => attribute.logical_attribute_is_natural_key)).map((record) => record.logical_entity_name);
    const componentExamples = [];
    let remainingComponentNames = 200;
    for (const component of components) {
      if (!remainingComponentNames) break;
      const example = component.slice(0, remainingComponentNames);
      componentExamples.push(example);
      remainingComponentNames -= example.length;
    }
    const metrics = {
      conceptual_objects: concepts.length, logical_entities: entities.length,
      logical_relationships: logical.length, cross_entity_relationships: crossEdges, self_relationships: selfEdges,
      connected_components: components.length, components: componentExamples,
      isolated_entity_count: isolatedEntities.length, isolated_entities: isolatedEntities.slice(0, 200),
      physical_support_objects: sourceObjects.size, single_object_entities: singleObject,
      entity_source_support_ratio: { numerator: singleObject, denominator: entities.length },
      business_attributes: business.length, single_source_business_attributes: singleSource,
      single_source_attribute_ratio: { numerator: singleSource, denominator: business.length },
      audit_attributes: attributes.filter((record) => record.logical_attribute_is_audit_column).length,
      surrogate_attributes: attributes.filter((record) => record.logical_attribute_is_surrogate_key).length,
      framework_attributes: attributes.filter((record) => record.logical_attribute_is_audit_column || record.logical_attribute_is_surrogate_key).length,
      active_attributes: attributes.length,
      entities_without_natural_key_count: entitiesWithoutNaturalKey.length,
      entities_without_natural_key: entitiesWithoutNaturalKey.slice(0, 200),
      metric_examples_truncated: entities.length > 200 || isolatedEntities.length > 200 || entitiesWithoutNaturalKey.length > 200,
    };
    if (entities.length && singleObject === entities.length && singleSource === business.length)
      issue(warnings, "source_shaped_model", "logical_entity", null,
        "All Entities have one physical Object support and all business Attributes have one physical source. Review grain and dependencies; this does not prove copying or require splitting.");
    if (metrics.isolated_entities.length) issue(warnings, "isolated_entities", "logical_entity", null,
      "Some Entities have no cross-entity relationship. Review missing evidence; isolated reference Entities can be intentional.");
    const metadataAttributes = new Map();
    if (metadataMap instanceof Map) for (const state of metadataMap.values())
      for (const record of state.effective || state.baseline || [])
        if (record.attribute_name && record.attribute_inferred_data_type) metadataAttributes.set(physical(record, true), record);
    for (const attribute of business) {
      const decimal = /^DECIMAL\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)$/i.exec(attribute.logical_attribute_data_type || "");
      if (decimal && Number(decimal[1]) === Number(decimal[2])) issue(warnings, "decimal_zero_integer_capacity", "logical_attribute",
        keyObject("logical_attribute", attribute), "DECIMAL precision equals scale; values of 1 or greater cannot fit. Confirm business capacity.");
      if ([...lineage(attribute)].some((source) => metadataAttributes.has(source) &&
          normalize(metadataAttributes.get(source).attribute_inferred_data_type) !== normalize(attribute.logical_attribute_data_type)))
        issue(warnings, "type_divergence", "logical_attribute", keyObject("logical_attribute", attribute),
          "The modeled type differs from current inferred Metadata. Review conversion evidence; divergence can be intentional.");
    }
    for (const relationship of conceptual) {
      const from = supports(conceptNames.get(normalize(relationship.from_conceptual_object_name)));
      const to = supports(conceptNames.get(normalize(relationship.to_conceptual_object_name)));
      if (!from.size || !to.size) continue;
      const hasEdge = logical.some((edge) => [
        [edge.from_logical_entity_name, edge.to_logical_entity_name],
        [edge.to_logical_entity_name, edge.from_logical_entity_name],
      ].some(([left, right]) => [...supports(entityNames.get(normalize(left)))].some((source) => from.has(source)) &&
        [...supports(entityNames.get(normalize(right)))].some((source) => to.has(source))));
      if (!hasEdge) issue(warnings, "possible_missing_logical_relationship", "conceptual_relationship", keyObject("conceptual_relationship", relationship),
        "Support-overlap heuristic found no Logical counterpart. Confirm whether this business relationship is implemented, deferred or rejected.");
    }

    if (required) {
      if (!exactFields(decisions, ["schema_version", "entities", "relationships"]) || decisions.schema_version !== "1.0" ||
          !Array.isArray(decisions.entities) || !Array.isArray(decisions.relationships)) {
        issue(errors, "decisions_missing_or_invalid", "model", null,
          "Provide schema_version 1.0 and the two entity/relationship decision arrays; metrics and pass flags are computed.");
      }
      const found = new Map();
      for (const section of ["entities", "relationships"]) for (const entry of Array.isArray(decisions?.[section]) ? decisions[section] : []) {
        const allowed = section === "entities" ? ENTITY_DATASETS : RELATIONSHIP_DATASETS;
        const dataset = entry?.dataset;
        const fields = ["dataset", "key", "decision", "evidence", ...(dataset === "logical_entity" ? ["identity_attributes", "identity_mode"] : [])];
        if (!allowed.includes(dataset) || !exactFields(entry, fields) || !indexes.has(dataset) ||
            !exactFields(entry.key, modelMap.get(dataset).definition.canonical_key)) {
          issue(errors, "decision_invalid", dataset || "model", entry?.key || null, "Decision fields or canonical key are invalid.");
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
        let assertionEvidence = false, compositeAnalysis = false, conceptualCardinalityMismatch = false;
        const evidenceSeen = new Set();
        for (const reference of Array.isArray(entry.evidence) ? entry.evidence : []) {
          const referenceIdentity = core.stableStringify(reference);
          if (evidenceSeen.has(referenceIdentity)) issue(errors, "evidence_duplicate", dataset, entry.key, "Duplicate evidence reference.");
          evidenceSeen.add(referenceIdentity);
          if (exactFields(reference, ["note"]) && section === "entities") {
            const name = reference.note;
            if (typeof name !== "string" || !name.endsWith(".md") || name.startsWith("/") || name.includes("\\") ||
                name.includes(":") || /[\u0000-\u001f\u007f]/.test(name) || name.split("/").some((part) => !part || part === "." || part === ".."))
              issue(errors, "note_invalid", dataset, entry.key, "Evidence note must be a session-relative Markdown path.");
            else {
              notes.add(name);
              if (!(noteFiles instanceof Map ? noteFiles.has(name) : object(noteFiles) && Object.hasOwn(noteFiles, name)))
                issue(errors, "note_missing", dataset, entry.key, "Referenced sanitized evidence note is missing.");
            }
            continue;
          }
          if (!exactFields(reference, ["dataset", "key"]) || !["analysis_result", "modeling_assertion_record"].includes(reference.dataset) ||
              !indexes.has(reference.dataset) || !exactFields(reference.key, modelMap.get(reference.dataset).definition.canonical_key)) {
            issue(errors, "evidence_invalid", dataset, entry.key, "Use an existing Analysis/Assertion canonical key; notes are allowed only for Entity decisions.");
            continue;
          }
          const evidence = indexes.get(reference.dataset).get(key(reference.dataset, reference.key));
          if (!evidence || !active(evidence)) {
            issue(errors, "evidence_inactive_or_missing", dataset, entry.key, "Evidence must identify an active effective record.");
            continue;
          }
          if (reference.dataset === "modeling_assertion_record") {
            const layer = dataset.startsWith("logical") ? "logical" : "conceptual";
            const document = rowList("modeling_assertion_document").find((item) => normalize(item.modeling_assertion_document_name) === normalize(evidence.modeling_assertion_document_name));
            if (!active(document || {}) || !Array.isArray(evidence.modeling_assertion_applicable_layers) ||
                !evidence.modeling_assertion_applicable_layers.includes(layer))
              issue(errors, "assertion_not_applicable", dataset, entry.key, "Assertion requires an active document and the applicable modeling layer.");
            else assertionEvidence = true;
          } else {
            const counts = COUNTS.map((name) => evidence[`validation_${name}_count`]);
            const [sourceCount, sourceDistinct, targetCount, targetDistinct, missing, unused, duplicates] = counts;
            const supported = /^\d+\.\d+\.\d+$/.test(evidence.validation_policy_version || "") &&
              evidence.validation_result === "supported" && counts.every((count) => Number.isSafeInteger(count) && count >= 0) &&
              sourceCount > 0 && targetCount > 0 && sourceDistinct > 0 && targetDistinct > 0 &&
              sourceDistinct <= sourceCount && targetDistinct <= targetCount && missing <= sourceCount && unused <= targetCount &&
              duplicates === 0 && targetCount === targetDistinct && missing === 0 &&
              sourceDistinct <= targetDistinct && unused === targetDistinct - sourceDistinct;
            if (!supported) issue(errors, "analysis_not_supported", dataset, entry.key,
              "Analysis must contain a complete supported deterministic result with consistent counts, nonempty domains, no orphan values and unique target keys.");
            if (section === "relationships" && !analysisAlignment(dataset, record, evidence)) issue(errors, "analysis_endpoint_mismatch", dataset, entry.key,
              "Analysis endpoints do not match the relationship's physical lineage or supported Conceptual Objects.");
            if (section === "relationships" && supported) {
              if (dataset === "logical_relationship") compositeAnalysis = ["from", "to"].some((endpoint) => {
                const name = record[`${endpoint}_logical_entity_name`];
                const endpointAttribute = attributeIndex.get(tuple([name, record[`${endpoint}_logical_attribute_name`]]));
                return endpointAttribute?.logical_attribute_is_surrogate_key && entityAttributes(name)
                  .filter((attribute) => attribute.logical_attribute_is_natural_key).length > 1;
              });
              const cardinality = record[`${dataset}_cardinality`];
              const alignment = analysisAlignment(dataset, record, evidence);
              if (!((dataset === "conceptual_relationship" && cardinality === "unknown") ||
                  (cardinality === "many_to_one" && alignment === "forward") ||
                  (cardinality === "one_to_many" && alignment === "reverse") ||
                  (cardinality === "one_to_one" && alignment && sourceCount === sourceDistinct))) {
                if (dataset === "conceptual_relationship") conceptualCardinalityMismatch = true;
                else issue(errors, "analysis_cardinality_mismatch", dataset, entry.key, "Declared cardinality is not supported by the cited directional uniqueness evidence.");
              }
            }
          }
        }
        if (conceptualCardinalityMismatch && !assertionEvidence) issue(errors, "analysis_cardinality_mismatch", dataset, entry.key,
          "Known Conceptual cardinality is not supported by the cited directional uniqueness evidence. A different business grain requires an applicable business Assertion; otherwise retain unknown cardinality.");
        if (compositeAnalysis && !assertionEvidence) issue(errors, "analysis_composite_identity", dataset, entry.key,
          "Individual-Attribute Analysis cannot prove lookup of a composite natural identity. Cite an applicable business Assertion for the complete lookup; do not treat component counts as tuple proof.");
        if (dataset === "logical_entity") {
          const natural = entityAttributes(record.logical_entity_name).filter((attribute) => attribute.logical_attribute_is_natural_key)
            .map((attribute) => normalize(attribute.logical_attribute_name)).sort();
          const declared = Array.isArray(entry.identity_attributes) && entry.identity_attributes.every((name) => typeof name === "string" && name.trim())
            ? entry.identity_attributes.map(normalize).sort() : null;
          if (!declared || new Set(declared).size !== declared.length || core.stableStringify(declared) !== core.stableStringify(natural))
            issue(errors, "identity_attributes_mismatch", dataset, entry.key, "Identity must name the complete tuple of actual active natural-key Attributes.");
          if (natural.length && entry.identity_mode !== "natural") issue(errors, "identity_mode_invalid", dataset, entry.key, "An Entity with natural keys must use natural identity mode.");
          if (!natural.length) {
            if (entry.identity_mode !== "append_only" || !assertionEvidence) issue(errors, "identity_evidence_missing", dataset, entry.key,
              "Without natural identity, append-only treatment requires an applicable active business Assertion.");
            else issue(warnings, "append_only_identity", dataset, entry.key, "Append-only identity relies on documented business evidence; the generated surrogate does not establish deduplication.");
          }
        }
      }
      for (const section of ["entities", "relationships"]) for (const entry of template[section])
        if (!found.has(`${entry.dataset}:${key(entry.dataset, entry.key)}`)) issue(errors, "decision_missing", entry.dataset, entry.key,
          "The affected active record needs a current evidence-backed decision.");
    }
    return { required, status: !required ? "not_required" : errors.length ? "needs_evidence" : "evidence_present",
      errors: errors.slice(0, 200), warnings: warnings.slice(0, 200),
      error_count: errors.length, warning_count: warnings.length, truncated: errors.length > 200 || warnings.length > 200,
      metrics, template, note_paths: [...notes].sort() };
  }

  return { evaluateQuality };
});
