# Candidate history / selected evidence reproduction

Read-only production audit, 2026-09-05. Synthetic fixture tests only.

`test_candidate_history_reproduction.py`: **32 passed**. Command:

```bash
PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m pytest -c web_app/backend/pyproject.toml .scratch/test_candidate_history_reproduction.py --tb=no --show-capture=no -q
```

## Confirmed failure

Every family rejects an exact unchanged applied record when its physical evidence is outside the current selected subset. The same evidence can be outside selection because the user selected another subset or because inactive physical records no longer appear in selection. No live database is needed to reproduce this validation seam.

| Family | Safe diagnostic code | Rejections in fixture |
| --- | --- | --- |
| Analysis | `candidate.endpoint_outside_selection` | Existing relationship |
| Conceptual | `candidate.support_outside_selection` | Existing Object support |
| Logical | `candidate.source_outside_selection` | Existing Entity source and Attribute source |
| Dimensional | `candidate.source_outside_selection` | Existing Entity source and Attribute source |

All four pass the control: exact in-scope echo validates and produces no staged changes. The same controls pass with stored locks enabled and agent lock fields false, as required by the authoring contract. Omitting the historical evidence also produces no changes. Dimensional alone rejects completely empty candidates, so its omission control echoes the unchanged Submodel while omitting all Entity/Attribute sources.

The failure occurs before applied-record reconciliation: Conceptual/Logical validate incoming supports/sources before `_merge_*`; Dimensional validates all incoming physical sources before merging; Analysis checks incoming endpoints before looking up/merging the applied relationship.

Safety controls pass: a genuinely new record with that outside-selection evidence rejects, as does copying evidence to a different parent record identity. Do not globally add all historical physical keys to the selected-key allowlist.

## Detailed-mode distinction

Detailed reconciliation requires every supplied applied reference in `reviewed_applied_record_refs`. This does **not** require every applied record body to be returned. Conceptual requires every detailed entity; Logical requires its topology/detail records; Dimensional allows applied bodies in the older whole-model validator but does not require them. Current Dimensional whole-model seed prompt asks only for a relationship receipt and explicitly forbids returning applied bodies. Its merged final candidate still reaches the ordinary validator.

Current defaults repeatedly say to preserve compatible applied records; omission is documented as preservation. This makes unchanged echoes plausible, but the bug is not proven to be a mandatory full-history echo in every detailed stage.

## Proposed bounded fix

Teach incoming evidence checks to distinguish unchanged applied evidence under the **same canonical owner identity** from new/changed evidence. Preserve agent authority restrictions and stored locks. Permit only the established historical edge/endpoint; never grant another parent permission to reuse it. Keep new or changed references subject to selected-scope rules and the final authoritative graph validator.

An exact unchanged normalized record can safely become a no-op; a record changed for another reason while carrying an unchanged historical source needs per-source identity/content comparison rather than a blanket whole-record exemption. Inactive/removed history cannot justify new active references. Regression cases should cover historical source metadata changes, status changes, copied sources, and locked source flags as well as the 32 baseline cases.

Prompt guidance can explicitly say to omit untouched applied records, but cannot replace this backend distinction: models may still echo them, and detailed assembly may materialize them.

## Agreed first fix: exact canonical echo only

Parent confirmed this bounded choice after the physical-history gate. It supersedes
the broader per-source proposal above. Re-ran all 32 reproduction tests against
current production: **32 passed**, still reproducing the rejection.

Resolve the applied owner using each candidate module's existing canonical key
function (`normalize_model_key_value` trims ASCII spaces and casefolds key values).
Compute the existing `_merge_*` result once, then compare that complete canonical
document with `existing.model_dump(mode="json")`. Exact equality permits only
the physical-selection check to be skipped. Existing merges restore stored lock
flags, Analysis validation/status fields, omitted nested records and original
nested ordering. Raw candidate equality is therefore the wrong comparison.
All schema, duplicates, agent authority, assertion availability, policy-column,
lock and reference checks still run, followed by the full Model graph gate.

No new recursive normalizer/helper is needed. Do not casefold arbitrary payload
strings or strip lifecycle fields. Same canonical key alone does not establish
equality: changed basis, definition, source rationale/order/status or spelling
that current reconciliation treats as an edit remains an edit. Reactivation is
not an echo. This also agrees with canonical `_retains_physical_history`: edits
to another field of an owner do not generally grant its sources historical
eligibility. A broader per-source policy would need a separate canonical review.

Exact production locations, all under backend `features/`:

- `analysis/candidate.py::_normalize` (currently lines136–164): move applied
  lookup and `_merge_record` before endpoint scope checking; reuse that merged
  document for equality and staging. Exempt only exact canonical echoes from
  `candidate.endpoint_outside_selection`.
- `conceptual/candidate.py::_normalize` (lines137–166): resolve/merge each Object
  and Relationship after its authority check, before evidence checking.
  `_validate_agent_evidence` (line236) receives an explicit unchanged-physical-
  history flag; only Object support membership can use it. Assertion checks stay.
- `logical/candidate.py::_normalize` (lines198–211): resolve/merge Entity and
  Attribute once; pass equality to `_validate_entity_evidence` (line261) and
  `_validate_attribute_evidence` (line289). Only physical branches use the flag.
- `dimensional/candidate.py::_normalize` (lines198–267): resolve/merge each Entity
  and Attribute before the existing source loop; retain the merged dictionaries
  for `validate_staged_records` (lines282–298), avoiding a second merge. Change
  only physical source membership checks; policy/authority checks remain intact.

Promote the scratch controls into the four existing `test_*_candidate.py` suites
with the expected outside-selection echo result changed to valid/no staged
changes. Add changed-owner/source/status, copied-owner, mixed unchanged echo plus
new selected output, omitted nested history, duplicate identities and forbidden
agent lock tests. Keep exact in-scope/locked/omission controls, and verify original
snapshots remain unchanged. Exercise normal and detailed executor assembly with
an out-of-selection applied echo before freezing; no prompt workaround is needed.
