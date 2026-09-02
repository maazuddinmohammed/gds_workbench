# Focus areas

Execute one current task even when the request spans several areas.

- **Metadata**: inspect with `inspect_metadata`; register complete Source, Bronze, Silver, Gold, ingestion, Copy, and Process records through Metadata Change Sets.
- **Model**: inspect a focused section with `read_model_section`; author Input Scope, evidence, models, Binding, Mapping, Code, and Validation through Model Change Sets.
- **Code**: generate complete artifacts from applied Binding and Mapping. Never deploy or run orchestration.
- **Validation Authoring**: create Validation Groups and Checks. SQL Preflight is separate and local.
- **Local Validation**: run schema and graph checks in memory. It does not replace Change Set validation on the server or prove runtime data correctness.
- **Ad Hoc**: bounded read-only inspection or explanation. If a mutation emerges, create a normal task.

Use `get_model_input_scope` for a focused Input Scope read. Never expose direct Model Input Scope mutation outside a Model Change Set.
