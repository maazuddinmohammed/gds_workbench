# Model Input Scope

Require a selected Model and fresh Model Snapshot. Show existing `model_input_scope` first; ask what to add or update. Preserve membership unless change is requested.

For additions, show authorized Source Tenants, accepting supplied Tenant Codes. Ask Source versus Bronze explicitly. List Objects grouped by System; accept exact selections or all Objects for selected Tenant/System combinations. Repeat for further Tenants when requested. Never use Bronze by default to override an explicit Source selection.

The Model retains one owning Tenant; its scope can contain Source/Bronze Objects from several authorized Source Tenants. Resolve each Object's `source_tenant_id` through registered metadata. Full physical keys identify placement, not ownership. Model access does not grant Source Tenant access. Use the authorized snapshot inventory; do not guess references absent from it.

Do not add Silver/Gold targets to input scope; those are Model Bindings. Stage scope only in a Model Change Set. Apply and refresh before dependent builds. A build's Selected scope is only its working subset, never a membership edit. Record every selected input as represented, context-only, excluded with reason, or blocked.
