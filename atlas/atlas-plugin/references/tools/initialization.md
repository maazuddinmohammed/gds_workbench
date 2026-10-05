# Resolve identity and open local review

Load for actual record access or local authoring, not general explanations. Read the advertised MCP schema and the local `command-contract` for arguments; this guide selects capabilities rather than duplicating their schemas.

| Need | Capability and limit |
|---|---|
| Resolve Tenant name/code | Reuse verified context or page `list_tenants`. Never invent an ID or force a menu after an unambiguous selection. |
| Tenant configuration | `get_tenant_details`; respect `connections_truncated`. A truncated Connection list cannot prove absence. |
| Resolve Model | Page `list_models` for the authorized Tenant; inspect its actual revision, policies and templates. No `get_model_details` tool is established. |
| Local workspace | `session-init` creates/reuses the resolved absolute root. `model-select` binds the first Model; `owner-add` registers verified additional Metadata owners. These do not create server records or grant access. |
| Resume | `status`, then `task-select` only if changing the selected task. Preserve draft and operation evidence. |
| Command arguments | `node scripts/atlas-local.js command-contract --command <name>` from the installed plugin directory. Use [local runtime](../local-runtime.md) for procedures and host setup. |

Open or reuse Atlas Local Workbench when local authoring/review needs it or the user requests it:

```sh
bash scripts/open-workbench.sh
```

On Windows use `scripts/open-workbench.ps1`. Both open bundled static HTML, with no server or port. Select the working-directory root through browser directory access; a user gesture may be necessary. Reuse the existing app across tasks. Workbench Refresh rereads local files, not remote snapshots.

An unavailable launcher does not prevent independent read-only discussion. It does prevent claiming that required local review occurred. [Submission](../change-set-lifecycle.md) establishes actual Stage Runner readiness and approvals.
