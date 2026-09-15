# Dimension history and lookup

Use when Dimensional Build, Mapping or Code needs changing-value or temporal behavior. [Dimensional records](../model/dimensional.md) owns accepted fields; [keys/audit](../model/keys-and-audit.md) owns shared columns. The user confirms Type 1 and Type 2 support and framework population of Type 2 fields using the natural keys. Select behavior from requirements and use the actual configured column names/types.

## Select behavior from analytical needs

Ask only when the existing model, requirements and user decisions do not resolve the answer. A useful question is: "After CustomerSegment changes, should earlier sales report the segment at sale time, the current segment, or support both?" That requirement determines the design; there is no global Type 2 default.

| Attribute change behavior | Meaning / required decision |
|---|---|
| `fixed` | Preserve the original value under the agreed business rule; determine how exceptional corrections are handled. |
| `overwrite` | Replace the stored value; that Attribute no longer preserves its former value in the same row. Clarify whether corrections affect prior version rows as well. |
| `historize` | Preserve changing values through a defined history design. The flag alone does not specify effective dates, version matching or the load implementation. |
| `null` | No applicable declared change behavior; not an implicit overwrite or proof that historical needs were considered. |

Decide at meaningful Attribute granularity. One dimension may overwrite corrected spelling and retain segment history. Reuse confirmed policy; do not make every Attribute historical or ask the same question for technical/audit fields whose population is already defined.

## If row versions are required

Type 2 commonly assigns a distinct surrogate to each version and adds validity boundaries plus a current-row marker. Retain a stable business identity so versions can be related. See [Kimball Type 2](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/type-2/).

Before completing the affected design, resolve:

- Which Attributes create a version versus overwrite a correction; how duplicates, unchanged inputs and repeated loads are recognized.
- Effective-time source, timezone, boundary convention and open-ended representation; avoid overlapping intervals for one business member.
- Whether a fact resolves the current version or the version valid at its business event time. The complete business-key/time predicate must select exactly one eligible version, or follow the confirmed missing-member policy; handle validity gaps as well as overlaps. Late facts cannot automatically use today's version.
- How late/missing members, unknown versus not-applicable values, corrections and backdated changes are handled. Do not invent a sentinel key, discard a fact or substitute an arbitrary current row.
- The technical columns' actual names/types/nullability. The framework supplies the Type 2 fields; use the configured contract without inventing placeholder values.

These are decision criteria, not a mandatory interview checklist or new payload fields. Put concise rules in existing Entity/Attribute definitions, relationship basis and source rationale; preserve the full executable decision for later Mapping. Use an Assertion only for a reusable attributable rule that benefits from one.

## Technical columns and framework boundary

History columns are additional modeled Attributes, separate from the confirmed audit block. Do not repurpose `IsActive`, `CreatedDate` or `UpdatedDate` as version markers without an explicit consumer contract. A technical Attribute is not automatically a framework-generated or SQL-omitted field.

Current backend `features/dimensional/policy.py` can project configured effective-from, effective-to and current-marker columns when a dimension has an active nontechnical `historize` Attribute. That creates model columns; the external framework populates them at load time using natural keys. Surrogate placement and fact/bridge coverage still need the alignment recorded in [keys/audit](../model/keys-and-audit.md#population-boundary-and-implementation-alignment).

The existing GDS seed template defines the following. Resolve the actual Model configuration before use; seed values do not prove deployment or override a supplied framework convention.

| Purpose | Seed name | Type / nullability |
|---|---|---|
| Version start | `EffectiveFrom` | TIMESTAMP, non-null. |
| Version end | `EffectiveTo` | TIMESTAMP, nullable; seed definition uses null for the current version. |
| Current-version marker | `IsCurrent` | BOOLEAN, non-null. |

`IsActive` remains in the shared audit block. Its presence is not sufficient reason to substitute it for `IsCurrent`. The Type 2 field names above come from `database/seed/04_application_reference.sql`; actual clock and boundary behavior must agree with the consumer.

Retain these history Attributes in the Model, target metadata, DDL and Binding. In each applicable Attribute Mapping, state "Framework-populated Type 2 field; omitted from transformation SQL." Do not invent source lineage, timestamp/boolean expressions or SQL that maintains these values. This adds the configured Type 2 fields to the own-surrogate/nine-audit exclusions; other technical fields still follow their explicit population rule.

Preserve the complete natural/business-key tuple, including source namespace where required, through Model, target metadata and Mapping. Transformation SQL supplies the mapped business-key values; the generated surrogate is not a substitute for the framework's natural-key matching. Explain current-member identity separately from version identity: repeating a natural key across historical versions is intentional. Framework-owned version maintenance does not decide a fact's current-versus-event-time dimension lookup; that analytical rule still belongs in Mapping.

If a particular history requirement exceeds the confirmed consumer behavior, keep that requirement and execution gap explicit. Continue independent modeling work; do not silently flatten history, claim load readiness or invent a second executable artifact. Do not re-ask the settled Type 1/Type 2 capability or history-field population questions.

Source for current projection: `web_app/backend/gds_workbench_api/features/dimensional/policy.py`; storage fields: `mcp_server/gds_etl_workbench/domain/modeling_records.py`. Both are development provenance, not packaged runtime dependencies.
