# Agent output transport audit — 2026-09-05

Read-only production review. Installed `openai-agents==0.22.0`; all model calls in
this investigation used `httpx2.MockTransport`. No external model calls.

## Findings

- `integrations/agents/adapters.py` sets `Agent(output_type=str)`. The SDK omits
  `response_format`; the actual stage schema is only inside the input text.
- Captured 35 real workflow/mode/stage requests while running the seven executor
  test modules (106 passed). Added the exact Conceptual relationship-refinement
  schema and Enrichment's actual 25-target batch schema: all 37 seeded agent stages.
- SDK strict normalization accepts 32/37 after removing `x-gds-*` annotations from
  the transport copy. Canonical Conceptual/Logical/Dimensional schemas otherwise
  raise `UserError` because `x-gds-population-guidance` is beside `$ref`.
- All five Mapping entries intentionally contain open `$defs.JsonObject`:
  one-shot/tool-assisted mapping_authoring and detailed header_mapper,
  attribute_mapper, target_validator. Strict normalization correctly rejects
  these. Do not close those objects or invent fixed template properties.
- Normalization requires optional properties explicitly and converts nested
  `oneOf` to `anyOf`; backend canonical validation must remain authoritative.
  The converted schemas retain OpenAPI `discriminator`; strip that transport-only
  annotation too. Preserve canonical schemas/guidance in prompts and validation.
- Converted schema sizes in the census are 721–29,509 bytes. Enrichment's schema
  is 2,972 bytes for its actual maximum 25-description batch. No remaining
  allOf/oneOf/if/not/prefixItems were found in accepted normalized schemas.
- Normal typed SDK output validates before returning to our repair runner.
  A malformed response raises `ModelBehaviorError`, which the adapter converts
  to `AgentExecutionFailedError`; the existing repair never runs.

## Selected implementation

Enable JSON mode for every agent stage with one shared `ModelSettings.extra_body`
setting. Keep `output_type=str`, the unchanged canonical schema in the prompt,
and canonical validation plus bounded repair. Count the small response-format tag
once in the existing envelope budget. This avoids another schema-normalization
boundary and supports Mapping's intentional open documents.

`tests/web_backend/test_agent_json_mode.py` exercises actual SDK serialization
with Conceptual/Mapping validators, both supported reasoning-setting branches,
tool calls, malformed/type-invalid repair, stable invocation attempts and one
numeric usage receipt per HTTP call. Twelve supported combinations reproduce the
missing response-format field before the fix. Tool-assisted runs use the registry's
supported explicit effort, not its unsupported `default` selection.

Implementation verified: all 12 regressions pass after one shared adapter
setting. Combined adapter/usage gate: 42 passed; repair/execution/stage/schema/
assembly gate: 57 passed. The same SDK regressions plus notebook execution pass
on Python 3.12 (65 tests). Ruff, format and owned Pyright checks pass.

The strict-schema bridge below is a verified alternative, deferred from this
cohesive fix. JSON mode constrains JSON syntax; it does not replace semantic
validation or guarantee a usable result from unavailable providers.

## Verified strict-schema alternative

Use one `AgentOutputSchemaBase` subclass for strict-compatible stage schemas.
It publishes the cleaned, SDK-normalized wire schema; its `validate_json` returns
raw text to the existing `_candidate` and `ValidationRepairRunner`. This keeps
JSON parsing, diagnostics, bounded repairs and final canonical validation in the
existing backend flow. It does not accept a writable candidate on SDK authority.

For Mapping's flexible JSON, keep `output_type=str` and set
`ModelSettings.extra_body={"response_format":{"type":"json_object"}}`.
Canonical schemas already remain in the prompt and backend. The smallest first
slice could enable JSON mode everywhere; that improves JSON syntax only. The
hybrid above also supplies actual structure for the other 32 stages.

Do not treat arbitrary strict-conversion errors as silently acceptable. Use a
bounded compatibility decision for intentional open JSON, retain schema/context
bounds, and validate the concrete 37-stage catalog. Do not remove actual
`properties` names merely because a dynamic name resembles an annotation.
`agent_request_envelope_bytes` currently counts the schema only in the input.
Include the additional normalized `response_format` schema in that same budget;
the new transport copy can add 29.5 KiB. JSON mode adds only its small format tag.

## Local reproduction

`/private/tmp/gds_output_schema_probe.py`: census plus 106 executor tests.
`/private/tmp/gds_structured_output_transport_probe.py`: actual installed SDK,
actual Conceptual/Mapping validator schemas, real local FunctionTool round trip,
existing repair runner, in-memory HTTP and numeric usage recorder.

| Probe | Result | HTTP calls | Repair attempts |
|---|---|---:|---:|
| Normal typed Conceptual output, malformed text | AgentExecutionFailedError | 1 | bypassed |
| Strict schema bridge, malformed then valid | success | 2 | 2 |
| Strict schema bridge plus tool | success | 3 | 2 |
| Mapping JSON mode, malformed then valid | success | 2 | 2 |
| Mapping JSON mode plus tool | success | 3 | 2 |

All five retained one numeric usage receipt per HTTP call. No request or response
body was printed or persisted. MockTransport proves SDK serialization/tool/repair
behavior; it does not prove a particular Foundry deployment accepts a schema.
Refusal, empty output and provider/network failures still need bounded handling;
no output setting guarantees semantic correctness or successful authorization.

OpenAI documents `output_type` on Agent definitions and distinguishes strict
schema adherence from JSON mode. Strict schemas require closed objects and all
properties required; unsupported schemas can be rejected by the API.
Sources: [Agent definitions](https://developers.openai.com/api/docs/guides/agents/define-agents),
[Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
