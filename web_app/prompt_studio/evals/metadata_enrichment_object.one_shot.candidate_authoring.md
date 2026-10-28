# Test log: metadata_enrichment_object.one_shot.candidate_authoring

## 2026-10-28 · `r1-source_cryptic` · fixture `source_cryptic` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 4.7 | 4.0 |
| Blockers cited | – | – |
| Confusing cited | S4 ×2, S5 ×2, I2 ×1, S4.1 ×1 | S5.4 ×3, S6 ×1, S5.2 ×1, S3.1 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-01 confusing [S5.4]: S5.2 counts System descriptions as documented meaning, but here the only one ('Legacy mainframe kept for historical records.') says why the System exists, not what T0042 holds. It is unclear whether that is a supported meaning for the table or whether the null rule applies; I chose null because the S5.4 example is a cryptic name that nothing describes.
- candidate run-01 confusing [S6]: Final check items 2 and 3 assume a text description (one or two plain sentences, what one row represents) and never say how they apply when the answer is null.
- candidate run-01 comment: Null looks like the intended result here: the table and column names are cryptic, no table or column has a description, and S5.2 and S5.3 say names, data types, key flags and profiles are clues only and cannot create a meaning. S3.1 does not list zone_code and zone_description, which appear in the source_context entry, but this did not change my answer.
- baseline run-02 confusing [S4]: Ranks source_context descriptions first but never says whether a System-level description alone (here 'Legacy mainframe kept for historical records.') can support an Object description; only the S4.1 cryptic-name rule settled it as null for me.
- baseline run-02 confusing [S5]: 'a compact JSON array string, without added spaces, case changes or unescaping' is ambiguous between the decoded key text and the raw escaped text; I copied the schema's property name verbatim, which keeps the quote escaping.
- baseline run-02 comment: S4.1's example name T0042 is the exact Object name in this input, so null is nearly spelled out and this run may not show how the rule holds for other cryptic tables. The only documented text is the System description, which says why the System exists but not what this table's rows record. Five undescribed columns of mixed types with no key roles gave no supported meaning without guessing from types.
- candidate run-03 confusing [S5.4]: S5.2 ranks System descriptions as documented meaning, but this rule says a cryptic name that nothing describes gets null. The messages do not say whether a System-level line such as 'kept for historical records' counts as describing the table; I read it as not enough.
- candidate run-03 comment: S5.4's example uses the very name T0042, so this input is easier than a different cryptic name would be. A short rule saying whether a System description alone can support a table description would remove my one doubt. The source_context entry also carries zone_code and zone_description, which S3.1 does not list.
- candidate run-04 confusing [S5.4]: Not stated whether a System-level description alone ('Legacy mainframe kept for historical records') counts as a supported meaning for one table. It describes the System, not what a row here holds, so I treated the table as undescribed and returned null; one sentence on the 'only the System is described' case would remove the doubt.
- candidate run-04 confusing [S5.2]: Item 3 says clues can 'sharpen a meaning found above', but the only meaning above is System-level; it is unclear whether column types and profiles may sharpen it into a table description. I assumed not.
- candidate run-04 confusing [S3.1]: The source_context entry also carries zone_code and zone_description, which S3.1 does not list (S3.2 places zone fields in gds_context, which is [] here). Harmless, but it could be mistaken for the Object's own zone.
- candidate run-04 comment: The case matches the S5.4 example (cryptic table name that nothing describes), so null felt right, but the System description made me pause. The column types and profiles (a unique 8-character column, an amount, a date, a two-value flag) invite a guess about the kind of records, and S5.2 item 3 and S5.3 correctly rule that out. One extra sentence in S5.4 about System-only evidence would settle the doubt.
- baseline run-05 confusing [I2]: Step 3 says to use Profiles to establish purpose and supported grain, but S3.2, S4 and S4.1 say Profiles and uniqueness only support documented meaning. With no documentation at all (as here, where F01 is 100% distinct) it is not said outright that Profiles cannot carry a description alone; I inferred that.
- baseline run-05 confusing [S4.1]: The only stated null trigger is a cryptic name that nothing documents. It is not said whether System-level text alone (here 'Legacy mainframe kept for historical records') could justify a generic description; S4's 'return null only when no supported meaning remains' leaves that boundary open and I relied on the T0042 example.
- baseline run-05 confusing [S5]: 'Copy each output key ... without added spaces, case changes or unescaping' is ambiguous for a key that contains quotes. I took it to mean the decoded key is the compact array string and that it is JSON-escaped once inside the output object, not double-escaped.
- baseline run-05 comment: S4.1 uses T0042 as its example of a cryptic name, which is exactly this input's table name, so the example answers this case and the test does not show whether the rule generalizes to other cryptic names. S2 is long for an Object-only task, and none of its bronze or instance rules mattered for this source table.
- baseline run-06 confusing [S4]: Ranks source_context descriptions as the first evidence, but does not say whether a System-level description (here 'Legacy mainframe kept for historical records') can support an Object description; I judged that it does not say what this table's rows record, so I relied on the S4.1 cryptic-name rule.
- baseline run-06 comment: The last sentence of S4.1 names this exact case (cryptic table name, nothing documenting it), so null was straightforward. The Profiles hint at a shape (a unique 8-character value, an amount, a date, a flag, a name-like text), but S4 and S4.1 correctly bar guessing meaning from types or uniqueness. One sentence saying whether System-level text may ever stand in for an Object description would remove my only hesitation.

## 2026-10-28 · `r1-bronze_two_instances` · fixture `bronze_two_instances` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 4.0 | 4.0 |
| Blockers cited | S4.1 ×2 | S5.1 ×1 |
| Confusing cited | S4.1 ×4, S5 ×2, S3.2 ×1, S2 ×1, I2 ×1 | S5.4 ×3, S5.1 ×2, I1 ×1, S6 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- baseline run-01 blocker [S4.1]: Minor: the no-storage rule plus 'business terms that fit the same data from any System' kept me from saying that the table merges the UK and DE databases (ids restart per instance) and that GDSBatchID loads can repeat an item. I think a downstream reader could use that, but I followed the rule.
- baseline run-01 confusing [S4.1]: It asks for the grain 'when documented', but S2.5 says a bronze table with GDSBatchID can hold the same record in several loads, so 'one row per ordered item' (the UK source grain) may not hold for this table. It is unclear whether to state the source grain or the bronze row grain; I stated the source grain.
- baseline run-01 confusing [S5]: 'Include every assigned target' and the 2,000 UTF-8 byte limit (the schema says maxLength 2000) read like wording shared with the Attribute workflows. Harmless here (one Object, short text) but slightly generic.
- baseline run-01 comment: The saved draft's 'confirmed orders only' rule was kept per S4 although nothing else documents it (line_status has three undocumented values). The DE source has no description, so I applied the UK grain to both on the strength of the registered description and S2.2. The S4.1 example is nearly identical to this input's subject, which could tempt a model to copy its wording.
- candidate run-02 confusing [S5.4]: The saved sentence 'lines cancelled before confirmation are removed in the source' is business scope but is worded as what the source does with its data. S5.1 forbids describing storage, while S5.4 says remove only storage, zone, load, name, hedge or column text and keep specific business content. I kept it unchanged; the rules do not say which wins for borderline wording like this.
- candidate run-02 comment: The same example sentence appears in S4 and S5.1 and almost matches this table (quantity, price, requested delivery date), so this test cannot show whether a model derives the text from the evidence or copies the example; I checked each detail against this run's column and source descriptions. The registered description holds only storage wording, so the meaning came from the source table description and the column descriptions. The generic paragraph after S6 (locks, previous_candidate_omitted) does not apply to this call.
- baseline run-03 blocker [S4.1]: Mild: the ban on describing storage kept me from adding that, with GDSBatchID, one ordered item can appear once per load and that order numbers repeat across the UK and DE instances, so 'one row per ordered item' is the source grain, not strictly the bronze row grain.
- baseline run-03 confusing [S4.1]: Says to state what one row represents 'when documented', but not which grain to state for a bronze table that appends versions (S2 point 5). I used the source's documented grain, which may overstate uniqueness in bronze.
- baseline run-03 confusing [S4.1]: Does not say whether naming the contributing instances (UK and German databases) is wanted or counts as storage detail. I included them in brackets as provenance.
- baseline run-03 confusing [S3.2]: Wording about 'contextual siblings' (also I2 step 3) and 'complete groups of columns' (I2 step 2) comes from Attribute workflows. With one Object and empty selected_attribute_names it does not apply, so I ignored it.
- baseline run-03 comment: The prompt worked well here: naming the business System through S2 point 4, dropping the storage wording from the saved text and keeping its business caveat were all straightforward. The one real gap is how to state grain for a bronze table that holds several instances and appended versions while storage detail is banned. A short worked example of such a description in S4.1 would settle both the grain and the instance-mention questions.
- candidate run-04 confusing [S5.4]: The saved sentence 'removed in the source' is business scope that S5.4 says to keep, but it also says where data is handled, which S5.1 bans. I kept it verbatim; it is unclear whether 'in the source' counts as allowed wording.
- candidate run-04 confusing [S5.1]: S5.1 asks what one row represents, but S2 item 5 says that with GDSBatchID one line can appear in several versions, and S5.1 bans load and batch wording. I wrote 'one row per ordered item' from the UK source description; the exact row grain of this table stays unclear.
- candidate run-04 comment: Clear overall; the escaped-key rule in S4 and the keep-and-trim rule in S5.4 were easy to apply. The Good example in S5.1 is nearly the same as this table's real evidence, so a model could copy it without reading the inputs; I wrote from this run's evidence, which happens to support the same wording.
- candidate run-05 blocker [S5.1]: The ban on saying where rows come from kept me from noting that the table holds order lines of two instances (UK and DE). Later steps can see this in source_context and the instance column, so the loss is small, but the note would help match parallel tables.
- candidate run-05 confusing [I1]: Step 4 says keep the saved description's 'supported' business content, but S5.4 says keep it unless contradicted and never drop it just because nothing confirms it. Here nothing else confirms 'confirmed orders only', so 'supported' could be read as 'remove'. I followed S5.4.
- candidate run-05 confusing [S5.1]: It asks what one row represents, but S2 (item 5) says a bronze table with a batch id can hold one record in several loads, and S5.1 forbids load wording. I used the UK source description 'one row per ordered item' as the business grain; a line saying whether that is right for a bronze table would help.
- candidate run-05 confusing [S5.4]: Unclear whether 'removed in the source' in the saved text counts as loading wording to strip. I kept it because it states which orders exist, not how data is loaded.
- candidate run-05 confusing [S6]: The closing paragraph (locks, manifests, repair.previous_candidate_omitted, enabled tools) does not fit this call: S1 says no tools are available and the input has no locks or manifests.
- candidate run-05 comment: The S4 and S5.1 examples are almost the same table as this input (sales order lines with quantity, price and requested delivery date), so a good answer here cannot show whether the model reads the evidence or copies the example. I took every detail from the source description, column descriptions and saved description, and dropped only the saved text's 'Raw bronze copy of SO_LINE' opening.
- baseline run-06 confusing [S4.1]: Says to name the business source System but not whether to name the instances when several load one bronze table. I named the UK and German databases because the registered description and the instance column support it.
- baseline run-06 confusing [S2]: Item 5 says a record can appear in several loads under GDSBatchID, so a bronze row may not be exactly one ordered item. S4.1 asks what one row represents but bans storage detail, so it is unclear how to word the grain here; I used the source's documented 'one row per ordered item'.
- baseline run-06 confusing [I2]: Step 3 mentions 'contextual siblings', which is not defined for this Object-level task, and no sibling Objects were supplied.
- baseline run-06 confusing [S5]: The last paragraph refers to 'enabled tools' although S1 says no tools are available (apparently carried over from the tool-assisted variant).
- baseline run-06 comment: The confirmed-orders sentence rests only on the saved Project description, which nothing else confirms; I kept it because S4 says to. S4.1's example names a System but no instances, so the two-instance case relied on my reading of S2. Everything else mapped cleanly to the rules.

## 2026-10-28 · `r2-source_cryptic` · fixture `source_cryptic` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 5.0 |
| Confidence (1–5) | 4.0 | 5.0 |
| Blockers cited | – | – |
| Confusing cited | S4.1 ×3, S5 ×3, S4 ×1, I2 ×1 | I1 ×2, S5.2 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- baseline run-01 confusing [S4.1]: The only rule that settles this input (a cryptic name that nothing documents: return null) is one clause at the end of S4.1, while nearby text pushes the other way: S4 'Never return null...', I2 step 4 'exhaust the evidence before declaring meaning unsupported', S5 'do not omit uncertain targets'. I resolved it in favour of null, but it took weighing.
- baseline run-01 confusing [S4]: 'Return null only when no supported meaning remains' does not say whether a System-level description alone (here 'Legacy mainframe kept for historical records') counts as supported meaning for an undocumented table; I treated it as not describing what these rows record.
- baseline run-01 confusing [S5]: The closing paragraph mentions 'enabled tools' and a repair mode, while S1 says no tools are available; this is generic wording that does not apply to this run.
- baseline run-01 comment: I would move the cryptic-name null rule next to where S4 says when to return null, since for undocumented tables it is the deciding rule. The input itself was easy once that clause was found: ZX_118 and F01-F05 have no descriptions, no mapping, and only types and Profiles, which S3.2 and S5 say cannot establish meaning.
- baseline run-02 confusing [S4.1]: S4 says return null only when no supported meaning remains and I2 (step 4) says to exhaust the evidence first, while S4.1 says a cryptic name that nothing documents supports nothing: return null. It is not stated whether a System-level description alone (here 'Legacy mainframe kept for historical records') counts as supported meaning for an Object, so a vague sentence like 'Historical records from the legacy mainframe' looked possible until I judged it unsupported.
- baseline run-02 confusing [I2]: Step 3 says to use Profiles to establish purpose and grain, but S3.2 says Profiles only supplement documented meaning and S5 forbids inferring meaning from a type alone. With no documentation at all, the Profiles (a unique 8-character column, a decimal, a date, a two-value flag, a free-text column) invite a guess the rules forbid; a plain statement that undocumented Profiles alone give null would help.
- baseline run-02 confusing [S5]: 'Copy each output key character for character ... without added spaces, case changes or unescaping' can be read two ways. I kept the key as the schema JSON shows it, with each quote mark escaped, so it parses to the compact array string.
- baseline run-02 confusing [S5]: The closing paragraph mentions 'enabled tools' and repair.previous_candidate_omitted, which conflicts with S1 ('no tools are available') and does not apply when repair is null; it reads like shared boilerplate.
- baseline run-02 comment: The S4.1 example (a cryptic name that nothing documents returns null) matches this input almost exactly, so the null answer felt safe. The unique column F01 and the other Profiles make a guess tempting, and the rules rightly stop it. One sentence saying whether a System-level description alone can support an Object description would remove the only judgment call I had.
- candidate run-03 confusing [S5.2]: Minor: item 1 ranks System descriptions as top documented meaning, yet the paragraph after the list says a System description alone never supports a description; the later sentence settled it, but the ranking reads stronger than it is.
- candidate run-03 confusing [I1]: Minor: step 3 says descriptions, key flags and profiles show what the table holds and what one row may represent, which sounds stronger than S5.2 item 3 and S5.3 where they are only clues that never create a meaning (here F01 is fully unique, which proves nothing about what a row is).
- candidate run-03 comment: The S5.4 example of a cryptic name that nothing describes matches this table, whose columns F01 to F05 are equally undescribed and whose only documentation is a generic System description. The bans on invention, hedges and source or storage wording leave no compliant non-null text, so I returned null. A line in S5.4 saying that undescribed columns plus a System-only description also mean null would remove the small inference I made.
- candidate run-04 confusing [I1]: Step 3 says key flags and profiles 'show what the table holds and what one row may represent', but S5.2 says names, types, key flags and profiles are clues only and S5.3 says a unique column alone does not prove what a row represents. Here F01 is unique across all 9,120 rows, so step 3 invites a row-grain guess that S5.3 forbids; I followed S5.
- candidate run-04 comment: Null was clear because S5.4's own example (a cryptic name that nothing describes) matches this table, and S5.2 rules out building a meaning from the System description, column names, types or profiles. The closing generic paragraph mentions 'enabled tools' although S1 says no tools exist, which is harmless in one-shot mode.
- baseline run-05 confusing [S4.1]: The null rule is stated for a cryptic name that nothing documents, but here the System has a general description ('Legacy mainframe kept for historical records') and Profiles exist. It is not said whether a System-level description alone can justify a thin generic table description, so the line between null and a short description is a judgment call.
- baseline run-05 comment: Null follows from S4.1 (cryptic name that nothing documents) and S4 (no fabricated specificity); the two rules agree on this input. The System text describes the System, not what this table's rows record, so I did not reuse it. One sentence in S4.1 about System-only evidence would remove the single judgment call.
- candidate run-06 comment: Everything about this table is cryptic (table and column names, no descriptions, only a generic System description), so S5.2 item 3, S5.3 and S5.4 clearly give null. The profiles hint at ids, amounts and dates, but the rules correctly stop those clues from becoming a description. S5.2 lists System descriptions as documented meaning and then says they never support a description alone, which reads slightly awkward but did not change my answer.

## 2026-10-28 · `r2-bronze_two_instances` · fixture `bronze_two_instances` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 4.0 | 4.0 |
| Blockers cited | S4.1 ×3 | S5.2 ×1 |
| Confusing cited | S4 ×3, S4.1 ×3, S5 ×2, S2 ×1 | S5.4 ×3, S5.2 ×2, S6 ×2, I1 ×1, S5.1 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-01 confusing [S5.4]: S5.1 bans source and load wording, but S5.4 says to keep scope rules 'even when worded as something the source does'. It does not say whether to keep that wording or restate it neutrally. I kept the rule (confirmed orders only; lines cancelled before confirmation) and dropped 'in the source'.
- candidate run-01 confusing [S5.2]: 'Describe what they share' does not say what to do when one loading table (here the second instance) has no description. I assumed it matches the described one, because S2 says instances of a System have the same or very similar tables.
- candidate run-01 confusing [I1]: Step 3 says column descriptions, key flags and profiles 'show what the table holds', but S5.2 item 3 says names, key flags and profiles are only clues and can never create a meaning.
- candidate run-01 confusing [S6]: The closing paragraph (locks, manifests, enabled tools, repair.previous_candidate_omitted) is generic and does not fit this one-shot, no-tool call; S4 describes repair differently (previous answer plus validation_issues).
- candidate run-01 comment: The registered description held only storage and loading wording, so the row meaning came from the first source table's description and the scope rule from the saved draft. A short good/bad pair for a saved draft that mixes storage words with a scope rule would settle the S5.1/S5.4 question. Otherwise the prompt and input were consistent and easy to follow.
- baseline run-02 blocker [S4.1]: 'Do not ... describe storage' made me leave out that, because GDSBatchID appends changed rows (S2.5), one order line can appear in several loads and only the highest batch is current. I think that qualifies 'one row per ordered item' for this bronze table, but I omitted it.
- baseline run-02 confusing [S5]: 'Copy each output key ... without added spaces, case changes or unescaping' does not say whether the backslashes shown in the schema's property name belong to the key or are only JSON escaping. I assumed the key is the plain compact array text of the five key parts, written as an ordinary JSON string key.
- baseline run-02 confusing [S4]: Keeping the saved description's specific content unless contradicted, and never returning vaguer text because it is unconfirmed, sits uneasily with omitting disputed details and not fabricating specificity. The saved sentence about confirmed orders and removed cancelled lines has no other support, and line_status has three undocumented values. I kept it as stated.
- baseline run-02 confusing [S4.1]: It does not say whether the description should mention that several source instances feed the table, or what one row means when instances are combined. I added the UK and German databases and 'in each database'.
- baseline run-02 comment: S4.1's sample sentence is very close to this input's data and, unlike the S3 examples, is not marked illustrative, so I avoided copying 'ERP' and 'product'. Otherwise the prompt is clear; the main gap is how to state grain for an appended, multi-instance bronze table without describing storage.
- baseline run-03 blocker [S4.1]: The two-sentence limit and the ban on describing storage kept me from noting that so_no and line_no repeat across the UK and DE databases and that rows can repeat across loads (GDSBatchID), so 'one row per ordered item' is the source grain, not necessarily the physical row grain.
- baseline run-03 confusing [S4]: It says to keep the saved description's specific business content unless contradicted, but also to rank documented meaning first and omit unverified detail. The 'confirmed orders only' claim appears only in the saved draft; I kept it but it is the part I am least sure of.
- baseline run-03 confusing [S4.1]: It does not say whether to name the contributing instances (UK, DE) or how to treat a grain documented by only one of two sources (S3.3 only says to consider all sources). I named both instances and applied the UK grain to the whole table.
- baseline run-03 confusing [S5]: The closing paragraphs are generic: they mention tools, manifests and repair state that do not exist in this input (S1 says no tools are available) and repeat schema rules already given earlier in the same section.
- baseline run-03 comment: S2 made it easy to see that the business System is ORDERS_APP, not GDS. A short worked example of a multi-instance bronze description in S4.1 would settle whether the instances and the repeated rows per load belong in the text. Everything else was clear.
- candidate run-04 confusing [S5.4]: It says to keep scope rules 'even when worded as something the source does', but S5.1 and S6 item 3 forbid source, instance and load wording. I kept the scope content (confirmed orders only; lines cancelled before confirmation are excluded) and dropped the phrase 'removed in the source'; it is unclear whether the original wording was meant to stay.
- candidate run-04 comment: The storage-only text in the saved description and the registered description was covered well by S5.1 and S5.4. The registered description held only storage and load words, so the meaning came from the source table description in ingestion_mapping; a short note that such text carries no meaning would help. I left out the status column because it has no description and S5.2 says names and profiles cannot create meaning.
- candidate run-05 blocker [S5.2]: Rule 3 (names, types and profiles never create a meaning) made me leave out the line status, which I believe the table carries, because that column has no description anywhere.
- candidate run-05 confusing [S5.4]: Says to keep scope rules 'even when worded as something the source does', but S5.1 and S6 item 3 ban source, zone and load words. I kept the rule (confirmed orders only; lines cancelled before confirmation) and reworded 'removed in the source' to 'excluded', but it is unclear whether the original wording is expected.
- candidate run-05 confusing [S5.1]: 'Leave out column names' sits next to 'the main information it carries'; it is unclear whether naming kinds of information such as quantity, price and currency is allowed. I used plain business words, not column names.
- candidate run-05 confusing [S5.2]: The registered object description is ranked first as documented meaning, but here it only describes storage and loading, so it gives no business meaning. No rule says explicitly to skip it; I inferred that from S5.1.
- candidate run-05 confusing [S6]: The closing paragraph after the checklist (enabled tools, locks, manifests, repair.previous_candidate_omitted) does not apply to this one-shot, single-description call and sits oddly beside S1, which says no tools are available.
- candidate run-05 comment: Row meaning came only from the UK source table description; the German source table has no description, so I relied on the matching name and the column descriptions. A rule for when the top-ranked evidence is purely storage text would remove my main judgment call. Otherwise the prompt was easy to follow.
- baseline run-06 blocker [S4.1]: Mild: the ban on describing storage kept me from saying that this bronze table can hold several loaded versions of the same ordered item (GDSBatchID appends) and that ids repeat per instance, so 'one row per ordered item' is true per source database and current load rather than literally for every physical row. I stated the source's documented grain plainly instead.
- baseline run-06 confusing [S4.1]: It says to name the business source System but is silent on whether a multi-instance bronze table should also name its instances (here the UK and German databases). S2 item 5 stresses instances, so I named both.
- baseline run-06 confusing [S4]: 'Omit disputed details' sits beside 'keep the saved description's specific business content unless contradicted'. It is unclear whether an unconfirmed saved claim (confirmed orders only) counts as disputed. I kept it, reading the rule against dropping text only for lack of confirmation as decisive.
- baseline run-06 confusing [S2]: Item 5 says one record can appear in several loads, while S4.1 asks for what one row represents, which here comes from the source description. No guidance says which grain to state for a bronze table that has GDSBatchID.
- baseline run-06 comment: Clear for the plain case; the judgment calls were keeping the saved 'confirmed orders only' sentence while dropping its storage sentence, and how to phrase grain for a bronze table. A short worked example for a multi-instance bronze table would settle the ambiguities above.

