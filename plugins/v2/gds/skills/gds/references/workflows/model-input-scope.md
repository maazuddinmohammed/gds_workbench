# Model Input Scope

Model Input Scope is a Model Change Set dataset containing selected active Source and/or Bronze Objects for one Model.

Scope determines the transformation input. When equivalent Source and Bronze Objects are both selected, use Bronze by default. Use Source when Bronze is absent, the user explicitly chooses it, or the architecture intentionally skips Bronze through a foreign catalog. Ask only when equivalence or intent is unclear.

Do not add Silver or Gold targets to input scope. Target association is Model Binding, not Mapping and not Input Scope. Every scoped Object must have the same `source_tenant_id` as the Model Tenant.

Record all selected inputs in the coverage loop; never silently drop the lower-precedence record.
