# First-release scope

Implemented release boundary. The package supplies local runtime, Workbench and companion extension; installed backend compatibility is checked separately.

| Area | First release |
|---|---|
| Agent hosts | VS Code supports the complete workflow, including Stage through its extension. Other compatible hosts can prepare local work and hand off to VS Code for submission; no additional direct Stage adapter is included. |
| Backend | Include database/MCP changes required by the agreed Atlas behavior, implemented and tested locally. Deployment and changes to populated installations remain separate operator actions. |
| Code Generation | Generate SQL. New Python generation is deferred until its entrypoint, output, parameter, packaging and consumer contracts are established. |
| Member support | New Member table/dataset support is deferred until its real schema and relationships are available. |
| Existing records | Preserve existing Python artifacts/assignments and Member Group records. Their presence is not an invalid Snapshot, and deferred generation does not authorize conversion, deletion or deactivation. |
| Workbench/extension | Adapt the agreed workspace and improve the table/DBML experience. Modularize Stage Runner while preserving its existing behavior before Atlas-specific adaptation. |

## Applying the scope

- A Python generation request gets a clear capability explanation. Preserve its existing files and assignments; do not silently regenerate them as SQL. Continue independently requested SQL work where possible.
- Process metadata may describe an existing supported Python executable using its actual registered contract. Registering it does not generate or execute Python.
- Member-based execution remains deferred. Preserve existing metadata and the agreed new-Copy-Group default `is_member_group_required=false`.
- Missing host capability preserves local work. Follow [extension readiness](change-set-lifecycle.md#extension-readiness); a portable skill package does not supply the VS Code tool in another host.
- Do not widen permissions while aligning backend contracts. Preserve server-owned authorization, locks, revision fencing, redaction and idempotency.

## Required compatibility work

Track the implementation beside its authoritative rules: [Process Group order](metadata/tables/process-group.md#dependency-order), [Copy order](metadata/tables/copy.md#copy-order-and-default), [keys/audits](model/keys-and-audit.md#population-boundary-and-implementation-alignment), [Binding](model/binding.md#existing-records-and-reassignment), [Mapping consumer context](model/mapping-documents.md#complete-context-for-coding-and-validation), and [Validation SQL/consumer contracts](model/validation.md#sql-eligibility-and-protection).

Existing installations require an explicit backend upgrade and operator review of existing Process Group dependency orders. Do not silently assign 1 to historical groups. Deliver compatibility checks and operator instructions; deployment remains separate.

Model-derived Metadata work may keep several owner-specific Snapshot/draft roots in one working directory. The primary Tenant and active Model stay fixed; each owner retains independent authorization, validation, Stage and Apply evidence. See [workspace ownership](workspace-contract.md#model-derived-metadata-owners).

This workspace arrangement does not broaden Binding eligibility: current Silver/Gold targets require their `source_tenant_id` to match the Model's Tenant. Report an ineligible target before dependent work; never rewrite ownership to make it eligible.

Workbench remains the local review/edit/validation surface. User acknowledgement occurs in the agent conversation; the agent invokes Stage Runner, presents server validation/action review and asks separately to Apply. No acknowledgement, Stage or Apply buttons are included in the first Workbench release.
