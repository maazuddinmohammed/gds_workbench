# Metadata Enrichment

Use `metadata-enrichment`, a selected Model, fresh Metadata/Model Snapshots and a separate Metadata Change Set.

## Scope and preservation

Resolve Full/Selected from active applied `model_input_scope`; require active Source/Bronze Objects, Connections, Systems and Zones. Never infer scope from visibility or include Silver/Gold. Limit 200 Objects/5,000 Attributes. Write through each `source_tenant_code`'s authorized Metadata session, including GDS-placed Objects; follow `../session.md` for ownership and combined context.

Read compact `object`/`attribute` schemas. Copy complete records, preserving unknown fields, natural keys and physical `attribute_data_type`. Reuse or ask once: overwrite unlocked descriptions or fill missing. Unsupported meaning leaves descriptions unchanged; clearing requires an explicit request. Fill only blank/null `attribute_inferred_data_type`. Skip locked/inactive records; locked/inactive Objects protect Attributes. Never add locks or edit scope locks.

## Meaning before descriptions

Investigate process, row grain, lifecycle and related Objects using Profiles, Analysis, Assertions, source comments and ingestion lineage. Names suggest questions, not facts. Resolve ambiguity through bounded domain/relationship evidence under saved SQL policy; technical failures leave affected descriptions unchanged.

Describe Object row meaning and role, then Attributes in that context. Distinguish adjacent concepts: billed customer versus recipient. “Amount charged for this line, before tax, in the order currency” requires evidence for grain, tax and currency. “Amount value for Amount” adds nothing. Keep ambiguous price meanings unresolved; never invent acronym, status-code or identifier expansions. Cite sanitized findings in object-analysis notes before downstream modeling.

## Type evidence

For Source, inspect its own Attribute. For Bronze, resolve Source only through active `ingestion_attribute_mapping` and `ingestion_object_mapping`, matching complete endpoint natural keys. Compare resolved Objects' `source_tenant_code` for ownership; endpoint Tenant codes describe placement. Never infer lineage by names. Multiple Source candidates are ambiguous: retain registered evidence and investigate Bronze when possible.

Prefer current Source schema, including empty tables: `DESCRIBE TABLE <quoted-relation> <quoted-column>` returns bounded type/comment evidence. Use reliable non-string types. Only when current schema is unavailable, prefer reliable Source inferred type, then registered storage type. Current STRING/unsupported schema must not revive stale numeric declarations: investigate bounded Source evidence, then Bronze schema/evidence. Conclusive Source samples, including STRING, outrank Bronze. Inconclusive samples preserve known current-schema STRING; registered STRING alone stays inconclusive.

Normalize known native aliases to Databricks types; preserve authoritative decimal precision/scale up to 38. Keep authoritative complex types only if the full declaration fits 100 characters. Never guess unsupported native types.

`execute_databricks_sql` follows saved policy and returns at most 50 rows. Source needs Connection `foreign_catalog`, Object `fc_object_schema`/`fc_object_name`, Attribute `fc_attribute_name`, and its active non-GDS source `connection_id`; the tool routes GDS execution. Bronze uses actual placement catalog/schema/Object/Attribute. Missing coordinates prevent remote investigation, not use of registered evidence. Never connect directly to Source or substitute ordinary names.

Never sample an Attribute masked locally or at its resolved Source. For uncertain/string types, use `references/examples/metadata-enrichment-type-evidence.sql`; substitute only resolved quoted identifiers, doubling embedded backticks. It samples at most 50 values remotely, returning type/count only. Sample DECIMAL(38, observed scale) is provisional: neither scale nor 38 digits establishes production capacity. Preserve declared precision; Logical must independently assess units, range and cast failures. Null/blank-only remains inconclusive; leading-zero identifiers, mixed values, invalid ISO dates and excessive precision remain STRING.

Retain sanitized notes and normalized type, method (`source_schema`, `registered_type`, `source_sample`, `bronze_schema`, `bronze_sample`) and bounded count. Never save samples, raw output or prompts.

## Finish

Descriptions fit 2,000 UTF-8 bytes; types fit 100 characters. Report updated, unchanged, locked/inactive, unavailable and inconclusive outcomes. Validate effective Metadata, recheck scope Model revision/freshness, then follow acknowledgement, Tenant Lock, Stage, server validation and Apply. Refresh Metadata before dependent work.
