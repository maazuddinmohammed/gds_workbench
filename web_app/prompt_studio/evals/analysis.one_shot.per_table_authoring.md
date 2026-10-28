# Test log: analysis.one_shot.per_table_authoring

## 2026-10-28 · `baseline-with-context` · fixture `hr_lookalike_groups_with_context` · 3 runs

| Measure | baseline |
|---|---|
| Results returned | 3/3 |
| Valid answers (schema) | 3/3 |
| Expected items found | 3/3 (100%) |
| Forbidden items returned | 0 |
| Other items per valid answer | 0.0 |
| Clarity (1–5) | 4.0 |
| Confidence (1–5) | 4.0 |
| Blockers cited | – |
| Confusing cited | S9 ×3, S10 ×3, S8 ×2, S13 ×2 |

Suggested verdict: **baseline only (no studio change for this stage)**

Review notes:
- baseline run-01 confusing [S9]: S9 makes the To side `one` when the To column is a documented single-column key, and t1.employeeid has is_natural_key true. S6 says a To column with distinct_count below non_null_count (400 vs 1200 here) is not a single-column key and rules out many_to_one and one_to_one, and the Context record says
- baseline run-01 confusing [S10]: S5 and S10 steer toward a unique single-column key so a correct finding can come back `supported`, while S8 (Grain and history) allows a repeating To key when a documented rule establishes the pair. Because S3 defines `supported` as requiring unique To values, this correct link to a multi-load Bronz
- baseline run-01 comment: The only link, t2.employeeid to t1.employeeid, is stated outright by the Context record and the column description, so the evidence is strong. Cardinality is the one real judgement call, because t1.employeeid repeats across loads (400 distinct values in 1,200 rows). A short rule for the cardinality of a To key that repeats only because Bronze keeps several loads would remove that call.
- baseline run-02 confusing [S8]: Says to link each System's tables to that System's own parent 'by source_systems' and to leave the link out when the parent's System cannot be told. Here every source_systems is empty, so only the Context record (cds_/cym_ groups) says which parent t2 belongs to; I relied on it, but S8 does not say 
- baseline run-02 confusing [S9]: The To side is 'one' for a documented single-column key, yet t1.employeeid has is_natural_key true while its profile repeats (400 distinct of 1200 non-null) and the Context record says it repeats across loads. S6 settles it (a repeating To column cannot be many_to_one, so I used many_to_many), but S
- baseline run-02 confusing [S10]: Asks for references to point at keys so findings can come back supported, but S3 defines supported as unique To values, so a multi-load Bronze parent like t1 can never validate as supported. The prompt does not say whether such a pair is still wanted; I followed the Context record and included it.
- baseline run-02 confusing [S13]: The closing paragraph after S13 mentions 'enabled tools' and 'Context identities and manifests', but S1 says one-shot mode has no tools and this input has no manifests.
- baseline run-02 comment: The single link is clear from the employeeid description and the Context record, and the other three columns (contact name, postcode, load batch) have no parent. The only real judgment was cardinality, where I followed S6 and S9 plus the record's 'repeats across loads' statement over the natural-key flag. A one-line rule for a natural-key flag contradicted by a multi-load profile would remove that doubt.
- baseline run-03 confusing [S10]: Says to point a reference at a single-column key so a correct finding can come back supported, but S3 defines supported as needing unique To values. t1.employeeid repeats (400 distinct in 1200 rows), so this correct link will validate as unsupported. Nothing says whether to still propose a link know
- baseline run-03 confusing [S9]: A To column can be both a documented key (t1.employeeid has is_natural_key true) and repeating, which makes the To side one and many at the same time. S6 implies repeats win, so I chose many_to_many; unknown (link certain, multiplicity not established) is a plausible alternative the text does not cl
- baseline run-03 confusing [S8]: Says to link each System's tables to that System's own parent by source_systems and to leave the link out when the parent's System cannot be told, but source_systems is empty for every table. I took the Context record's cds_/cym_ group statement as telling the System; the prompt does not say a Conte
- baseline run-03 confusing [S13]: The closing paragraph mentions 'enabled tools' although S1 says there are no tools in one-shot mode. Harmless, but inconsistent.
- baseline run-03 comment: The Context record is the only level-1 evidence and is what makes the link decidable; without it the repeating Bronze key would push S8 (Grain and history) toward leaving the pair out. Cardinality is my weakest call: both employeeid columns repeat across loads, so S6 and S9 give many_to_many even though the business relationship is many contacts to one employee. A one-line rule for multi-load Bronze keys (which cardinality to use, and that an unsupported validation is expected) would remove most of my doubt.

## 2026-10-28 · `baseline-no-context` · fixture `hr_lookalike_groups` · 3 runs

| Measure | baseline |
|---|---|
| Results returned | 3/3 |
| Valid answers (schema) | 3/3 |
| Expected items found | 2/3 (67%) |
| Forbidden items returned | 0 |
| Other items per valid answer | 0.0 |
| Clarity (1–5) | 3.0 |
| Confidence (1–5) | 3.0 |
| Blockers cited | S6 ×3, S8 ×1, S10 ×1 |
| Confusing cited | S8 ×6, S5 ×2, S10 ×2, S4 ×1, S6 ×1 |

Suggested verdict: **baseline only (no studio change for this stage)**

Review notes:
- baseline run-01 blocker [S8]: I believe t2.employeeid -> t1.employeeid (reference, CDS employee) is a real link from the descriptions, but t1 is 'one row per employee per load' (400 distinct in 1200 rows), no current-state table is selected, and there is no Context record, so I found no documented rule and left it out.
- baseline run-01 blocker [S6]: Contradiction rule: t1.employeeid distinct_count (400) is below non_null_count (1200), so it is not a single-column key even though is_natural_key is true; that fails gate items 3 and 5 and removes the 'documented single-column key' premise of evidence order 2.
- baseline run-01 blocker [S10]: A repeating To column can never come back 'supported' (To values must be unique), so this link would be expected to validate as 'unsupported'; this reinforced leaving it out.
- baseline run-01 confusing [S8]: 'a documented rule establishes it' is undefined: do the column descriptions ('Employee this emergency contact belongs to', 'Identifier of the employee in CDS') and the grain statement count, or is a Context record required? The answer flips on this.
- baseline run-01 confusing [S5]: S3 and S5 treat is_natural_key true as a documented single-column key, but S6 says a repeating column is not a single-column key. For a per-load snapshot parent the key flag and the profile conflict, and the rules do not say which wins or whether many_to_many is acceptable for a plain employee lookup.
- baseline run-01 confusing [S8]: The parallel-Systems rule says to use source_systems, but source_systems is [] for every table and the lake System and Connection are identical. Only 'CDS' vs 'CYM' in names and descriptions separates t1 from t4, and the rules never say that wording counts as evidence of the System.
- baseline run-01 comment: The business link is plain from the descriptions; the whole decision turned on whether a per-load snapshot parent whose key repeats (about three rows per employee) may be a target. Please state in S8 what counts as a documented rule and whether a Context record is required. If snapshot parents should be allowed, say so in S6, S9 and S10, including the expected cardinality and that validation will report unsupported.
- baseline run-02 blocker [S6]: Rule that a To column with distinct_count below non_null_count is not a key and cannot be many_to_one pushed t2.employeeid to t1.employeeid to many_to_many (t1 repeats each employee per load), although the business meaning is many contacts per employee.
- baseline run-02 confusing [S8]: Grain and history allows a pair on a repeating key only when a documented rule establishes it, but never defines a documented rule; with no Context records I counted the two employee descriptions plus the is_natural_key flag, and an empty result is also defensible under S1.
- baseline run-02 confusing [S5]: t1.employeeid is a documented single-column key (is_natural_key true, listed in key_columns) but its all_rows profile repeats (400 distinct of 1200); S5 says ideally confirmed, S6 says not a key, S9 says To side is one for a documented key and many for repeating values, and nothing says which wins for inclusion rather than cardinality.
- baseline run-02 confusing [S8]: The parent System must be told by source_systems, which is empty for every table; it is unclear whether CDS and CYM wording in descriptions may tell the System (I used it to pick t1 and drop t4).
- baseline run-02 confusing [S10]: Advice to point at a single-column key so the finding can come back supported cannot be met when the parent keeps one row per load; the finding will validate as unsupported and the prompt does not say whether that is acceptable.
- baseline run-02 confusing [S4]: Operational columns are defined by is_meta_data true, but gds_batch_id is described as the load batch while is_meta_data is false; I treated it as operational (no target exists anyway).
- baseline run-02 comment: The deciding factors were the flagged-but-repeating key in t1 and the undefined documented rule in S8; one sentence saying whether descriptions alone can establish a pair on a history table would remove most of the doubt. An empty list would also follow from S1 (when in doubt, leave it out).
- baseline run-03 blocker [S6]: The rule that a To column with distinct_count below non_null_count cannot be many_to_one kept me from many_to_one for t2.employeeid -> t1.employeeid, which is the business meaning (each contact belongs to one employee); the per-load history forced many_to_many.
- baseline run-03 confusing [S8]: Grain and history allows a pair to a repeating key only when a documented rule establishes it, but a documented rule is never defined. It is unclear whether column and table descriptions count (I relied on them) or only Context records, and it overlaps the evidence tiers in S6.
- baseline run-03 confusing [S8]: Parallel tables pairs Systems by source_systems, which is empty for every table here; CDS and CYM appear only in table names and descriptions. It is unclear whether that is enough to choose t1 over t4 or whether the link must be left out.
- baseline run-03 confusing [S6]: S5 and S9 treat is_natural_key true on t1.employeeid as a documented single-column key (To side one), while S6 says a column with 400 distinct values in 1200 non-null rows is not a key (To side many). The precedence is only implicit.
- baseline run-03 confusing [S10]: Asks to point a reference at a single-column key so a correct finding can come back supported, but a per-load parent like t1 can never validate as supported because its values repeat, so a correct link will be measured unsupported.
- baseline run-03 comment: The reference column and the CDS parent were clear from the descriptions, but the history-grain rules (S6, S8) and the empty source_systems made inclusion a judgment call, and I included the link. S7 has no example of a per-load parent whose key repeats; one would remove most of the doubt, including which cardinality is expected.

