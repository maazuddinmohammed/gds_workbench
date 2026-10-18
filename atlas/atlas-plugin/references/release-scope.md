# First-release scope

Implemented release boundary. The package supplies local runtime, Atlas Local Workbench, VS Code extension; installed backend compatibility is checked separately.

| Area | First release |
|---|---|
| Agent host | VS Code Copilot uses the Stage Runner extension in a trusted working folder. Stage and governed Apply remain separate. Microsoft sign-in stays in VS Code. |
| Backend | Include database/MCP changes required by the agreed Atlas behavior, implemented and tested locally. Deployment and changes to populated installations remain separate operator actions. |
| Code Generation | Generate SQL. New Python generation is deferred until its entrypoint, output, parameter, packaging and consumer contracts are established. |
| Member support | Member is editable through Metadata Change Sets, keyed by Member Group + Member Code. Member filtering is opt-in. |
| Existing records | Preserve existing Python artifacts/assignments and Member Group records. Their presence is not an invalid Snapshot, and deferred generation does not authorize conversion, deletion or deactivation. |
| Atlas Local Workbench/extension | Adapt the agreed workspace and improve the table/DBML experience. Modularize Stage Runner while preserving its existing behavior before Atlas-specific adaptation. |

## Applying the scope

- A Python generation request gets a clear capability explanation. Preserve its existing files and assignments; do not silently regenerate them as SQL. Continue independently requested SQL work where possible.
- Process metadata may describe an existing supported Python executable using its actual registered contract. Registering it does not generate or execute Python.
- Member filters are configured only on explicit request; pipeline execution belongs to the external framework. Preserve the new-Copy-Group default `is_member_group_required=false`.
- Missing extension capability preserves local work. Follow [extension readiness](change-set-lifecycle.md#extension-readiness); the plugin package does not install the Stage Runner extension.
- Do not widen permissions while aligning backend contracts. Preserve server-owned authorization, locks, revision fencing, redaction and idempotency.

## Workspace and review boundaries

Never silently assign order 1 to historical Process Groups; existing dependency orders need operator review. If the server rejects a field described here, its backend predates this contract: report the gap instead of working around it.

Project-derived Metadata work may keep several owner-specific Snapshot/draft roots in one working directory. The primary Tenant and active Project stay fixed; each owner retains independent authorization, validation, Stage and Apply evidence. See [workspace ownership](workspace-contract.md#project-derived-metadata-owners).

This workspace arrangement does not broaden physical Metadata write or runtime access. Verify operational targets under their true owner; modeled Mapping and Code need no target registration.

Atlas Local Workbench remains the local review/edit/validation surface. User acknowledgement occurs in the agent conversation; the agent invokes Stage Runner, presents server validation/action review and asks separately to Apply. No acknowledgement, Stage or Apply buttons are included in the first Atlas Local Workbench release.
