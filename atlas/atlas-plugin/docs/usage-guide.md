# Atlas usage guide

Atlas helps Copilot build and maintain GDS Workbench metadata, models, mappings
and code. You describe the work in plain English and Atlas prepares it locally.
Records in GDS Workbench change only after you approve twice: Stage, then Apply.

Set up Atlas first with the [setup guide](copilot-vs-code-installation-and-setup.md).

## Words you'll see

| Term | Meaning |
|---|---|
| Tenant | Your team's space in GDS Workbench. It owns metadata and Projects. |
| Project | One modeling effort in a Tenant: its scope, models, Mappings and code. |
| Scope | The source tables chosen for a Project in the web app. |
| Snapshot | A local copy of saved records that Atlas reads. |
| Change Set | One reviewed batch of draft changes. |
| Applied | Saved with Apply. |

## How it works

```text
You ask
  -> Atlas prepares local drafts
  -> You review them in Atlas Local Workbench
  -> You approve Stage: Stage Runner uploads a server draft
  -> You approve Apply: Atlas saves the records
```

- Questions and explanations are answered directly, with nothing to approve.
- Copilot also asks you to **Allow** Atlas's helper commands and server tools.
  That's normal; saving records still needs your Stage and Apply approvals. The
  one exception is a profiling run, which saves its profiles directly.
- Apply saves Atlas records only. It doesn't deploy code, run pipelines or commit
  to Git.

## Start or resume

For Project work, your Project must already exist in the web app with its source
tables in scope.

1. Open your working folder in VS Code: one folder per Project, outside
   `Tools/Atlas`. Open the Chat view and select **Local**, then **Agent**.
2. Send `Start atlas.` To continue earlier work, send
   `Resume atlas. Show the unfinished work in this folder.`

Atlas asks only for what it's missing:

| Atlas may ask for | What to answer |
|---|---|
| Tenant | Your team's Tenant name or code. Ask `List my tenants.` if unsure. |
| Project | The Project name. Ask `List the projects.` if unsure. |
| SQL policy | Whether Atlas may run read-only queries on your data. It writes SQL code either way. **Never**: no queries or profiling. **Essential**: only queries needed to continue. **Proactive**: also useful checks. |
| Environment | `dev`, `qa`, `stg` or `prod`, when queries run. The default is `dev`. |
| Sub-agent policy | Asked only before Atlas delegates work. See [below](#choose-the-sub-agent-policy). |

To give everything at once:

```text
Start atlas.
Tenant: [your Tenant code]
Project: [your Project name]
SQL policy: [Never / Essential / Proactive]
Task: [what you want done]
```

## What you can ask, with sample prompts

Copy a prompt and replace the parts in [brackets]. Plain English works too. Use
the names you see in Atlas Local Workbench: entity names such as [Customer] for
models, and `schema.table` for physical tables.

### Understand what exists

```text
Explain how Atlas works.
Why does the [Customer] logical entity exist? Explain only; don't change anything.
Show the lineage of [gold_demo.fact_order.order_amount] back to its source.
```

### Register and fix physical metadata

```text
Register the tables defined in [customer-spec.md] under System [ERP] and Connection [ERP_SQL]. Set up Source and Bronze ingestion.
Fill missing physical descriptions for [bronze_demo.customer]. Keep existing descriptions.
List the Systems and Connections in [your Tenant].
```

Atlas can take definitions from DDL, a schema export or documentation in your
working folder. It asks whether you want Source registration only or Bronze
ingestion too. If your framework's usage is unclear, it asks for the relevant
orchestration code. Physical metadata is shared across Projects.

### Prepare a Project's sources

Scope is managed in the web app. Atlas uses it but doesn't change it.

```text
Which source tables should I add to the Project scope for [order reporting]?
Profile the scoped tables. SQL policy: Essential.
Write Project enrichment for the scoped tables: missing descriptions and key findings. Keep existing values.
Analyze the scoped tables: grain, candidate keys and relationships.
```

Project enrichment records this Project's own descriptions and findings; it never
edits shared physical metadata.

### Build the models

Each layer builds on applied work: a dimensional model needs an applied logical
model. Subject Areas group the scoped tables by business capability. A build works
on one Subject Area at a time, reusing what earlier areas built, while the Project
keeps one model per layer. Areas are optional focus windows, never evidence. To
improve what is already built, ask Atlas to optimize the model instead.

```text
Group the scoped tables into Subject Areas. Subject Areas only.
Build the logical model for the [Order Capture] Subject Area. SQL policy: Never.
Optimize the logical model: review grain and relationships. SQL policy: Never.
Build the dimension [Dim Customer] from the applied logical entity [Customer]. Dimension only.
Grill me on the [Order] grain.
```

For a logical model, Atlas checks coverage of the scoped tables and columns (per
Subject Area when you build one), lineage back to sources, normalization, naming
standards, column order and relationships, which point from each child's foreign
key to its parent. Say **Grill me** to settle design questions together, one at a time.

### Map and generate code

A Mapping needs an applied target, and code needs an applied Mapping.

```text
Complete the Mapping for [silver_demo.Order] from System [ERP]. Update only what is missing.
Generate the transformation SQL for [silver_demo.Customer] from its applied Mapping.
I ran [silver_customer.sql] and got this error: [paste the error]. Fix the code.
Register [silver_demo.Customer] and its generated SQL for the pipeline.
```

Atlas writes generated SQL to the `code/` folder in your working folder. You run
it yourself; Atlas doesn't execute or deploy it. Bring any error back and Atlas
fixes the code locally.

### Validate

```text
Validate the logical model. Don't change anything.
Write validation checks for [Fact Order] that catch real data problems, not trivial ones.
```

### Change an existing Project

```text
Change request [CR-1042]: [Finance needs order amounts by customer country]. Show me what has to change and recommend the smallest option before changing anything.
Set the Project's default dimensional history to [Type 2].
```

Atlas traces the impact across metadata, models, Mappings, code and validation,
offers options and recommends the one with the fewest changes. It asks you
before drafting anything.

## Review in Atlas Local Workbench

Atlas opens Atlas Local Workbench in your browser when changes are ready.

1. Select **Open working directory** and choose your working folder: the one that
   contains `.atlas`, not `.atlas` itself. Allow folder access.
2. Review the proposed records and any validation findings.

| Button | What it does |
|---|---|
| **Save changes** | Saves your own edit to the local draft files |
| **Reload local files** | Shows Atlas's latest local edits; it doesn't download server records |
| **Validate locally** | Checks the local changes and lists findings |
| **Generate DBML** | Exports diagram descriptions of the whole local Project, plus one file per Subject Area |

To change something, ask Atlas in chat, then select **Reload local files**. If
you edit a record yourself, select **Save changes** and tell Atlas what you
changed. If the Workbench reports a conflict, reload and redo your edit.
Approvals happen in chat; the Workbench has no Stage or Apply button.

## Approve Stage, then Apply

1. When the changes are right, tell Atlas: `I approve these changes for Stage.`
   VS Code asks to allow **Stage approved Atlas Change Set**. It replaces only
   your pending server draft; select **Allow**. Stage Runner uploads the changes.
2. Atlas validates the draft on the server and shows the result.
3. When Atlas asks `Apply these validated changes to [Project]?`, reply
   `Yes, apply.` Atlas saves the records and refreshes your local Snapshots.

If anything changes after you approve, Atlas asks you to review it again.

## Choose the sub-agent policy

Before Atlas hands work to a helper agent, it asks once per working folder:

| Choice | Meaning |
|---|---|
| **Current model only** (recommended) | Helpers use the same AI model as your chat |
| **Agent selects the model** | Atlas picks a suitable available model for each task |
| **Specified model only** | Helpers use only the exact model you name |

Change it any time, for example: `Set the sub-agent policy to Current model only.`
If your editor can't follow the rule, Atlas works without helpers.

## Tips for good results

- Name the Tenant, Project and tables, and say what to keep, such as "keep
  existing descriptions".
- Point to documents and standards by their path in your working folder.
- When you're unsure, ask: "Give me options and recommend one."
- You can start a new task in the same folder any time; existing drafts are kept.
- Don't paste passwords, tokens or raw source data into chat.

Not supported yet: building models from existing code (reverse engineering).

## If something goes wrong

| Problem | What to do |
|---|---|
| VS Code asks you to sign in for **gds-workbench** | Sign in with the same Atlas account. |
| Atlas says Stage Runner needs sign-in | Run **ATLAS: Check Stage Runner** and sign in. |
| Atlas Local Workbench didn't open | Ask Atlas to open it again, in Chrome or Edge. |
| A tool is missing | Use a **Local** session with **Agent**, and check **Configure Tools**. See [setup troubleshooting](copilot-vs-code-installation-and-setup.md#troubleshooting). Your drafts are kept. |
| Validation fails | Ask Atlas to explain and fix the findings, then review again. |
| Stage or Apply result is uncertain | Ask Atlas to check the saved operation and server state before retrying. |
| Records are locked or changed on the server | Ask Atlas to explain the conflict. Don't replace local files to force it. |
