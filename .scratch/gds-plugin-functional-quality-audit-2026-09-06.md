# GDS plugin functional-quality audit — 2026-09-06

Completed in three sequential changes: modeling quality, Mapping/SQL, then operational handoff. Existing unrelated work was preserved. The local plugin ZIP was rebuilt; nothing was published, deployed, applied to GDS, or executed in Databricks.

## Findings and corrections

| Area | Finding | Correction |
| --- | --- | --- |
| Final output | Technical validation could be mistaken for business correctness; review concentrated on the plan. | Mandatory inspection of the completed effective graph, evidence classification, input/output reconciliation, reference repair, and explicit coverage limits before presentation. |
| Analysis | General modeling findings could be forced into relationship records; measured fields have an all-or-none contract. | Separate real Attribute-endpoint relationships from general reasoning. Inference verdicts belong in relationship basis; all validation fields stay null without complete measured evidence. |
| Descriptions | Type inference dominated enrichment; descriptions could come from names alone. | Establish Object purpose, row grain and relationships first; interpret Attributes in context. Query only under the saved policy; leave unsupported meanings blank. Preserve existing values, locks and masking. |
| Conceptual | A generated compact model could coexist with old active source-shaped concepts. | Review after drafting; consolidate business vocabulary, explicitly retire superseded mutable records and repair dependents within scope. Omission never deletes an applied record. |
| Logical | Submodel assignment and cross-System identity decisions lacked examples. | Business-capability submodels, reusable memberships, evidence-based normalization exceptions/derived attributes, source-qualified identity, and a worked address/grain reconciliation. |
| Dimensional | Grain principles lacked a final functional check. | Check join fanout, conformance, history lookup, unknown/late members, Bridge allocation, snapshot completeness and additivity; expose unsupported policy. |
| Mapping | Empty generic scaffold; no populated attribute example; required dependency records omitted. | Two-key default: transformation_source and transformation_logic. Populated object/direct/derived/constant examples, exact physical lineage and SQL coordinates, required mapping_dependency, explicit operation semantics and draft review. |
| SQL | Forced UNION ALL could duplicate unified entities; example invented prior-value preference, lookups and parameters. | UNION ALL only for disjoint target keys or followed by supported reconciliation. Example now matches its stated Mapping. Review actual SQL; return incomplete Mapping for governed correction. |
| Validation | Preflight wording implied local execution and encouraged routine testing. | Static review first. Databricks preflight is external, policy-bound and optional. Code generation does not automatically start Validation Authoring. Snapshot-generated schema guidance aligned. |
| Snapshot access | Live MCP reads were called Snapshot reads; readiness implied more than it checks. | Distinguish frozen local select, local draft overlay, live revision-tagged reads, MCP pagination, truncated local selections, Snapshot install, and Workbench Refresh. |
| Stage | Wrong helper output names; missing initial cache binding; unsupported fingerprint-cache claim. | Exact manifest/accepted_digest → manifestPath/expectedDigest translation, explicit state/cache flow, sanitized five-field proof, and verified resume/Apply checks. |
| Recovery | Installing a fresh Model Snapshot over unapplied local records fails. | Existing stash/install/restore/reassess/validate/accept flow documented. Identical bytes can reuse acknowledgement; cached drafts require explicit disposition. |
| Routing | Read-only review conflicted with unconditional setup; design acknowledgements could be confused with result acknowledgement. | Read-only cross-layer review skips setup/writes. Result acknowledgement is distinct. Targets are execution boundaries, not a mandatory full-pipeline checklist. |

Normal Stage now stays on the verified extension path. Legacy helpers remain available for explicitly requested Custom/manual recovery; they do not produce a verified Stage receipt and are not an automatic payload-through-chat fallback. Native PowerShell helper capability remains unchanged. Obsolete database-reset instructions were removed from the user guide; database files were untouched.

## Verification

- Baseline plugin suite: 192 passed, 44 skipped.
- Plugin plus relevant MCP schema checks: all 224 cases passed across the suite and final packaging rerun; 44 PowerShell-dependent cases skipped because PowerShell is unavailable.
- Workbench JavaScript: 52 passed.
- Stage Runner: 73 passed, including synthetic loopback HTTP integration; types and bundle compile passed. No live GDS endpoint used.
- Independent modeling exercise identified mixed grains, unsafe ID conversion, unsupported identity merging, invalid fact aggregation and unknown descriptions. Its read-only routing ambiguity was corrected.
- Independent handoff exercise: 38 local fixture operations passed, including unchanged-byte revision recovery and failed-validation repair. Two remaining state/proof wording ambiguities were corrected.
- Four populated Mapping inner documents validated through actual Python record schemas. Databricks SQL parsed; a SQLite projection check with synthetic values preserved source identity/leading zeros and implemented name/null rules. This does not claim Databricks runtime execution.
- Skill validation, instruction-size limits, Ruff and diff whitespace checks passed. Router remains under 600 words; each guide under 700. Worked examples remain loaded only when relevant. Total/Logical-path budgets now include the examples and complete handoff instructions.
- Deterministic plugin packaging passed; existing VSIX still matches unchanged extension source/bundle.

## Deliverables and limits

- Plugin: [gds-agent-plugin-0.5.0.zip](../plugins/v2/dist/gds-agent-plugin-0.5.0.zip)
- [Modeling example](../plugins/v2/gds/skills/gds/references/examples/modeling-decisions.md)
- [Mapping examples](../plugins/v2/gds/skills/gds/references/examples/mapping-documents.md)
- [Updated user guide](../plugins/v2/gds/docs/USER_GUIDE.md)

No real failing output, business dataset, or live VS Code agent session was evaluated. Forward tests used fictional evidence and disposable local fixtures. Flexible Mapping JSON and technical validators cannot prove business truth; that remains an explicit agent review obligation. Instructions now require evidence limits and blocked material decisions, but cannot guarantee zero hallucinations from every model. No database tests or live Apply/execution were performed.
