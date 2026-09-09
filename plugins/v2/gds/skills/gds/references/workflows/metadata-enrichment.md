# Metadata Enrichment

Use `metadata-enrichment`, a selected Model, and fresh Metadata **and** Model Snapshots. Stage only a Metadata Change Set through supported tools.

## Scope and preservation

Resolve Full/Selected inputs from active applied `model_input_scope` records. Require active Source/Bronze Objects, Connections, Systems and Zones. For each resolved `source_tenant_code`, use its authorized Metadata session for writes, including GDS-placed Objects. Use `../session.md` for separate owning-Tenant writes and shared Model scope evidence. Never infer scope from visibility or include Silver/Gold. Limit 200 Objects/5,000 Attributes.

Read compact `object` and `attribute` schemas. Copy complete Snapshot records, preserving other fields, unknown fields, natural keys and `attribute_data_type`. Ask once: overwrite existing unlocked descriptions or fill missing only. Reuse the saved choice. Apply supported text only to eligible fields; unsupported meaning leaves the field unchanged. Clearing a description requires an explicit request. Preserve `is_locked=false`: never add locks. Fill only null/blank `attribute_inferred_data_type`. Skip inactive/locked records; a locked/inactive Object protects its Attributes. Do not edit scope locks.

## Business meaning before descriptions

Inspect process, row grain, lifecycle and related Objects using descriptions, Profiles, Analysis, Assertions and ingestion lineage. Names suggest questions, not business facts. Resolve ambiguity with bounded counts/domain or relationship evidence under the saved SQL policy. Never sample masked fields. Leave unsupported meaning unchanged and report the gap. Technical failure preserves affected descriptions; report unavailable.

Describe each Object's row meaning and role, then its Attributes in that context. Include units, codes, roles and time semantics only with evidence. Reconcile related descriptions: an order's billed customer need not be its recipient. Use meaningful source comments; never invent acronym, status-code or identifier expansions.

## Type evidence

Inspect registered metadata first. For selected Source, use its own Attribute. For Bronze, resolve Source only through active `ingestion_attribute_mapping` and its active `ingestion_object_mapping`, matching complete source/target physical natural keys. Require the Source to have the same data owner. Mapping endpoint Tenant codes describe placement; compare resolved Objects' `source_tenant_code` for ownership. Never match names heuristically. Multiple distinct Source candidates are ambiguous: retain registered evidence and use Bronze evidence if possible.

Read current Source schema first when available; use `DESCRIBE TABLE <quoted-relation> <quoted-column>` for bounded per-Attribute type/comment evidence, including empty tables. Prefer its reliable non-string type. Only when Source schema is unavailable, use a reliable existing Source inferred type, then registered Source storage type. A current Source STRING/unsupported type must not revive an older registered numeric type: inspect bounded Source evidence, then Bronze schema/evidence. A conclusive Source sample, including STRING, wins over Bronze. If samples are inconclusive, retain a known current schema STRING; registered STRING alone remains inconclusive. Normalize known native aliases to Databricks types, preserving exact decimal precision/scale up to 38. Keep authoritative Databricks complex types only when their complete declaration fits 100 characters. Do not guess an unsupported native type.

Use `execute_databricks_sql` only under the session SQL policy, with at most 50 returned rows. Source relations require complete Connection `foreign_catalog`, Object `fc_object_schema`/`fc_object_name`, and Attribute `fc_attribute_name`; pass its active non-GDS source `connection_id`; the tool resolves GDS internally. Bronze uses its actual placement catalog/schema/Object/Attribute. Missing relation coordinates make remote evidence unavailable; registered metadata can still be used. Never connect directly to Source or substitute ordinary names for foreign-catalog coordinates.

Never sample an Attribute when it or its resolved Source requires masking. For string/uncertain types, use `references/examples/metadata-enrichment-type-evidence.sql`: replace only quoted relation/column identifiers from resolved metadata, escaping embedded backticks by doubling them. It inspects at most 50 values remotely and returns only inferred type and count. Null/blank-only observations remain inconclusive; leading-zero identifiers, mixed values, invalid ISO dates, and numbers exceeding exact precision stay STRING. Do not save raw samples, raw tool output, or prompts; retain only normalized type, method (`source_schema`, `registered_type`, `source_sample`, `bronze_schema`, or `bronze_sample`), and bounded count in task coverage.

## Complete the task

Descriptions must fit 2,000 UTF-8 bytes; types fit 100 characters. Do not emit an update for an unsupported description. Inconclusive type evidence and technical failures leave affected fields unchanged with an explicit coverage outcome.

Report added/replaced descriptions, filled inferred types, and existing-type, locked, inactive, changed, unavailable and inconclusive outcomes. Validate the effective Metadata graph. Recheck Model revision and fresh Metadata Snapshot before handoff; reassess changed evidence. Follow existing acknowledgement, Tenant Lock, Stage, server validation and Apply; locks remain strict. Refresh Metadata for downstream workflows.
