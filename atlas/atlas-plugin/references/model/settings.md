# Model settings through Change Sets

Use this guide for a requested policy/settings change. Read the effective `model_details` record, edit a complete local proposal, and use the existing [Change Set lifecycle](../change-set-lifecycle.md). No direct settings-save operation exists in the plugin.

- Preserve `model_name` exactly. It is Model identity, never a rename operation.
- `model_description` is an ordinary Change Set field; never call a UI save endpoint.
- `logical_schemas` / `dimensional_schemas`: arrays of `{"schema_name":"silver","description":"Normalized entities."}`. Description may be null. Names are nonblank (maximum 400 characters), unique ignoring case/surrounding spaces; maximum 100 schemas per layer. Do not remove schemas still used by retained entities.
- `silver_model_naming_instructions` / `gold_model_naming_instructions`: nonblank text or null; maximum 32,768 UTF-8 bytes. Null selects defaults.
- `logical_entity_scd_type` / `dimensional_entity_scd_type`: `"type_1"`, `"type_2"`, or null (unspecified). They are independent. Review affected design/history and downstream Mapping; changing a setting does not backfill or silently rebuild saved entities.
- `default_mapping_source_system_code`: active registered System code, e.g. `"ERP"`, or null to clear the default. The backend resolves its ID. This default is not evidence that a System supplies a particular target.
- Templates below are JSON objects or null. Maximum 262,144 JSON bytes each. No unknown properties. Read exact schemas through `describe_model_dataset` / the installed Model Snapshot.

Web-agent provider/model/SDK/reasoning/turn/retry defaults, Model identity, Input Scope and lock administration are outside plugin authoring.

## Logical and Dimensional audit templates

`silver_model_audit_columns_template` and `gold_model_audit_columns_template` share the same format. `schema_version` accepts only `"1.0"` (omission defaults to it). `columns` is required, ordered, and has at most 32 entries. Every entry requires:

| Field | Accepted value |
|---|---|
| `semantic_name` | Nonblank string, maximum 255 characters; names unique ignoring case and surrounding spaces. |
| `data_type` | Nonblank string, maximum 100 characters. |
| `nullable` | JSON boolean, not a string. |
| `definition` | Nonblank string up to 2,000 characters, or explicit null. |

Null selects these shared defaults. An explicit `{"schema_version":"1.0","columns":[]}` disables audit columns. A supplied array replaces the default array; it does not append to it.

```json
{
  "schema_version": "1.0",
  "columns": [
    {
      "semantic_name": "SourceSystemID",
      "data_type": "BIGINT",
      "nullable": true,
      "definition": "Originating source System identifier."
    },
    {
      "semantic_name": "IsDataValid",
      "data_type": "BOOLEAN",
      "nullable": true,
      "definition": "Framework data validation flag."
    },
    {
      "semantic_name": "HashKey",
      "data_type": "STRING",
      "nullable": true,
      "definition": "Framework change-detection hash."
    },
    {
      "semantic_name": "IsActive",
      "data_type": "BOOLEAN",
      "nullable": true,
      "definition": "Framework active-record flag."
    },
    {
      "semantic_name": "GDSBatchID",
      "data_type": "BIGINT",
      "nullable": true,
      "definition": "Framework batch identifier."
    },
    {
      "semantic_name": "PipelineRunID",
      "data_type": "STRING",
      "nullable": true,
      "definition": "Framework pipeline run identifier."
    },
    {
      "semantic_name": "CreatedDate",
      "data_type": "TIMESTAMP",
      "nullable": true,
      "definition": "Framework record creation time."
    },
    {
      "semantic_name": "UpdatedDate",
      "data_type": "TIMESTAMP",
      "nullable": true,
      "definition": "Framework record update time."
    },
    {
      "semantic_name": "CreatedBy",
      "data_type": "STRING",
      "nullable": true,
      "definition": "Framework record creator."
    },
    {
      "semantic_name": "UpdatedBy",
      "data_type": "STRING",
      "nullable": true,
      "definition": "Framework record updater."
    }
  ]
}
```

## Existing Dimensional technical template

`gold_model_technical_columns_template` uses the complete structure below. Null selects these defaults. Unknown/missing required fields fail validation. `schema_version` accepts `"1.0"` and defaults to it when omitted.

Names/templates are nonblank, at most 255 characters; types at most 100; definitions at most 2,000. All three `type_2` entries use the audit-column structure above. Their names must differ; start/current require `nullable:false`, end requires `nullable:true`. The own surrogate also requires `nullable:false`.

Only `{entity_name}` is accepted in own-surrogate names/definitions and the role-free foreign-key name; only `{role_name}` in role-qualified foreign-key names. Both placeholders are accepted in the foreign-key definition. Each name template must include its corresponding placeholder. No formatting/conversion suffixes are accepted.

```json
{
  "schema_version": "1.0",
  "dimension_surrogate_key": {
    "semantic_name_template": "{entity_name}Key",
    "data_type": "BIGINT",
    "nullable": false,
    "definition_template": "Surrogate key for {entity_name}."
  },
  "fact_bridge_foreign_key": {
    "with_role_semantic_name_template": "{role_name}Key",
    "without_role_semantic_name_template": "{entity_name}Key",
    "definition_template": "Foreign key to {entity_name}."
  },
  "type_2": {
    "effective_from": {
      "semantic_name": "RecordStartTime",
      "data_type": "TIMESTAMP",
      "nullable": false,
      "definition": "Inclusive start of this dimension version."
    },
    "effective_to": {
      "semantic_name": "RecordEndTime",
      "data_type": "TIMESTAMP",
      "nullable": true,
      "definition": "Exclusive end of this dimension version."
    },
    "is_current": {
      "semantic_name": "IsCurrentRecord",
      "data_type": "BOOLEAN",
      "nullable": false,
      "definition": "Whether this is the current dimension version."
    }
  }
}
```

Use the effective policy, including pending settings, during later local design. Follow [keys and audit columns](keys-and-audit.md) to reserve framework names and retain the final complete Model definitions.
