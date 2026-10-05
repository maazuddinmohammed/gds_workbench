# Atlas usage guide

Use this guide after completing either the
[Codex setup](codex-installation-and-setup.md) or
[Copilot - VS Code setup](copilot-vs-code-installation-and-setup.md).
You only need the setup guide for the host you use.

The Atlas steps are the same in both hosts:

```text
Open your working folder
          |
       Start Atlas
          |
Review and check local changes
          |
     Approve Stage
          |
Review the checked server draft
          |
     Approve Apply
```

**Stage** sends reviewed files to a server draft. **Apply** saves the approved
draft as current Atlas records. They are separate actions.

## 1. Open your working folder

Use a folder for your work, separate from the Atlas installation folder.

| Host | How to start |
|---|---|
| Copilot - VS Code | Open the working folder in VS Code. Open Copilot Chat in a local agent session. |
| Codex CLI | Open the same local working folder in VS Code. Run **Atlas: Start Codex Bridge** and keep VS Code open. In a terminal, enter that folder with `cd`, then run `codex`. |

To use another folder, open that folder in a new agent session. You do not need
to install Atlas again. For Codex, start the bridge in VS Code for each new
working folder. Microsoft sign-in may be reused by VS Code. Keep Atlas files inside the
opened folder or its child folders so Stage Runner can read them.

## 2. Start Atlas and describe the work

Send:

```text
Start atlas.
```

Atlas asks only for missing information needed by your request. It opens
Atlas Local Workbench when preparing or reviewing local changes.
It reuses saved choices when you resume.

| Information | What to provide |
|---|---|
| Tenant | Your team's Tenant name or code. If unsure, ask Atlas to list your available Tenants. |
| Task | Describe what you want to create, change, or inspect. |
| Model | The Model name, if the task needs one. Ask Atlas to list available Models if needed. |
| Working folder | Confirm the current folder, or give the full path to a folder inside it. |
| Sub-agent policy, only before authorized delegation | Choose **Current model only**, **Agent selects the model**, or **Specified model only**. For the last choice, give the exact AI model name or ID. |
| SQL permission | **Never**: no SQL execution. **Essential**: run SQL only for evidence needed to continue. **Proactive**: also run useful checks. |
| Environment | When SQL is needed, choose `dev`, `qa`, `stg`, or `prod`. The default is `dev`. |

The SQL environment does not change your Microsoft account or Atlas backend.

For example:

```text
Start atlas.
Tenant: [your Tenant code]
Model: [your Model name]
Task: Improve missing descriptions for the selected customer tables.
Keep existing descriptions. Use the current working folder.
SQL policy: Never.
Sub-agent policy: Current model only.
```

### Choose the sub-agent policy

A sub-agent is a helper agent assigned part of the work. Choose its model rule:

| Choice | What Atlas must do |
|---|---|
| **Current model only** (recommended) | Use the same AI model as your main chat for every sub-agent. |
| **Agent selects the model** | Select a suitable available model for each sub-agent's task. |
| **Specified model only** | Use only the exact model you name for every sub-agent. |

This choice does not change your main chat model or your Atlas data Model.
It applies to all workflows and nested sub-agents in this working folder.
Atlas saves the choice and reuses it when you return. Older folders without a
saved choice prompt you only before authorized delegation.

You can change it in chat, for example: `Set the sub-agent policy to Specified
model only. Use [exact model name or ID].` Replace the brackets with your choice.
Atlas must check that your host can use that model. If it cannot follow the
rule, Atlas continues in the main agent and explains the limit. It must not
select a substitute model without your instruction. Choosing a policy does not
require Atlas to use sub-agents.

## 3. Let Atlas prepare the local work

Atlas checks the selected Tenant, Model, and existing work. It gets the required
Snapshot: a local copy of the saved Atlas records. It puts proposed changes in
separate local files, then checks them.

Wait for Atlas to report that the changes are ready for review. For a read-only
request, Atlas can answer without preparing changes or using Stage and Apply.

## Atlas Local Workbench

1. Select **Open working directory**.
2. Select your working folder: the folder that contains `.atlas`. Do not select
   the `.atlas` folder itself.
3. Allow folder access in Chrome or Edge when asked.
4. Review the proposed changes and validation findings.

The top bar shows the saved sub-agent policy. **Not set** means that Atlas still
has no saved delegation preference. Independent work can continue. Use
**Reload local files** after changing the policy in chat.

| Control | What it does |
|---|---|
| **Save changes** | Saves an edit to local files. |
| **Reload local files** | Reads the latest local files after agent edits. It does not download new server records. |
| **Validate locally** | Checks the local changes and shows findings. |
| **Generate DBML** | Exports a diagram description of the complete local Model. This is an optional user action. |

If the page did not open, ask Atlas to open Atlas Local Workbench again.
If it reports a file conflict, review that conflict before saving.

## 4. Review and approve Stage

1. Check the complete batch in Atlas Local Workbench.
2. Ask Atlas to correct unwanted changes or unresolved findings.
3. When the batch is correct, tell Atlas: `I approve these changes for Stage.`
4. Complete any tool confirmation shown by your agent host.

Stage Runner reads the approved local files and sends them to the server draft.
It returns a short receipt to the agent. You do not need to paste the records,
copy hashes, or run helper commands. Bulk Stage records are sent directly by the
runner; the agent still reads records when it needs to author or review them.

If the content changes after approval, Atlas must check it and ask you to review
it again. Atlas Local Workbench has no Stage or Apply button in this release.

## 5. Review and approve Apply

1. Atlas checks the staged draft on the server and shows the result.
2. Review the proposed actions for the selected Tenant and Model.
3. If the result is correct, approve Atlas's separate **Apply** request.
4. Wait for Atlas to confirm success and refresh the affected local Snapshots.

Apply saves Atlas records. It does not deploy generated code, run a pipeline,
or commit files to Git. A successful local check alone does not mean Apply is
complete.

## 6. Resume work later

Open the same working folder in your agent host. Send:

```text
Resume atlas. Show the unfinished work in this folder.
```

Select the same folder in Atlas Local Workbench if asked. Use
**Reload local files** after the agent changes files.

One working folder holds one active Model. Use another folder for a different
Model. Starting a new task preserves existing drafts.

## Choose a task

You can describe your request in plain English or name a workflow:

| Workflow | Use it to |
|---|---|
| Investigate | Explain Atlas, existing models, lineage or recorded rationale. |
| Source analysis | Profile/analyze selected sources, grain, candidate keys and relationships. |
| Conceptual model | Define business concepts and relationships. |
| Logical model | Develop normalized Entities, Attributes and Submodels. |
| Dimensional model | Design dimensions, facts, measures and history. |
| Mapping | Define transformations into an applied target model. |
| Code generation | Generate SQL from applied Mapping. |
| Verify | Check artifacts or author SQL Validation definitions; distinguish checks from execution. |
| Model change | Assess impact and update the affected existing design. |
| Metadata | Correct physical Metadata, descriptions or ingestion settings. |
| Registration | Register modeled targets or generated files; optionally prepare local creation DDL. |

Guided explanation is the default. Ask for **Grill Me** to discuss design choices
step by step; switching modes keeps the same work. Atlas reuses valid existing
artifacts and enters the needed stage instead of restarting the whole SDLC.

Examples:

- “Analyze these source tables and build a logical model. SQL Never.”
- “Map these objects to the existing model.”
- “Explain why this entity exists, then update its grain.”
- “Validate this logical model without generating SQL checks.”

Physical description correction and Model-owned enrichment are different operations.
The current plugin cannot read/write the web workflow's Model-owned enrichment
through its governed Model contracts; it reports that gap instead of modifying
physical Metadata as a substitute. See [capability boundaries](../references/platform/capabilities.md).

## If work stops

| Problem | What to do |
|---|---|
| Sign-in is required | Use the renewal steps in your setup guide: [Codex](codex-installation-and-setup.md#reconnect-or-stop) or [Copilot](copilot-vs-code-installation-and-setup.md#when-atlas-asks-you-to-sign-in-again). Keep the same dev account. |
| A tool is missing | Repair your host setup. Keep the local drafts. |
| Validation fails | Ask Atlas to explain and correct the findings, then review again. |
| Stage or Apply has an uncertain result | Ask Atlas to check the saved operation and server state before retrying. |
| Records are locked or have changed on the server | Ask Atlas to explain the conflict. Do not replace local drafts or Snapshots to force the action. |

Do not put passwords, tokens, or raw source data in chat. The
[technical runtime reference](../references/local-runtime.md) is for agents and
maintainers; normal use does not require its commands.
