# Modeling Assertion contract

## Evidence boundary

An Assertion is one atomic statement attributable to one source location. Useful
categories include:

- business definitions, aliases, and bounded vocabulary;
- entity/event grain, identity, and key rules;
- relationship cardinality, optionality, and lifecycle;
- history, effective dating, retention, and late-arriving behavior;
- calculation, derivation, aggregation, and additivity rules;
- source-to-target mappings, precedence, filters, and exceptions;
- ownership, refresh, latency, quality, and classification constraints; and
- explicit scope inclusions, exclusions, assumptions, or unresolved decisions.

Do not assert a design merely because it seems reasonable. Observed data belongs in
Profiling or Analysis evidence. Agent interpretation belongs in a proposal until a
source or user decision supports it.

## Document record

`modeling_assertion_document` has the document name as its canonical key. Use a stable,
human-readable name that includes a version/date when multiple versions must coexist.

- `tenant_code` and `system_code` are nullable, but when present must identify the
  Model Tenant and an active System.
- `modeling_assertion_file_pattern` is an optional stable discovery pattern, not a
  temporary path or URL.
- `modeling_assertion_document_type` is a bounded established type when available,
  such as `requirements`, `glossary`, `policy`, `specification`, `spreadsheet`, or
  `decision_record`. Preserve the Model's vocabulary.
- `modeling_assertion_document_metadata` is always an object. Prefer safe fields such
  as `source_title`, `source_version`, `effective_date`, `content_sha256`, and
  `extraction_scope`. Omit unknown values rather than inventing them.
- New current sources normally use `is_active: true`.

Do not store source content, credentials, secret names/references, temporary download
URLs, or sensitive local paths in metadata.

## Assertion record

`modeling_assertion_record_key` is the Model-wide canonical key: 1–100 characters,
starting with a letter, then letters, digits, `_`, `.`, or `-`. Prefer a stable semantic
form such as `orders.grain.one-row-per-order`, adding a short disambiguator only for a
real collision. Do not base identity only on a page number or mutable ordinal.

- `modeling_assertion_document_name` must match a Document record.
- `modeling_assertion_record_type` should use an established bounded vocabulary. When
  none exists, prefer specific semantics such as `definition`, `grain`, `identifier`,
  `relationship`, `optionality`, `history`, `calculation`, `mapping_rule`,
  `quality_rule`, `ownership`, `scope`, or `decision`.
- `modeling_assertion_text` is a faithful, self-contained paraphrase with qualifiers.
- `modeling_assertion_details` is always an object. A useful optional structure is
  `subject`, `predicate`, `object`, `qualifiers`, and `effective_date`; omit fields that
  do not fit rather than forcing every fact into a triple.
- `modeling_assertion_source_location` should use the source's durable coordinates:
  page/section/paragraph; sheet/range; slide; table/row label; or heading. It is null
  only when the supplied text has no stable location.
- `modeling_assertion_applicable_layers` is a unique list drawn only from `analysis`,
  `conceptual`, `logical`, `dimensional`, and `mapping`. Use all and only the layers the
  statement can legitimately support.
- Confidence is `high` for explicit unambiguous wording, `medium` for a clear synthesis
  across nearby passages, `low` for unresolved interpretation, or null when the source
  does not justify a rating.
- Status is `active`, `needs_review`, `inactive`, or `deprecated`. New conflicting or
  ambiguous facts use `needs_review`; do not erase the conflict.
- New records normally use `modeling_assertion_record_is_locked: false`.

Every staged record is complete and ID-free. Database IDs returned by focused reads are
for navigation only.

## Extraction and reconciliation

1. Identify source title, version/date, type, ownership scope, and safe location system.
2. Read existing Documents, then Records for the matching Document IDs. Follow cursors
   to avoid overwriting a partial view.
3. Make a coverage outline, then extract one atomic fact at a time with qualifiers and
   exact location.
4. Deduplicate semantic equivalents. Preserve the established key when updating a fact.
5. Keep contradictory facts as separate located records, mark them `needs_review`, and
   describe the conflict without choosing a winner.
6. Check layer applicability before a builder cites the key as an Assertion support or
   source.

For large sources, report processed and skipped sections. This makes later focused
retrieval auditable, but does not claim semantic/vector search completeness.
