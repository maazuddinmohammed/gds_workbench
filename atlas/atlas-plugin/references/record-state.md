# Record state and protection

Shared rules for every workflow. Apply them when reading inputs, authoring complete records and performing [local validation](local-validation.md). Dataset schemas determine which state fields exist.

## Locks

| State | Authoring rule |
|---|---|
| Locked record | Preserve the complete applied record. Do not edit, deactivate, unlock, rename/rekey or create a replacement to bypass its lock. Report blocked changes and continue independent work. |
| Unlocked record | Changes still require valid scope, ownership, references, workflow intent and validation. Unlocked does not mean unrestricted. |
| Active locked input | May be read, queried under SQL policy and used as evidence or a reference when otherwise eligible. Reading a locked input does not change it. |
| No lock field | Do not invent one or assume that another record's lock applies without a documented rule. Profiling Profiles have no independent lock field. |

- A **Metadata Object lock** protects the Object and all its Attributes, including proposed Attribute additions. An Attribute's own lock protects that Attribute. Omit unchanged locked Metadata records from pending changes; current validation rejects their submission even when unchanged.
- A **Model record lock** protects that complete record, including nested supports, sources and submodel memberships. Preserve independently locked nested members when editing an unlocked parent. Carry complete nested arrays; omission does not delete or retire applied members.
- Logical and Dimensional Entities and their separately stored Attributes/Relationships have their own locks. The current generic Model validator does not propagate an Entity lock to those separate records. Do not claim that additional protection is implemented.
- Do not clear flags locally to satisfy validation. A separately governed human lifecycle action is distinct from workflow authoring; resume from refreshed/reconciled state after such a change.
- Schema is part of Entity identity. Changing a schema/name changes the key; preserve locked Entity-owned Mapping, Code and nested sources rather than silently redirecting them.

## Activation and history

- Preserve existing inactive/deprecated records and their keys during unrelated work. Absence from a new draft does not delete them or make their names available for reuse.
- Do not silently reactivate records or their parents. An intentional supported lifecycle change needs its dependent changes and validation; a lock still blocks it.
- Use eligible active inputs for profiling/modeling and enforce each dataset's active-dependency rules. Metadata references do not all require active parents: an active Copy may remain under an inactive Copy Group and be skipped at runtime. Inactive records may explain history; visibility alone does not make them current modeling evidence.
- Preserve valid retained history when upstream physical metadata or scope becomes inactive. Historical retention does not authorize new out-of-scope content. Follow the dataset's retained-history rules during validation.
- Activation fields vary: some datasets use `is_active`, others a named status such as `active`, `inactive` or `deprecated`; some have neither. Use the published schema and agreed defaults. Unknown, false and zero are distinct values.

## Three different locks

| Lock | Protects |
|---|---|
| Tenant Lock | Governed concurrent writes. Acquiring it does not unlock Metadata or Model records. |
| Model Input Scope lock | The membership record and its lifecycle. An active locked membership remains usable; the lock is not a restriction on profiling or modeling from that input. |
| Record/nested-member lock | The protected record's content under the rules above. |

Local checks use the bound applied baseline as well as pending work. The server rechecks authoritative protection during governed submission/Apply; a stale Snapshot cannot override a current lock. Follow the [Change Set lifecycle](change-set-lifecycle.md) for that sequence.

Current contracts: `application/change_sets/metadata_validation.py`, `application/change_sets/model_validation.py` and `domain/modeling_records.py` under `mcp_server/gds_etl_workbench/`; Atlas local mirrors under `workbench/validation/`; helpers and Atlas Local Workbench share those rules.

## Model lock

A locked Model is read-only across every section and workflow. Individual record
locks do not override it. Read operations and independent Metadata authoring remain
available. Agents must never unlock a Model or propose its lock state in a Change
Set. A human Architect or higher may use Lock/Unlock Model in the web UI while
holding the Tenant Lock; engineering may use approved backend SQL. Finish or
cancel queued/running workflows before locking. Refresh after a lock transition:
it advances the Model revision and invalidates older write plans.
