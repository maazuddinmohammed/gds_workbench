# Mapping inner-document examples

Fictional preconditions: applied Binding targets `CustomerSourceRecord`, with STRING columns `SourceSystemCode`, `CustomerCode`, `CustomerName`, followed by BIGINT `SourceSystemID`; source columns are STRING. Confirmed grain: source System/customer code. Evidence establishes unique, non-null, nonblank codes with significant formatting. Optional names trim surrounding spaces, converting blanks to null. ERP/CRM remain separate records; customer unification requires evidenced identity/reconciliation rules.

Illustrative Bronze placement: `GDS` Tenant/System, connection `DEMO_GDS`. Ownership `source_tenant_code=DEMO` and Mapping lineage `source_system_code=ERP` differ from physical keys. Obtain actual keys, SQL relations, Attributes and policies from evidence. These are **inner documents**; describe each dataset before constructing its outer Change Set record.

Unless a custom template was selected, established default installation permits outer Object `output_template_code="mapping_object_default"` and Attribute `output_template_code="mapping_attribute_default"`. Otherwise use these inner shapes with `output_template_code=null`; never invent installed codes or seed that database. Preserve the outer record schema.

Store this ERP object document in `mapping_transformation_document`:

```json
{
  "source_objects": [
    {
      "tenant_code": "GDS",
      "system_code": "GDS",
      "connection_code": "DEMO_GDS",
      "object_schema": "bronze",
      "object_name": "erp_customer",
      "alias": "c"
    }
  ],
  "steps": [
    "Read every row from the resolved relation bronze.erp_customer as c once. No joins, filters, aggregation or deduplication are required.",
    "Project the SQL-populated columns through SourceSystemID in order using their Attribute transformations. Source codes are unique, non-null and nonblank; preserve CustomerCode unchanged.",
    "Use (SourceSystemCode, CustomerCode) as the confirmed output grain and runtime merge key. ERP and CRM branches have disjoint composite keys. No predecessor target is required; runtime performs the merge."
  ]
}
```

Store these in corresponding `attribute_mapping_transformation_document` fields. Alias `c` resolves through the ERP Object above. Registered Attribute names here equal Bronze SQL columns. For Source Objects, resolve differing `fc_attribute_name`; retain registered `attribute_name` lineage.

`CustomerCode` — direct value and business-key lineage:

```json
{
  "source_attributes": [
    {
      "tenant_code": "GDS",
      "system_code": "GDS",
      "connection_code": "DEMO_GDS",
      "object_schema": "bronze",
      "object_name": "erp_customer",
      "attribute_name": "customer_code"
    }
  ],
  "transformation": "Return c.customer_code as STRING unchanged. Preserve leading zeros, case and whitespace. Source and target disallow null; source evidence establishes nonblank values. No cast, normalization or default."
}
```

`CustomerName` — derived value:

```json
{
  "source_attributes": [
    {
      "tenant_code": "GDS",
      "system_code": "GDS",
      "connection_code": "DEMO_GDS",
      "object_schema": "bronze",
      "object_name": "erp_customer",
      "attribute_name": "customer_name"
    }
  ],
  "transformation": "Return NULLIF(TRIM(c.customer_name), '') as STRING. Null input stays null; blank input becomes null. Target permits null. No fallback to prior target values."
}
```

`SourceSystemCode` — confirmed constant with no source column:

```json
{
  "source_attributes": null,
  "transformation": "Return the STRING literal 'ERP' for every row, from the confirmed source-lineage policy. Never null. This combines with CustomerCode to identify a source record."
}
```

`SourceSystemID` uses the registered Bronze `source_system_id`, cast to BIGINT under the confirmed conversion policy. Include its full Attribute lineage in the actual Mapping. The own surrogate and framework audit fields are accounted for as database/framework-generated, with no SELECT expression. See `../orchestration-rules.md`.

For the Object template, `source_objects` and `steps` are required keys whose values may be JSON null. For the Attribute template, `source_attributes` may be omitted or null; `transformation` remains required. A generated Attribute may describe its confirmed identity/generation rule instead of an invented SQL expression.

Read/preserve or author `mapping_dependency` separately per layer/System; Object text cannot replace it. Resolve conflicting preconditions instead of copying examples. `multi-system-target.sql` adds an equivalent CRM branch.
