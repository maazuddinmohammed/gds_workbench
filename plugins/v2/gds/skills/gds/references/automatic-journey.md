# Automatic journey

Ask one compact intake for missing directory, Tenant Code, Model, desired endpoints, Full/Selected scope, destination pattern, artifact layout, and SQL policy. Infer supplied answers. Logical Build always includes Profiling, relationship Analysis, Conceptual, and Logical phases.

Queue only requested targets in dependency order. Work one target at a time. Inside a target, make evidence-supported decisions, batch complete records, and update coverage without optional pauses.

When a target is complete:

1. Validate the complete effective graph. Run local review only when the user requests an action summary.
2. Notify the user to Refresh the already-open Workbench.
3. Treat a clear positive acknowledgement as acceptance of the exact digest.
4. Check current revision, reconcile, run `prepare-stage` once, execute its ordered operations, and validate the Change Set on the server.
5. Ask separately before Apply.
6. Apply once and stop at the target boundary. Automatically create and install the required fresh Snapshot before a dependent target; leave that target queued until the user resumes.

Never cross Model Input Scope into Profiling or modeling until Scope Apply succeeds and a fresh Model Snapshot confirms it. Never cross Metadata registration into Model Binding until Metadata Apply succeeds and a fresh Metadata Snapshot confirms the targets. Never cross Model Binding into Mapping until Binding Apply succeeds and a fresh Model Snapshot confirms it.
