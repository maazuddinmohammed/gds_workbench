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

## 2026-10-28 · `r1-cross_system_reference` · fixture `cross_system_reference` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 6/6 (100%) | 6/6 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 4.7 |
| Confidence (1–5) | 4.0 | 5.0 |
| Blockers cited | – | – |
| Confusing cited | S6 ×3, S9 ×2, S14 ×1, I1 ×1, S7 ×1 | S4.4 ×3, S7 ×2, S14 ×2, S1 ×1, S8 ×1 |

Suggested verdict: **same**

Review notes:
- baseline run-01 confusing [S6]: The 'one parent' bullet says to choose the parent 'in the focus table's source System', but S2 item 3 lets a column hold another System's id when a description says so. For erp_customer_no (a CRM table whose description names the ERP) nothing says which rule wins; I let the description win, but the wording reads like a ban on cross-System links.
- baseline run-01 confusing [S9]: 'Link each System's tables to that System's own parent' and 'never link a table to its look-alike in another System' are about parallel tables. It is not said that a documented cross-System reference from a table that is not a look-alike (contact to ERP customer) is exempt, so a careful reader may hesitate.
- baseline run-01 confusing [S14]: The closing paragraph is generic: it mentions enabled tools, manifests and identities, which do not exist in this one-shot call with no tools (S1).
- baseline run-01 comment: S2 item 3 plus the column description were enough to include the ERP link, but one sentence in S6 saying that a description naming another System overrides the own-System preference would remove the doubt. No Context records were given, so the cross-System decision rests on a single description (S7 evidence order 2). owner_user_id has no user table in key_directory, so it correctly produced no link.
- candidate run-02 confusing [S7]: Tie-break rule 2 (same source System and lake Connection) could be read as favoring CRM table t3 over ERP table t1 for erp_customer_no, because both hold customer accounts. S7 does not say that a description naming another System (S8, S9 item 2) is applied first; I followed S9.
- candidate run-02 confusing [S4.4]: 'every eligible column in full' does not say what makes a column ineligible, so I could not tell whether any focus-table columns were left out. It did not change my answer.
- candidate run-02 confusing [S1]: 'never drop a link only because its evidence is not perfect' reads looser than S9 (four conditions, and similar names or compatible types are never enough alone) and S12 (unmeasurable pairs need a named reference). It did not matter for this input, where the descriptions name both parents.
- candidate run-02 comment: Both links are named by the column descriptions, and S8 correctly warns that the cross-System one (erp_customer_no) is easy to miss. owner_user_id looks like a reference by S6 but the directory has no user table, so I left it out. Adding one sentence to S7 that a description naming another System wins over the same-System tie-break would remove the only real pause I had.
- candidate run-03 confusing [S8]: The first bullet says to link only within the same look-alike group and 'never across groups', and names a schema as one way groups are told apart. Here the ERP and CRM tables sit in different schemas (erp, crm) of one lake Connection, so I briefly wondered whether the cross-System link was barred. I settled it with the cross-System bullet and S9 item 2, but the first bullet states no exception and does not say that a group means a repeated copy of the same tables rather than a different System. Low impact.
- candidate run-03 confusing [S4.4]: 'every eligible column' is never defined, so it is unclear whether some columns can be left out of focus_table and whether a left-out column could still start a link. Low impact here: all eight columns were shown.
- candidate run-03 confusing [S14]: The closing paragraph after the repair list refers to 'enabled tools' and 'Context identities and manifests', but S1 says no tools are available and this input has no identities or manifests. It also repeats S5. Harmless here, but it reads like text from a different prompt.
- candidate run-03 comment: S8's cross-System bullet almost mirrors this input (a CRM contact holding the 'Customer number in the ERP'), so this case checks pattern-following more than judgement on an unfamiliar case. owner_user_id is a real reference, but no user table is in the key_directory, so I dropped it under S3 and S7 without disagreeing with any rule. Both kept links are VARCHAR(10) pairs in the same GDS Connection, so the S12 measurement conditions held.
- candidate run-04 confusing [S14]: The closing paragraph is general output boilerplate under the Repair attempts heading and mentions 'enabled tools', 'manifests' and 'Context identities', which do not exist in this one-shot call (S1 says no tools are available).
- candidate run-04 confusing [S4.4]: 'every eligible column' is not defined, so it is unclear whether the focus table can omit columns or whether all of them are shown.
- candidate run-04 confusing [S7]: Minor: tie-break rule 2 (same source System) could pull a cross-System column such as erp_customer_no toward the CRM account table; only S8 and S9.2 make clear that a description naming another System settles the parent, and S7 does not point to them.
- candidate run-04 comment: Both links were backed by explicit descriptions, identical VARCHAR(10) types and lengths, unique natural keys on the To side and the same lake Connection, so the decision was easy. owner_user_id is a reference column by S6 but no user table is selected, so it was dropped; the output has no way to report such a gap, which looks intended. The cross-System rule in S8 was easy to find and apply.
- baseline run-05 confusing [I1]: Step 3 asks for the parent 'in the same key namespace, source System and lake Connection', which reads as forbidding a parent in another System. S2 item 3 allows another System's id when a description says so, and erp_customer_no says 'in the ERP'. I followed S2.
- baseline run-05 confusing [S6]: 'Choose the one ... in the focus table's source System' and S9's 'that System's own parent by source_systems' have no stated exception for a column whose description names a different System. I read them as applying only when several tables could be the parent.
- baseline run-05 confusing [S7]: Item 3 says source-system boundaries must support the pair but never says what supports crossing one. I took a description naming the other System, plus a documented single-column key on the To side (evidence order 1), as enough.
- baseline run-05 comment: Everything else was clear: account_id is plain, and owner_user_id (a real reference but no user table is selected), status, free text and the date were left out without doubt. One explicit sentence in S6 or S9 saying that a description naming another System allows a link to that System's key would remove the only ambiguity. S8 would also help with a row showing a documented cross-System reference.
- baseline run-06 confusing [S9]: 'Link each System's tables to that System's own parent by source_systems' reads as banning cross-System links, but S2 point 3 and S7 evidence 1 allow them when a description names the other System (erp_customer_no says 'in the ERP'). I followed S2/S7; one sentence saying a description that names another System overrides the same-System preference would remove the doubt.
- baseline run-06 confusing [S6]: 'Choose ... in the focus table's source System' for several possible parents could be read as pointing erp_customer_no at the CRM account table; I treated only the ERP customer table as a candidate because the description names the ERP.
- baseline run-06 comment: I linked contact.account_id to t3.account_id (CRM, same System) and contact.erp_customer_no to t1.customer_no (ERP, named in the description); both are many_to_one into documented unique keys with matching VARCHAR(10) types, lengths and fitting distinct counts. I left out owner_user_id (a user reference, but no user table is shown), status (undescribed code, no code list), contact_id (own key), created_at and the free-text columns.

## 2026-10-28 · `r1-hr_lookalike_groups` · fixture `hr_lookalike_groups` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 3/3 (100%) | 3/3 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 3.7 | 5.0 |
| Confidence (1–5) | 3.0 | 5.0 |
| Blockers cited | S7 ×3 | – |
| Confusing cited | S9 ×4, S6 ×2, S4 ×1, S10 ×1, S7 ×1, S11 ×1, S5 ×1 | S14 ×3, S4.4 ×2 |

Suggested verdict: **same**

Review notes:
- baseline run-01 blocker [S7]: I believe the business meaning of contacts.employeeid to primary.employeeid is many_to_one, but the contradiction rule says a To column with distinct_count below non_null_count (400 vs 1200) 'cannot be many_to_one', so I answered many_to_many. The repeat is only the per-load append described in S2 item 5.
- baseline run-01 confusing [S6]: t1.employeeid is a documented natural key (is_natural_key true) but its profile repeats (400 distinct in 1200 rows). S6 treats the flag as enough (the profile only 'ideally' confirms it), S7 says repeats mean it is not a single-column key, and S10 makes the To side one for a documented key but many when values repeat. For bronze tables that append per load (S2 item 5) every business key repeats, and nothing says which rule wins or which cardinality to give.
- baseline run-01 confusing [S9]: Grain and history says to include the pair only when a documented rule establishes it, but does not say what counts as a rule. I treated the S2 item 5 load rule, the batch_attribute_name field and the 'one row per employee per load' description as enough; a Context record may have been expected.
- baseline run-01 confusing [S9]: Parallel tables says to pick the parent by source_systems and to leave the link out when the parent's System cannot be told. Here source_systems and source_context are empty for every table, while object and attribute descriptions name CDS versus CYM. I used the descriptions to choose t1 over the look-alike t4; it is unclear whether that is allowed.
- baseline run-01 confusing [S4]: batch_attribute_name appears in key_directory and the focus table but is never defined, and S2 calls the load column GDSBatchID while the evidence column is gds_batch_id. Its is_meta_data flag is false although its description says it is a load batch column, so S5 leans on a flag that S4 warns may only mean never set.
- baseline run-01 comment: Choosing t1 over the look-alike t4, and ignoring the employeeid columns of t3, t5 and t6 (not keys), was easy. The hard part is a batch-appended bronze parent: a correct link there can never come back supported under the S4 definition because To values repeat per load, which clashes with S11's advice to aim for supported findings. Please state plainly which cardinality such a link should get.
- candidate run-02 confusing [S4.4]: The focus table is described as the table fields plus every eligible column in full, but nothing says what makes a column eligible; all four columns, including the batch column, were shown here, so I could not tell what would be left out.
- candidate run-02 confusing [S14]: The closing paragraph mentions enabled tools, context identities and manifests, but S1 says no tools exist in one-shot mode and this call has no identities or manifests; harmless here, but it reads like leftover text from another prompt variant.
- candidate run-02 comment: The case is clean: S8 and S7 rule 1 send employeeid to the CDS parent t1 and rule out the CYM copy t4, and no other t2 column is a reference column. The all_rows profile cannot separate repeats caused by loads from several contacts per employee, so many_to_one rests on the S11 default (the From side is many unless it identifies its own rows) rather than on measured data. No rule made me drop a link I believed in.
- baseline run-03 blocker [S7]: The repeat rule bars many_to_one when the To column repeats. I would normally describe 'many contacts per employee' as many_to_one, but the CDS employee key repeats (400 distinct values in 1200 rows), so I used many_to_many.
- baseline run-03 confusing [S9]: It says to link each System's tables to that System's own parent using source_systems, and to leave the link out when the System cannot be told. Here source_systems and source_context were empty for every table, and both employee tables sit in the same Connection with non-unique keys, so only the words CDS and CYM in names and descriptions told them apart. The prompt does not say whether that is enough. I decided it was, because the key description says 'Identifier of the employee in CDS'.
- baseline run-03 confusing [S10]: S6 and S10 make a documented key a 'one' side, but S7 says a key whose values repeat is not a single-column key, and S9 allows a repeating key only when 'a documented rule establishes it' without saying what counts as a rule. I took 'one row per employee per load' in the t1 description as the rule and answered many_to_many; unknown would also be defensible.
- baseline run-03 comment: The step order (S5 to S7) was easy to follow and the S8 table helped. The two points above are the only places where I had to use judgement instead of following a rule. An S8 example for a bronze key that repeats once per load, with the expected cardinality, would remove most of my doubt.
- candidate run-04 confusing [S14]: The last paragraph says to regenerate from 'enabled tools' when previous_candidate_omitted is true, but S1 says no tools exist in one-shot mode. Harmless here because repair is null.
- candidate run-04 confusing [S4.4]: 'The same table fields, plus every eligible column in full' does not name the attributes list the focus table actually uses, and 'eligible' is never defined. All four columns were shown, so it did not affect the answer.
- candidate run-04 comment: employeeid points at t1.employeeid because t1 is in the same cds_ group (S7 rule 1, S8), not at t4 (cym_) or at the employeeid columns of t3, t5 and t6 (S7 Never). Cardinality is many_to_one because S11 says to judge within one load, so repeats from appended loads do not make t1.employeeid many. othercontactname, othercontactpostcode and gds_batch_id were set aside by S6.
- candidate run-05 confusing [S14]: The closing generic paragraph mentions enabled tools, context identities and manifests, and locks, which conflicts with S1 (no tools in one-shot mode) and has nothing to apply to in this input; I ignored it.
- candidate run-05 comment: Only one reference column exists (employeeid); S7 rule 1 and S8 pick the CDS parent t1 and rule out the CYM employee table t4 and t3's own reference column. The batch column, contact name and postcode were set aside under S6. Every rule needed here was explicit, so the case felt unambiguous.
- baseline run-06 blocker [S7]: I believe employeeid -> t1.employeeid is many_to_one (t1.employeeid is a Project natural key and t1 holds one row per employee per load), but the contradiction rule bars many_to_one and one_to_one when the To distinct_count (400) is below its non_null_count (1200), so I answered unknown.
- baseline run-06 confusing [S7]: Conflicts with S2 item 5, S9 (Grain and history) and S10 for a key that repeats only because GDSBatchID loads append rows. S7 calls such a column not a key, S9 allows the pair when a documented rule establishes it, S2 says the highest batch id is current, and S10 gives the To side one for a documented key but many when values repeat. It is unclear whether the natural-key flag or the profile wins, and whether many_to_one, many_to_many or unknown is wanted.
- baseline run-06 confusing [S9]: 'Link each System's tables to that System's own parent by source_systems; when the parent's System cannot be told, leave the link out' - source_systems is [] for every table and source_context is []. I told the CDS group from the CYM look-alike only by the CDS/CYM wording in the descriptions and table names; it is unclear if that counts as the System being told.
- baseline run-06 confusing [S6]: 'Choose the one whose key is unique and current' did not help: the employee keys of t1 and t4 repeat equally (400 distinct of 1200 rows), so only the CDS wording decided the parent.
- baseline run-06 confusing [S11]: 'Point a reference at a single-column key, so a correct finding can come back supported' cannot hold here: S4 says supported needs unique To values, but this bronze key repeats once per load. It is unclear whether validation looks only at the highest GDSBatchID rows.
- baseline run-06 confusing [S5]: gds_batch_id is described as the load batch column but is_meta_data is false, while the operational-column exclusion is worded by the flag. I excluded it by its description and name.
- baseline run-06 comment: The right parent (the CDS table, not the CYM look-alike) was easy to find from the CDS and CYM wording in the descriptions. The hard part was the repeating bronze key, where S7 and S10 point away from what S2 and S9 describe. One sentence in S7 or S10 saying how to treat a key that repeats only through GDSBatchID loads would settle it.

## 2026-10-28 · `r1-multi_instance_keyless` · fixture `multi_instance_keyless` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 3/6 (50%) | 6/6 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 3.7 | 4.3 |
| Confidence (1–5) | 3.0 | 4.0 |
| Blockers cited | S6 ×3 | – |
| Confusing cited | S10 ×3, S7 ×3, S4 ×2, S9 ×2, S2 ×1, S8 ×1, S6 ×1, S5 ×1 | S14 ×2, S9 ×2, S7 ×1, S12 ×1, S10 ×1 |

Suggested verdict: **better**

Review notes:
- candidate run-01 confusing [S7]: A keyless table's identifying column needs 'values that fit', but S4.3 gives other_columns only descriptions and data types, with no profile; S9 item 3 ('To length range') has the same gap. I judged fit from the declared VARCHAR sizes only.
- candidate run-01 confusing [S14]: The last paragraph mentions 'enabled tools' and 'manifests', which clashes with S1 'No tools are available' in this one-shot call; it reads like shared boilerplate.
- candidate run-01 comment: S7 (keyless tables) and S8/S10 (link the id column alone, never the instance column) cover this exact case, so both links were easy to decide. The t3.product_code description is null, so that link rests on the S7 name rule alone. I left out id, line_no, line_status, source_instance and GDSBatchID by the S6 exclusions.
- baseline run-02 blocker [S6]: Third bullet (a table with other_columns has no known key; point at a column only if its own description says it identifies the table's rows) made me drop product_code -> t3.product_code. I believe it is a real reference (From is described 'Product sold on this line', t3 is the product table, both VARCHAR(20), same System), but t3.product_code has a null description and t3 has no key columns.
- baseline run-02 confusing [S2]: S2.3 and S2.5 say an id repeats once per instance in a merged bronze table, while S7 treats a repeating To column as not a single-column key and S9 says not to emit parts of a composite key. The prompt never says whether the instance column counts as part of the parent's key, so I could not tell if order_no -> t1.order_no is a valid single-column reference or half of an (instance, order_no) reference. I treated source_instance as a load column and judged the reference inside one instance, as in the OrderLines.order_id -> Orders.order_id example of S5.
- baseline run-02 confusing [S10]: For a keyless parent whose column is only described as the row identifier, in a table where ids can repeat per instance and per load (S2.5), it is unclear whether the To side is one (many_to_one), many (many_to_many) or the multiplicity is unknown. I chose many_to_one because S6 accepts the described column as the row identifier, but the 'documented single-column key or a rule' wording could be read as requiring more.
- baseline run-02 confusing [S7]: The evidence order names only a documented single-column key as To evidence (item 2), but S6 allows description-only identification for keyless tables, so it is unclear which evidence level order_no -> t1.order_no has. Item 4 also asks for To distinct counts and string lengths, which other_columns never carry (S4), and 'missing evidence is never filled with assumptions' does not say whether that blocks the link or is simply skipped.
- baseline run-02 confusing [S8]: Example 1 uses the same wording as this run's product_code description and shows a link, but it says 'documented key'; here the product table is keyless and its code column is undescribed. I read the example as not applying, yet it pulls toward linking and a keyless counter-example would remove the pull.
- baseline run-02 confusing [S4]: key_directory includes the focus table, but t2 shows empty key_columns and other_columns even though its id column has an all_rows profile with distinct_count equal to non_null_count, which S4 says makes a key column. Minor, but it makes the directory entry for the focus table look unreliable.
- baseline run-02 comment: The steps in S5 to S7 and the I1 checklist were easy to follow, and the product_code case was settled by the explicit S6 rule. The hard part was the one candidate link (order_no) in a keyless, multi-instance parent, where S2.5 and S7/S9/S10 point different ways. A worked example of a described-but-unflagged identifier in a merged bronze table, with its expected cardinality, would settle it.
- baseline run-03 blocker [S6]: Left out product_code -> t3.product_code, which I believe is a real reference: t3 has no key columns, its product_code has a null description and no Context record exists, so the keyless-table rule (the column's description or a Context record must say it identifies the table's rows) is not met, and a name alone is only a lead (S5).
- baseline run-03 confusing [S10]: The To side is 'one' only for a documented single-column key or a rule of unique values, but S6 lets me point at a keyless table's column on its description alone (t1.order_no 'Sales order number.'); unclear if that counts as documented, so many_to_one versus unknown was a judgment call.
- baseline run-03 confusing [S9]: S2 items 3 and 5 say ids repeat once per instance and bronze keeps several rows per record (GDSBatchID), while S9 says not to emit parts of a composite key and that a repeating To key needs a documented rule; unclear whether a multi-instance, history-keeping bronze parent may be linked on the id column alone (here t1 also has source_instance).
- baseline run-03 confusing [S7]: Item 4 says missing evidence is never filled with assumptions, but keyless tables show no profile in other_columns, so the To distinct-count and length checks can never be run; unclear whether that blocks the link or counts as neutral.
- baseline run-03 confusing [S4]: It says key_directory lists the focus table too, with other_columns when it has no key columns, but t2 shows empty key_columns and empty other_columns although its id profile is fully distinct.
- baseline run-03 comment: I linked only order_no, because both sides have plain descriptions, identical VARCHAR(12) types and the same System and lake Connection; product_code is probably a real reference but its parent key is undocumented. The first example in S8 is almost word for word this input's product_code description, which makes it tempting to link without the 'documented key' condition. A short rule on how to treat the instance column when linking a multi-instance bronze child to its parent would remove my main doubt.
- candidate run-04 confusing [S12]: S12 and S4.6 say a correct finding should come back supported, and unsupported means To values repeat. S8, S9 and S10 still say to link to a parent whose id repeats once per instance, and S12 only says repeats across loads are fine, not repeats across instances inside one load. It is unclear whether such a link can be measured as supported; I followed S8 and S10 and linked.
- candidate run-04 confusing [S10]: 'When the referenced key is composite, do not emit its parts as separate findings' does not say whether the composite key is on the From side or the To side. The last sentence (the instance column completes the key, link the id column alone) settles this input, but I had to infer that.
- candidate run-04 confusing [S9]: The checks on the To length range and on distinct counts need a To profile, but the keyless parents (t1, t3) list only other_columns with descriptions and types, no profile. The prompt does not say what to do then; I used the declared VARCHAR sizes, names and descriptions.
- candidate run-04 comment: Both links were clear from S6 step 1 (order_no and product_code have descriptions naming another entity), S7 (keyless parent: pick the entity-plus-identifier column) and S8 (several instances in one Bronze table: link the id column alone). I left out id, line_no, quantity, net_amount, line_status, delivery_date, source_instance and GDSBatchID under S6, and there were no Context records or saved findings. Both pairs have the same registered VARCHAR type and the same lake Connection, so Validate can measure them under S12.
- candidate run-05 confusing [S9]: Rule 3 (From string lengths within the To length range) and the 'more distinct From values than To values' check need a profile of the To column, but S4.3 gives other_columns only a description and data types. For keyless parents like t1 and t3 these checks cannot be run; I treated that as no contradiction.
- candidate run-05 confusing [S14]: The closing paragraph mentions 'enabled tools' and 'manifests', but S1 says no tools are available in one-shot mode and no manifests appear in the input; I ignored those parts.
- candidate run-05 comment: Every column of the focus table was settled by a specific rule: S6 for the exclusions (id, line_no, measures, status, date, instance and batch columns), S7 for keyless parents and S8/S10 for the multi-instance Bronze tables. The pairing of product_code with t3.product_code rests on the column name and the From description only, because the To column has no description. Neither To column has a profile, so the length and distinct-count checks in S9 were not possible.
- baseline run-06 blocker [S6]: t3.product_code looks like the parent of order_line.product_code (From says 'Product sold on this line', both VARCHAR(20), lengths 6-14 fit, t3 is the product table), but t3 is keyless and the column description is null, so the keyless-table rule stops me from pointing at it. I left it out although I think it is real.
- baseline run-06 confusing [S9]: With S2 items 3 and 5 (ids repeat once per instance; GDSBatchID appends versions), t1.order_no alone is not unique: the real key is source_instance + order_no (+ current batch). S9 says not to emit parts of a composite key and S11 wants a single-column key, yet S2 and S6 imply the lake-level pair is wanted. I could not tell whether an instance-scoped key counts as composite (then the output would be empty). I emitted the pair, using the highest-GDSBatchID rule in S2 item 5 as the documented rule for grain.
- baseline run-06 confusing [S6]: The keyless rule needs a description that 'says it identifies the table's rows'. 'Sales order number.' does not say this literally; I accepted it. S7 evidence order 2 asks for a documented single-column key, which a keyless table can never have, so it is unclear which evidence level a description-only keyless pair reaches.
- baseline run-06 confusing [S7]: Check 4 compares distinct counts and lengths with the To column, but keyless other_columns have no profile. 'Missing evidence is never filled with assumptions' reads either as a veto on every keyless pair or as 'no corroboration'. I took the second reading.
- baseline run-06 confusing [S10]: The To side is 'one' only for a documented single-column key or a rule that each value occurs once. A keyless column accepted by description is neither, and S2 says bronze ids can repeat, so many_to_one versus unknown is unclear. I chose many_to_one (From side repeats: 61,000 distinct of 240,000 rows; S8 example).
- baseline run-06 confusing [S5]: The never-start list does not name instance columns, and source_instance has is_meta_data false. I set it aside because it is not a reference column and no listed table is its entity.
- baseline run-06 comment: The only real judgement call was order_line.order_no to t1.order_no (keyless target, description 'Sales order number.', two source instances, no profile on the target). One sentence in S6 or S9 saying whether a description like 'X number' counts as identifying the rows, and whether a per-instance id still counts as a single-column key, would remove most of my doubt. Everything else (id, line_no, measures, dates, line_status, source_instance, GDSBatchID) was clearly out.

## 2026-10-28 · `r2-hr_lookalike_groups` · fixture `hr_lookalike_groups` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 0/3 | 3/3 |
| Valid answers (schema) | 0/3 | 3/3 |
| Expected items found | 0/0 (–) | 3/3 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | – | 0.0 |
| Clarity (1–5) | – | 5.0 |
| Confidence (1–5) | – | 5.0 |
| Blockers cited | – | – |
| Confusing cited | – | S7 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-01 comment: With source_context, source_systems and context_records all empty, the cds_/cym_ prefixes and the 'in CDS' wording of the t1 key description were the only grouping evidence, and S7 and S8 handled that cleanly. The batch-repeating t1 key still counts as the 'one' side per S9 and S11, which I applied as written. I left out the name, postcode and batch columns under S6 without any doubt.
- candidate run-02 comment: The cds_/cym_ look-alike rules (S7 rule 1, S8) and the batch-column exclusion (S6) decided this input directly, and the S11 cardinality rule was easy to apply. In the focus table gds_batch_id has is_meta_data false, so only S6's explicit 'the batch column' wording excludes it. With source_systems empty, S8's last bullet (use names, schemas and descriptions) is what lets the groups be told apart.
- candidate run-03 confusing [S7]: Tie-break 4 prefers a key that identifies rows on its own over one that repeats, while S9 says a key that repeats once per load is still linkable. It is unclear whether per-load repeats count as repeats in tie-break 4. It did not affect this answer because t1 and t4 both repeat the same way and tie-break 1 already decided.
- candidate run-03 comment: Straightforward case: only employeeid is a reference column, and S7 tie-break 1 (same look-alike group, cds_ prefix) picks t1 over t4. The groups were visible only from the name prefix because source_systems and source_context are empty, which the last bullet of S8 covers. gds_batch_id has is_meta_data false, so it was excluded only through the 'batch column' bullet in S6.

## 2026-10-28 · `r2-cross_system_reference` · fixture `cross_system_reference` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 0/3 | 3/3 |
| Valid answers (schema) | 0/3 | 3/3 |
| Expected items found | 0/0 (–) | 6/6 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | – | 0.0 |
| Clarity (1–5) | – | 5.0 |
| Confidence (1–5) | – | 5.0 |
| Blockers cited | – | – |
| Confusing cited | – | S9 ×1, S1 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-01 confusing [S9]: Minor, did not affect this input: tier 2 accepts a name that ties the From column to an entity, but tier 3 says 'similar names' are never enough alone, S6 says a name is never enough on its own, and S1 says not to drop a link for imperfect evidence. For a name-only match with no description it is unclear which rule wins.
- candidate run-01 comment: Both links rest on an attribute description that names the parent (the CRM account; the contact's company in the ERP), and S8's cross-System rule settled erp_customer_no even though no Context record was given. owner_user_id looks like a reference to a CRM user, but no user table is in the key directory, so S3 leaves it out; status has no code-list table (S6). Each decision traced to one section, which made the prompt easy to apply.
- candidate run-03 comment: Clear for this input: the ERP wording on erp_customer_no matches the S8 cross-System rule and the S7 'decides first' sentence, so no tie-break was needed. owner_user_id reads like a reference to a CRM user, but no user table is in the key directory, so I left it out (S9 point 1).
- candidate run-06 confusing [S1]: S1 says to include a link when one parent is clearly the most plausible even if evidence is imperfect, while S9 says name or type similarity alone is never enough; the two can pull apart for name-only matches. It did not affect this input because both links had direct column descriptions.
- candidate run-06 comment: Both links follow directly from the column descriptions plus natural-key flags on the targets, and the cross-System paragraph in S8 made erp_customer_no easy to place. I left out owner_user_id because no CRM user table is in the key directory (S3, S7), and status as an undocumented code column (S6). Both pairs are VARCHAR(10) in the same GDS Connection, so Validate can measure them (S12).

## 2026-10-28 · `r2-multi_instance_keyless` · fixture `multi_instance_keyless` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 0/3 | 3/3 |
| Valid answers (schema) | 0/3 | 3/3 |
| Expected items found | 0/0 (–) | 6/6 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | – | 0.0 |
| Clarity (1–5) | – | 4.3 |
| Confidence (1–5) | – | 4.3 |
| Blockers cited | – | – |
| Confusing cited | – | S10 ×2, S4.3 ×2, S9 ×2, S7 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-02 confusing [S10]: The composite-key rule says not to emit parts of a parent's composite key, then says that for multi-instance tables the instance column completes the key and the id column is linked alone. Here t1.order_no is such a part, so it reads like a conflict until the last sentence; stating it as an explicit exception to the first rule would help.
- candidate run-02 confusing [S7]: For a keyless parent the key column needs 'values that fit', but other_columns have no profile and S9 says to skip length and count checks, so only data types can be compared; it is unclear what else counts as a fit.
- candidate run-02 confusing [S4.3]: other_columns is described as every column of a table without key columns, yet the focus table t2 shows key_columns [] and other_columns []; its columns are only in the focus table's attributes, which the reader has to infer.
- candidate run-02 comment: Both parents were keyless tables, and S6, S7, S8, S10 and S11 together gave one answer: two many_to_one references, with the instance column left out. source_instance has is_meta_data false, so only its description and its position before the technical column (S2 point 5) mark it as the instance column that S6 excludes. The undescribed t3.product_code was accepted only through the S7 name rule, which worked but is the weakest evidence in the answer.
- candidate run-04 confusing [S4.3]: Says other_columns lists every column of a table without key columns, but the focus table t2 shows key_columns [] and other_columns [] with its columns only in focus_table.attributes; I assumed S4.4 is the source for the focus table and it did not change the answer.
- candidate run-04 confusing [S9]: Criterion 2 asks for the same group, instance and System, which reads as if it conflicts with a Bronze table that holds several instances; S8 and S10 resolve it (link the id column alone), but S9 does not point to them.
- candidate run-04 comment: The only soft call was product_code to t3.product_code: t3 has no key flag, no description on that column and no profile, so it rests on the entity-plus-identifier name (S7) and the From description, and S1's include-when-most-plausible rule settled it. The multi-instance handling (link the id column alone, never source_instance) is clearly stated in S8, S10 and S12. No changes needed beyond the two minor notes above.
- candidate run-05 confusing [S9]: Criterion 2 asks for the same group, instance and System, which read alone seems to rule out linking inside a Bronze table that mixes ORD_UK and ORD_DE rows; S8 (Several instances in one Bronze table) and S10 settle it, but only if the reader connects them.
- candidate run-05 confusing [S10]: The Composite keys rule says not to emit parts of a composite parent key, then its last sentence says to link the id column alone when the instance column completes the key; the exception is easy to read as contradicting the first sentence.
- candidate run-05 comment: The order_no link rests on a clear description and on the OrderLines.order_id example in S6. The product_code link is the thinnest: the parent column t3.product_code has no description and no profile, so it is accepted only through the S7 name rule, and one sentence there saying a null description is fine for a keyless parent would remove my one real hesitation.

## 2026-10-28 · `r4-legal` · fixture `legal_entity_list` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 3/9 (33%) | 9/9 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 4.0 | 3.7 |
| Blockers cited | S7 ×3, S6 ×1, S2 ×1 | – |
| Confusing cited | S5 ×5, S4 ×1, S2 ×1, I1 ×1, S7 ×1 | S6 ×4, S9 ×1, S5 ×1 |

Suggested verdict: **better**

Review notes:
- candidate run-01 confusing [S9]: The evidence order does not say whether an undocumented, abbreviated column such as `cost_ctr` (no description, no Context record, no identifier word in the name) can be linked: tier 2 asks for an entity plus an identifier word, tier 3 says type and length fit is never enough alone, yet S1 and the last line of S9 say to include when nothing contradicts and no shown column fits better. I linked it because the RD System description names cost centers and the profile fits exactly (VARCHAR(8), 8 characters, 380 of 410 distinct).
- candidate run-01 confusing [S6]: Rule 2 needs an identifier word (id, no, num, number, code, key, ref), which `cost_ctr` lacks; only rule 3 and the 'whole picture' wording in S8 can make it a reference column, and they do not say how much evidence is enough or whether System descriptions count as evidence.
- candidate run-01 comment: Links: legal_entity_name to the RD name column (name to name, S7), cost_ctr to the RD cost center code, and manager_id to employee_id of the same table, all many_to_one. The cost_ctr link is the one real judgment call, and the legal entity case is almost word for word the example in S2 and S8. Other columns were left out as own key, free text, date, status, or a country code with no country table shown.
- baseline run-02 blocker [S6]: employee.legal_entity_name (described as the name of the employing legal entity) matches legal_entity.legal_entity_name on type, length range 9-38 and distinct count (12 of 14), so I think it is probably a real reference by name. I left it out because S5 bars starting a link at names, S6 says a unique name is not a key and never to point at descriptive columns, and the real key legal_entity_code (VARCHAR(6)) has no matching column in the focus table.
- baseline run-02 blocker [S7]: employee.cost_ctr to cost_center.cost_center_code (both VARCHAR(8), length 8, 380 of 410 distinct, similar name) looks right to me, but the column has no description and context_records is empty, so only level-3 corroboration exists, which S7 says is never enough alone. S2 item 3 (another System's ids need a description or Context record; HR vs RD) and S5 rule 2 (the name has no identifier word) point the same way.
- baseline run-02 confusing [S5]: Rule 1 makes a column a reference when its description names another entity, yet the Never list excludes names. It does not say whether that covers a controlled name column such as legal_entity_name (12 distinct values over 8,200 rows) or only free-text names such as a person's name.
- baseline run-02 confusing [S4]: key_columns admits any column with a unique profile, while S6 says a unique name is not a key unless its description says it identifies the table's rows. It is unclear whether 'Registered name of the legal entity' counts as identifying.
- baseline run-02 confusing [S2]: Not stated whether a System description (RD: 'the legal entities and cost centers of the group') counts as the description that can tie a column to another System's entity.
- baseline run-02 comment: The rules are detailed and mostly consistent, and the empty Context records made the decisions conservative: only the self-reference manager_id is certain. The doubtful cases (a name-based reference, an abbreviated column name, a cross-System code list) depend on how strictly 'name' and 'description' are read, and one explicit line on each would remove the doubt. The closing paragraph of S14 repeats S13, which is harmless but redundant.
- candidate run-03 confusing [S6]: Rule 2 needs an entity plus an identifier word (id, no, num, number, code, key, ref) and S9 evidence item 2 repeats that, but cost_ctr is an abbreviated entity name with no identifier word and no description. Only rule 3 (it holds the codes of another System's list) can cover it, and S9 item 3 says matching lengths alone are never enough, so it is unclear whether an abbreviation like 'ctr' counts as a clear name.
- candidate run-03 confusing [S5]: `to` must use the table id from <key_directory>, but nothing says outright that a self-reference such as manager_id cites the focus table's own id (t4). S3 and S10 imply it and I took the id from <focus_table>.
- candidate run-03 comment: legal_entity_name (S6 rule 3, S7 like-for-like name link, S8 example) and manager_id (S10 self-reference) followed directly from the rules. The one judgment call was cost_ctr: I linked it because S1 and S8 favour recall and its profile fits the cost center key exactly (VARCHAR(8), length 8, 380 of 410 values), but one sentence on abbreviated names without an identifier word would remove the doubt. I left country_code and status unlinked only because no country or status list is in the key directory.
- baseline run-04 blocker [S7]: cost_ctr -> t2.cost_center_code probably is a real reference (VARCHAR(8) on both sides, every value 8 characters, 380 distinct <= 410, name is an abbreviation of cost center), but the column has no description, there are no Context records, and the parent is in another System (S2 point 3), so the evidence is only corroboration (S7 evidence order 3, gate 5) and the name has no identifier word (S5 criterion 2). I left it out as the rules direct.
- baseline run-04 confusing [S5]: legal_entity_name has a description saying it belongs to another entity (criterion 1), yet names are on the never-start list. The text does not say which wins; I assumed the never-start list does (and S6 also bars pointing at a name, and the documented key is a 6-character code).
- baseline run-04 confusing [S5]: Criterion 2 asks for an entity plus an identifier word. cost_ctr has an abbreviated entity name ('ctr') and no identifier word, so it is unclear whether it even counts as a name lead to check.
- baseline run-04 confusing [I1]: Step 3 asks for the same source System as the focus table, while S2 point 3 allows another System's ids when a description or Context record says so. It is unclear whether a documented cross-System reference (HR to RD) may be proposed.
- baseline run-04 comment: The sort, then target, then gate order was easy to follow and gave one clear link (manager_id to t4.employee_id, a self-reference). The fixture looks built so that legal_entity_name matches t1.legal_entity_name on every profile check while being a name against a code key, and cost_ctr fits every value check while having no description, so I excluded both. One sentence saying whether a name-only abbreviation without an identifier word can ever be a reference column would remove the main judgement call.
- baseline run-05 blocker [S7]: cost_ctr -> t2.cost_center_code: I think this is probably a real reference (abbreviated name, VARCHAR(8) like the key, every value 8 characters, 380 distinct against 410 keys, key is unique), but there is no description and no Context record, so only evidence level 3 (corroboration) exists and gate item 5 ('you are sure') fails. I left it out.
- baseline run-05 blocker [S2]: Item 3 says a column holds another System's id only when a description or Context record says so. cost_ctr is in HR, cost_center is in RD, its description is null and there are no Context records, so the cross-System pair is blocked.
- baseline run-05 confusing [S5]: legal_entity_name: its description (the legal entity that employs this person) fits reference rule 1, but names are on the never-start list, and S6 forbids pointing at name columns even though S4 lists t1.legal_entity_name under key_columns just for being unique. I resolved it as no link, but a name that really identifies an entity sits between rule 1 and the never-list.
- baseline run-05 confusing [S5]: Rule 2 wants an entity plus an identifier word in the name. cost_ctr is an abbreviated entity with no identifier word, so it is unclear whether it counts as a lead worth checking at all.
- baseline run-05 confusing [S7]: Evidence level 2 needs a description or Context record that ties the focus table to the entity, but does not say whether loosely matching object descriptions ('Employees of the group', 'Cost centers of the group') count. I did not count them.
- baseline run-05 comment: manager_id -> t4.employee_id is the only link backed by a description, a documented unique key, and matching type, length and counts. The two near-misses (legal_entity_name, cost_ctr) pass every profile check, so the decision rested entirely on the evidence rules, and I read them as excluding both. If cost_ctr is meant to be linkable, the rules need to say how an undocumented abbreviated name in one System ties to another System's key.
- candidate run-06 confusing [S6]: cost_ctr names an entity by abbreviation but has no identifier word and no description. Rule 2 asks for an entity plus an identifier word, S9 says data fit alone (types, lengths) is never enough, yet S1, S6 rule 3 and S8 say to link on the whole picture even when evidence is not perfect. It is unclear whether such a name counts as a clear name; I linked it because the RD System description mentions cost centers and the lengths and counts fit exactly.
- candidate run-06 confusing [S6]: Step 1 says to classify reference columns before looking for targets, but rule 3 (the column holds the code or name by which a list identifies its rows) can only be judged after finding that list in the key directory, so Step 1 and Step 2 overlap for cross-System references.
- candidate run-06 comment: The prompt is long but well ordered, and the legal entity example in S2, S7 and S8 maps directly onto this input, so the name-to-name link and the manager self-reference were easy. country_code looks like a reference but no country table is shown (S3), and status has no description and no list table, so both are left out. The only real judgment call was cost_ctr.

## 2026-10-28 · `r4-xsys` · fixture `cross_system_reference` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 6/6 (100%) | 6/6 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 5.0 |
| Confidence (1–5) | 4.0 | 5.0 |
| Blockers cited | – | – |
| Confusing cited | S9 ×3, S6 ×3, S7 ×1 | – |

Suggested verdict: **same**

Review notes:
- candidate run-01 comment: Everything needed was in the evidence: account_id points at the CRM account key and erp_customer_no at the ERP customer key, matching the S8 cross-System example. owner_user_id looks like a reference to a CRM user list, but no user table is shown (S3), so I left it out. The S7 same-System tiebreak and the S9 item 1 same-System default could pull erp_customer_no toward t3, but its description naming the ERP settles it.
- candidate run-02 comment: The S8 example (`erp_customer_no` linking to the ERP customer table) nearly matches this input, so this case cannot show whether S6 rule 3 and S9 point 1 alone would lead a model to the cross-System link. `owner_user_id` is a reference column (CRM user) but no user table is in the key directory, so it is left out under S3 and S9. S8 says to judge cross-System links from the whole picture without saying how much evidence is enough, which did not matter here because the description names the ERP.
- candidate run-03 comment: owner_user_id is a reference column by its description (the CRM user who owns the contact), but no user table is shown, so I left it unlinked per S3 and S9, which seemed intended rather than a blocker. The S8 example (a CRM account's erp_customer_no links to the ERP customer table) nearly mirrors this input, so passing here is weak evidence for harder cross-System cases; the column's own description naming the ERP is what decided it for me. Nothing says whether a contact's own copy of an ERP key should still be linked when the CRM account probably carries it too, and I linked it because its de
- baseline run-04 confusing [S9]: The parallel-tables rule (link each System's tables to that System's own parent, never to a look-alike in another System) can be misread as forbidding erp_customer_no -> the ERP customer table. Only S2 item 3 and S7 evidence order 1 make it clear that a description naming another System's id allows a cross-System link; S9 does not say so.
- baseline run-04 confusing [S6]: The bullet that says to choose the parent in the focus table's source System (and I1 step 3, 'same key namespace, source System and lake Connection') conflicts with a documented cross-System reference. I read it as applying only when several parent tables compete for one column.
- baseline run-04 comment: I returned account_id -> t3.account_id and erp_customer_no -> t1.customer_no, both reference and many_to_one; the second rests on its description naming the ERP (S2 item 3, S7 evidence order 1) with matching VARCHAR(10) types, 3900 <= 5000 distinct values and equal lengths. owner_user_id is a described reference but no user table is in key_directory, so it was left out, and the remaining columns are the own key, free text, a status code or a timestamp. S8 has no example of a documented cross-System reference, which is the one judgment call in this input.
- baseline run-05 confusing [S9]: 'Link each System's tables to that System's own parent' reads as same-System only, but S2.3 allows another System's id when a description says so. Nothing says outright that a documented cross-System reference (erp_customer_no, described as the ERP customer number) may be linked; I relied on S2.3 and evidence tier 1 of S7.
- baseline run-05 confusing [S6]: The tie-break 'in the focus table's source System' would favour the CRM account for a customer-number column; it is unclear that it does not apply when the description names the other System.
- baseline run-05 confusing [S7]: Gate item 3 says source-system boundaries must 'support' the pair but does not say what counts as support when the pair crosses Systems.
- baseline run-05 comment: The other columns fell cleanly under S5 exclusions (own key, free text, timestamp, status code without a code table), and owner_user_id has no user table to point at. Both links pass S11 measurability (same VARCHAR(10) type, same lake Connection). A one-line statement in S9 or S6 that a description-documented cross-System id links to the named System's key would remove my only real judgement call.
- baseline run-06 confusing [S6]: The tie-break for several possible parents lists 'the customer tables of two Systems' and says to choose the one 'in the focus table's source System'. That reads as applying directly to erp_customer_no (ERP customer vs CRM account) and would point to the CRM table, yet the column description says it is an ERP customer number. I resolved it with S2 item 3 and S7 evidence order 1 (a description naming the reference wins), but the text never says an explicit description overrides the same-System tie-break.
- baseline run-06 confusing [S9]: 'Link each System's tables to that System's own parent by source_systems' is ambiguous for a column that explicitly holds another System's id: it could mean a cross-System link is never allowed. S7 item 3 ('source-system boundaries ... support this exact column pair') and S8 give no worked example of a documented cross-System reference; the only example (Orders.region_id) is the undocumented case.
- baseline run-06 comment: Both links were well supported: each description names its parent, registered types and lengths match, From distinct counts are below To distinct counts, and the To keys are unique all_rows keys in the same lake Connection. owner_user_id refers to a CRM user, but no user table is selected, so it gets no link. One worked example of a documented cross-System reference in S8 would remove the only hesitation.

## 2026-10-28 · `r4-keyless` · fixture `multi_instance_keyless` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 3/6 (50%) | 6/6 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 5.0 |
| Confidence (1–5) | 3.0 | 4.3 |
| Blockers cited | S6 ×3, S10 ×2, S7 ×1 | – |
| Confusing cited | S7 ×3, S6 ×3, S9 ×3, S10 ×2 | S6 ×4, S11 ×1, S10 ×1, S9 ×1, S4.3 ×1 |

Suggested verdict: **better**

Review notes:
- candidate run-01 confusing [S6]: `line_no` ('Line number within the order') fits the rule 1 wording (belongs to another entity) and the rule 2 name pattern (entity plus 'no'), but it is only a position counter. The 'Never start a link at' list has no item for sequence or position numbers; I excluded it as part of the focus table's own composite key (order_no + line_no), which no key flag marks and which I had to infer.
- candidate run-01 confusing [S6]: `source_instance` has is_meta_data false. Recognising it as 'the instance column of a table loaded from several instances' needs its description plus the two-instance ingestion_mapping; the rule does not say how to spot an instance column that is not flagged.
- candidate run-01 confusing [S11]: t1 and t3 have no key columns and no profiles, so their To column is known to identify rows only from its name (S7). S11 does not say whether that is enough for the To side `one` (many_to_one) or whether `unknown` is expected; I used many_to_one.
- candidate run-01 comment: S7's keyless-table bullet (entity plus identifier word, even with no description) and S8's instance rule settled both links without hesitation. Every decision traced to one short rule, though the prompt is long for an input with two links. Cardinality for unprofiled parents is the only place I was guessing at the intent.
- candidate run-02 confusing [S10]: The composite-keys rule speaks of the parent's key being composite, but here the focus table's own key (order_no plus line_no) is the composite one; I relied on S6 (OrderLines.order_id to Orders.order_id) and the S8 instance exception to emit order_no alone. The answer was not affected.
- candidate run-02 confusing [S9]: Repeating To values refers to a key-flagged To column, but in keyless tables (S7) the To column is identified only by name or description and has no profile. I treated the S7 identifying column as To side one per S11.
- candidate run-02 confusing [S6]: Rule 2 (entity plus identifier word no) literally matches line_no; only the never-start list (focus table's own key) and its position-in-order meaning rule it out.
- candidate run-02 comment: Both links came directly from the keyless-table rule in S7 (name is the table's entity plus an identifier word; product_code needs no description). The instance and composite-key guidance is spread over S8, S10 and S11 and agrees, but the reader has to reconcile three places. One worked example of a keyless To table with its To side stated as one would remove my small doubt about cardinality.
- baseline run-03 blocker [S6]: t3 (product) has no key columns and its product_code description is null, so nothing says that column identifies product rows. I left out product_code -> t3.product_code although the matching name, the same VARCHAR(20) type, the focus description 'Product sold on this line.', the table description and the 2,900 distinct codes of length 6 to 14 make it very likely real.
- baseline run-03 confusing [S7]: Item 4 asks for the To distinct_count and string-length range and says missing evidence is never assumed, but S4 says other_columns carry no profile. Read strictly, no keyless table could ever pass, which contradicts S6 allowing a pointer at a described column. I treated the matching VARCHAR(12) types plus the descriptions as enough for t1.order_no.
- baseline run-03 confusing [S6]: 'Sales order number.' names the column but does not say it identifies or is unique per row of t1. It is unclear whether that is enough for a keyless table. I accepted it because it is the only identifier-like column of a table described as customer sales orders.
- baseline run-03 confusing [S9]: t1 and t2 both mix two instances (source_instance column) and t1 appends by GDSBatchID. S2.3, S2.5 and S9 say ids repeat per instance and history repeats keys, but nothing says whether the instance column makes the key composite (so do not emit) or whether the single-column pair is still wanted. I emitted the single pair.
- baseline run-03 confusing [S10]: The To side is one only for a documented single-column key or a rule saying each value occurs once, and keyless t1.order_no has neither, so many_to_one versus unknown is unclear. I used many_to_one because the From side repeats (61,000 distinct in 240,000 rows) and the description names the order number.
- baseline run-03 comment: The prompt is clear for keyed tables, but a keyless, multi-instance, append-loaded target gives different answers under S6, S7 item 4, S9 and S10 for the same pair. One sentence saying what evidence is enough when the To table has no key and no profile, and whether the instance column counts as part of the key, would settle it. The product_code exclusion is clean by S6 but costly when every other signal agrees.
- baseline run-04 blocker [S6]: Keyless clause: I left out product_code -> t3.product_code although I believe it is a real reference (From is described as the product sold, t3 is the products table, both are VARCHAR(20), From lengths 6-14 fit). t3.product_code has a null description and there are no Context records saying it identifies the table's rows, so the rule forbade pointing at it.
- baseline run-04 blocker [S10]: I believe the order_no link is many_to_one in business terms, but the To side counts as `one` only for a documented single-column key or a stated uniqueness rule. A keyless table has neither, so I used `unknown`.
- baseline run-04 confusing [S7]: Item 4 asks for the To distinct_count and string-length range, but S4 says keyless tables show only descriptions and data types in other_columns. These checks cannot be run for the very tables S6 allows pointing into. It is unclear whether a missing profile blocks the link (missing evidence is never filled with assumptions) or only means there is no contradiction.
- baseline run-04 confusing [S9]: S2 says bronze tables with an instance column and GDSBatchID can repeat ids per instance and per load. It is unclear whether that makes the To key composite (source_instance + order_no), so that order_no alone should not be emitted, or whether it makes every bronze To side `many` under S10.
- baseline run-04 confusing [S6]: Says it identifies the table's rows: not clear how explicit the To description must be. I accepted 'Sales order number.' as enough, but a similar short description would be borderline.
- baseline run-04 comment: The keyless case needed three interpretation calls: what counts as a description that identifies rows, which S7 checks apply without a profile, and the cardinality of a keyless To side. A worked keyless example in S8, with one accepted pair and its cardinality and one declined pair whose target column has no description, would remove the guesswork.
- candidate run-05 confusing [S4.3]: Says a column whose profile is fully distinct belongs in key_columns and that the focus table is included, yet t2 shows key_columns [] although its id column is 100% distinct; no effect on the answer because id is technical.
- candidate run-05 confusing [S6]: Rule 2 (entity plus identifier word) also fits line_no, and the Never list has no entry for sequence or position numbers; I relied on the opening definition (values must identify rows of another entity) and its description to skip it.
- candidate run-05 comment: Both targets are keyless tables, so the S7 name rule for other_columns decided each link, and the S8/S10 instance-column exception made linking order_no alone clear. Cardinality followed S11: many order lines per order and many lines per product, with the To column identifying its table's rows. The instructions were easy to follow for this input.
- baseline run-06 blocker [S6]: Keyless To table t3: product_code has a null description and there are no Context records, so the rule 'point at an other_columns column only when its description or a Context record says it identifies the table's rows' made me omit product_code -> t3.product_code. I believe it is a real reference (same name, VARCHAR(20) on both sides, From lengths 6-14, From description 'Product sold on this line').
- baseline run-06 blocker [S7]: Evidence order puts name, data type and length fit in tier 3 ('never enough alone') and item 5 asks for deciding evidence, so nothing could decide the product_code pair; same omission as the S6 item.
- baseline run-06 blocker [S10]: The To side is 'one' only for a documented single-column key or a rule that each value occurs once. t1.order_no is a keyless column chosen from its description, so I could not say many_to_one (many lines, one order), which I believe is the true business multiplicity, and used unknown.
- baseline run-06 confusing [S6]: Unclear how explicit a keyless To description must be. 'Sales order number.' does not literally say it identifies the table's rows; I accepted it because it names the identifier of the table's own entity ('order number' is an identifier word in S5).
- baseline run-06 confusing [S7]: S7.4 asks for To distinct_count and a To length range, but keyless tables only have other_columns with no profile. 'Missing evidence is never filled with assumptions' can mean 'no contradiction found' or 'the gate fails'; I took the first, otherwise no keyless link could ever pass.
- baseline run-06 confusing [S9]: S2 items 3 and 5 say bronze ids repeat per instance and per load, so the real bronze key looks like (source_instance, id) with repeated rows. S9 says not to emit parts of a composite key and to include a repeating To key only when a documented rule establishes it. It is unclear whether this blocks single-column links into multi-instance bronze tables; I treated S2 item 5 as the rule and the instance as scope, not a key part.
- baseline run-06 confusing [S10]: Unclear whether a keyless column chosen through S6 counts as 'documented' for the To side, and whether the bronze repeat rules ('a rule allows repeats') push the To side to many, which would give many_to_many. I chose unknown as the only value I could defend.
- baseline run-06 comment: S6, S7 and S10 handle keyless target tables only implicitly. One explicit sentence on what a keyless To column needs (how its description must read, whether a profile is required) and which cardinality to use would remove most of my doubt. The data landscape (S2) and the not-a-reference list (S5) were very clear.

## 2026-10-28 · `r4-hr` · fixture `hr_lookalike_groups` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 3/3 (100%) | 3/3 (100%) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 5.0 |
| Confidence (1–5) | 3.0 | 5.0 |
| Blockers cited | S7 ×3 | – |
| Confusing cited | S9 ×5, S10 ×3, S5 ×1, S11 ×1 | S4.3 ×3, S6 ×1, S8 ×1, S14 ×1, S11 ×1, S2 ×1 |

Suggested verdict: **same**

Review notes:
- candidate run-01 confusing [S4.3]: Says the focus table's own columns are only in <focus_table>, but t2's own key_directory entry also lists them as other_columns; harmless here, but it blurs which copy to trust.
- candidate run-01 confusing [S6]: Excludes 'the batch column' as technical, yet gds_batch_id has is_meta_data false and a null profile.batch_attribute_name; I recognised it only through the table-level batch_attribute_name.
- candidate run-01 comment: Clear for this input: the cds_/cym_ example in S8 matches the case, and S7 rule 1 (own look-alike group) picks t1 over t4 without doubt. With source_context and source_systems empty, the same-System tests in S7 and S8 cannot be applied, so only name prefixes and the CDS/CYM descriptions separated the groups. No rule made me drop a link I believed correct.
- candidate run-02 confusing [S8]: With source_systems [] and all six tables in one lake System, Connection and schema, the text does not say whether the cds_ and cym_ prefixes are look-alike groups of one System (S8 bullet 1) or two business Systems (S7 rule 2; S8 says tables of different Systems never form one group). I treated them as groups using the S8 last bullet (tell groups apart by names and descriptions); both readings give t1, so the answer is unchanged.
- candidate run-02 confusing [S14]: The closing paragraph mentions record identities, authoring values, locked records staying as saved, and older prompts. None of these match this task's schema or S13 (omit locked findings), so it reads as text pasted from another prompt. Harmless here.
- candidate run-02 confusing [S4.3]: It says the focus table's own columns are in focus_table, yet the focus table t2 also appears in key_directory with a full other_columns list. I did not use it as a target (S3, S10 self-reference rule), but the text does not say the focus entry is repeated there.
- candidate run-02 comment: Simple case: one reference column (employeeid), and the cds_ look-alike group picks t1 over t4; the repeating t1 key is explained as loads (S9, S11). Cardinality followed S11 mechanically (From many, To one within one load), though 900 rows with 350 distinct ids over 3 loads would also fit about one contact per employee per load. No Context records, source_context or lineage were given, so the group came only from name prefixes and descriptions.
- baseline run-03 blocker [S7]: I believe the business meaning is many_to_one (many contacts per employee), but t1.employeeid repeats once per load (400 distinct in 1200 rows) and S7 says such a To column cannot give many_to_one, so I emitted many_to_many instead.
- baseline run-03 confusing [S10]: S10 says the To side is one for a documented single-column key and many when values repeat. t1.employeeid is a documented natural key (is_natural_key true) that repeats only because the bronze load appends rows per batch, so S6, S7, S9 and S10 point different ways. S9's 'a documented rule establishes it' is not defined; I relied on the description 'one row per employee per load' and S2 item 5.
- baseline run-03 confusing [S9]: S9 says to leave the link out when the parent's System cannot be told by source_systems, but source_systems and source_context are empty for every table. Only the descriptions and table names (CDS vs CYM) separate the two sources, and it is unclear whether that counts as being told.
- baseline run-03 confusing [S5]: gds_batch_id is plainly a load-batch column by its description, but is_meta_data is false, and S5 ties the operational-column exclusion to that flag while S4 says the flag defaults to false.
- baseline run-03 comment: The CDS-versus-CYM choice rests only on descriptions and table names, so a Source Information Context record would remove the doubt. The bronze parent key repeats once per load, and the rules do not say plainly how such a parent should be treated for cardinality, so many_to_one versus many_to_many is the real uncertainty. One worked example of a load-appended bronze parent in S8 or S9 would settle it.
- candidate run-04 confusing [S4.3]: Says the focus table's own columns are in <focus_table>, yet t2's own key_directory entry also repeats all four of them under other_columns. Harmless here, but it is unclear whether the duplicate is intended or whether those entries count as shown To columns under S3.
- candidate run-04 confusing [S11]: Says to judge cardinality within one load, but the focus profile is row_scope all_rows across three loads (900 rows, 350 distinct employeeid), so load repeats and several contacts per employee cannot be told apart. I used the From-side default (many) and the To side one from t1's key flag.
- candidate run-04 confusing [S2]: Item 4 gives the lake's own codes as GDS / GDS / GDS, but these lake tables carry GDS / WAREHOUSE / MAIN with source_systems [], so it is unclear whether WAREHOUSE is a business System or just the lake's storage. S8's last bullet (use names and descriptions) settled it and it did not change the answer.
- candidate run-04 comment: The look-alike rules (S7 rule 1, S8) and the rule against pointing at another table's reference column (S7 Never) made t1 an easy choice over the CYM tables and the sibling employeeid columns, even with empty source_context. The only real judgment was cardinality, settled by S11 and t1's key flag. The prompt is long, but each rule I needed was easy to find by section.
- baseline run-05 blocker [S7]: The contradiction rule says a To column with distinct_count below non_null_count cannot be many_to_one. t1.employeeid has 400 distinct of 1200 rows, so I emitted many_to_many. I believe the business meaning (contacts to the current employee row, highest gds_batch_id per S2) is many_to_one.
- baseline run-05 confusing [S9]: The parallel-tables rule says link by `source_systems` and leave the link out when the parent's System cannot be told, but `source_systems` is empty for all six tables. CDS vs CYM shows only in table names and descriptions. It is unclear whether that counts as telling the System, so I linked within CDS using the descriptions.
- baseline run-05 confusing [S10]: The To side is `one` for a documented single-column key and `many` when values repeat. t1.employeeid is both (is_natural_key true, 400 distinct of 1200 rows). S7 resolves it, but S10 does not point to S7.
- baseline run-05 confusing [S9]: 'Include the pair only when a documented rule establishes it' does not say what counts as a documented rule (the object description 'one row per employee per load' plus the S2 load rule?). S4 and S11 also imply a repeating To key can never validate as `supported`, which clashes with S11's advice to point at a unique single-column key.
- baseline run-05 comment: I linked t2.employeeid to t1.employeeid (CDS parent, same STRING type, 350 <= 400 distinct, length 8) and left out the CYM look-alike t4 and the sibling tables' employeeid columns. A bronze parent with one row per employee per load will always fail `supported` validation, so the prompt could say how such pairs should be reported. A worked example with a batch-repeating parent and its expected cardinality would remove most of my doubt.
- baseline run-06 blocker [S7]: A To column with distinct_count below non_null_count 'cannot be many_to_one or one_to_one'. t1.employeeid has 400 distinct values in 1200 rows (one row per employee per load), so I used many_to_many, although I believe the business meaning is many_to_one.
- baseline run-06 confusing [S9]: Parallel tables rule says link by source_systems and leave the link out when the parent's System cannot be told. All source_systems are empty here and only table names and descriptions (CDS vs CYM) show the source; the text does not say whether descriptions count. I treated them as enough.
- baseline run-06 confusing [S9]: Grain and history says include a history-table key 'only when a documented rule establishes it' but not what counts as such a rule. I used S2 point 5 plus the object description 'one row per employee per load'; no worked example covers a bronze table whose key repeats once per load.
- baseline run-06 confusing [S10]: To side is 'one' for a documented single-column key (t1.employeeid has is_natural_key true) but 'many' when values repeat (400 distinct of 1200), and S7 says repeats mean it is not a key. The rules point to different cardinalities for the same pair; I followed S7.
- baseline run-06 confusing [S11]: Says to point a reference at a single-column key so a correct finding can come back supported, but S4 needs unique To values for supported, which a bronze table with several loads per key never has.
- baseline run-06 comment: The link t2.employeeid to t1.employeeid is well supported by the descriptions (CDS source, employee entity, same lake Connection, STRING length 8, 350 distinct within 400), and I left out t4 as the CYM look-alike. The prompt does not say how to treat a natural key that repeats once per batch load, which is normal for bronze. A worked bronze-history example with the expected include or leave-out decision and cardinality would remove most of my doubt.

