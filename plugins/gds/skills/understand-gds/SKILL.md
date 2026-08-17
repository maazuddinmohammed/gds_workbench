---
name: understand-gds
description: Explain GDS concepts and route users to the smallest governed workflow. Use only for conceptual questions about what GDS is, how metadata, modeling, and governance relate, or which workflow to choose; do not execute reads, draft changes, or open the local Data Workbench.
---

# Understand GDS

1. Identify the user's branch: metadata, modeling, generated code, governance,
   or a general GDS explanation.
2. Read [references/gds-overview.md](references/gds-overview.md) when domain
   concepts or workflow boundaries are needed.
3. Route metadata inspection or change to `manage-gds-metadata`; generic Model,
   Scope, evidence, or Model Change Set work to `manage-gds-model`; layer design to
   its matching builder; and local Snapshot/Change Set editing to
   `open-gds-metadata-workbench`.
4. Explain only the branch the user needs. Keep Metadata Change Sets distinct
   from Model Change Sets and Metadata Snapshots distinct from Model Snapshots.
5. Use the exact GDS terms in the overview. Finish when the user can identify
   the relevant GDS concept and the next governed workflow.
