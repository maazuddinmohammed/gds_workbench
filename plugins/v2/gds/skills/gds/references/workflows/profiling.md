# Profiling

Profile only Objects selected by Model Input Scope. Report scoped, profiled, unprofiled, excluded, and blocked Attributes.

For a Source Object, build every physical reference from:

- Connection `foreign_catalog`
- Object `fc_object_schema`
- Object `fc_object_name`
- Attribute `fc_attribute_name`

Any missing coordinate is a hard error. Never connect directly to a Source or fall back to ordinary source Object/Attribute names.

For Bronze, use its resolved `tenant_catalog`, `object_schema`, `object_name`, and `attribute_name`.

Use existing Profile records first. Under `never`, execute no SQL and report missing measured evidence as unprofiled. Under `essential`, query only an evidence gap that would otherwise block a responsible result. Under `as_needed`, use bounded grouped reads when they materially improve the model.

Prefer counts, null rates, distinctness, ranges, patterns, and candidate-key tests. Read a small representative sample only when record shape or coded values need clarification. Never persist raw query output. Profiling records observed counts and statistics only; never fabricate evidence. Missing evidence may lower modeling confidence without automatically blocking a supportable Logical result.
