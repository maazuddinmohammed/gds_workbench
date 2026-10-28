# Test log: metadata_enrichment_attribute.one_shot.candidate_authoring

## 2026-10-28 · `r1-contacts_pii` · fixture `contacts_pii` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 4.0 | 3.7 |
| Blockers cited | S4 ×3, I2 ×1 | S5.4 ×2, S5.2 ×1, S8 ×1 |
| Confusing cited | S4 ×9 | S8 ×4, S5.1 ×3, S9 ×1, S3.4 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- baseline run-01 blocker [S4]: 'Return null for an unsupported description rather than restating its name' left STATUS with no description, although a plain 'status code of the contact record' is almost certainly true and would help a reader.
- baseline run-01 confusing [S4]: PII lists 'person-linked customer or employee IDs' as true but also says uniqueness and key membership alone do not establish PII. For CONTACT_NO (the unique number of a contact person) it is unclear how much linkage is enough; I relied on the sentence that person-linked identifiers of contacts are personal data and answered true.
- baseline run-01 confusing [S4]: STATUS has no documentation at all. 'Return null for an unsupported description' and 'false requires a supported non-personal meaning' (I2) point to null, but 'generic statuses' is listed as a false example. I used a null description and is_pii false; it is unclear whether a name plus a one-character, two-value profile counts as an established meaning.
- baseline run-01 confusing [S4]: 'Keep the specific detail of a registered description' conflicts with 'name a System only for a System-specific code list': the registered CREATED_AT text says 'in the CRM', and I changed it to 'source application'.
- baseline run-01 comment: The PII paragraph appears twice, in S4 and in the schema description, and the schema copy leaves out the sentence about companies versus people that decided ACCOUNT_NO (false) and CONTACT_NO (true). Key and nullability rules gave one clear answer for every column. PHONE and LAST_NAME are unselected siblings, so I used them as evidence only.
- candidate run-02 blocker [S5.2]: STATUS has no registered or saved description and the table text never mentions it, so I returned a null description; 'Status of the contact record' seems right, but the name alone cannot create a meaning.
- candidate run-02 blocker [S8]: Generic statuses are listed as false, but with no description I cannot show STATUS has a non-personal meaning, so I set is_pii to null instead of false.
- candidate run-02 confusing [S8]: CONTACT_NO: 'person-linked identifiers of contacts' points to true, while 'uniqueness or key membership alone never establishes PII' points the other way. I chose true because the number identifies one contact person, but the line between a person-linked ID and a plain record key is not defined.
- candidate run-02 confusing [S8]: The first bullet lists 'personal email', which could exclude a business email; only the later line on contact details of employees or contacts settles EMAIL as true.
- candidate run-02 confusing [S5.1]: The registered CREATED_AT text says 'in the CRM'. S5.1 says not to name a System while S5.4 says to keep registered detail; I dropped 'in the CRM'.
- candidate run-02 comment: The key decision was easy: CONTACT_NO is the only business identifier and primary key. S7 leaves is_nullable null for FIRST_NAME and STATUS even though their full-table profiles show no nulls, which may surprise readers. The weakest calls are the null description and null PII for the undocumented STATUS column.
- candidate run-03 blocker [S5.4]: STATUS has no registered or saved description, so I returned null. A plain 'Status of the contact record' seemed true and useful, but S5.2 says names never create a meaning and S5.4 says not to restate the column name.
- candidate run-03 confusing [S5.1]: S5.1 says to name a System only for code lists or identifier namespaces, while S5.4 says to keep the specific detail of registered descriptions. The registered CREATED_AT text says 'in the CRM'; I dropped it, but it is unclear which rule wins.
- candidate run-03 confusing [S8]: For the undocumented STATUS column, 'generic statuses' are listed under false, while 'evidence is missing' means null. I chose false, but that sits oddly with a null description (S5.4) for the same unknown meaning.
- candidate run-03 confusing [S9]: The closing paragraph mentions enabled tools and repair.previous_candidate_omitted, but S1 says no tools exist and context.repair is null here; harmless but slightly distracting.
- candidate run-03 comment: The key and PII rules were easy to apply, especially the S8 sentence saying names, contact details and person-linked identifiers of contacts are personal data. The main judgement calls were CONTACT_NO as PII true and the undocumented STATUS column. FIRST_NAME and STATUS stay is_nullable null under S7 even though their all_rows profiles show no nulls, which is cautious but leaves them unresolved.
- candidate run-04 blocker [S5.4]: STATUS has no registered or saved description and the table text never mentions it. I believe it is a record status flag, but names and profiles may only sharpen a documented meaning (S5.2), so I returned null instead of a bland 'Status of the contact record.'
- candidate run-04 confusing [S5.1]: The registered CREATED_AT text says 'in the CRM'. S5.1 says to name a System only for a code list or identifier namespace, but S5.4 says to keep the specific detail of registered text. I dropped the System name; the two rules do not say which wins.
- candidate run-04 confusing [S8]: False needs evidence of a non-personal meaning, yet STATUS has no documented meaning (S5.4 gives null). I used the 'generic statuses' example plus the 1-character, 2-value profile as that evidence and set false rather than null; it is unclear which is intended.
- candidate run-04 confusing [S3.4]: 'Your answer replaces the first one and the four flags' does not say what 'the first one' is until the list below it (attribute_description).
- candidate run-04 comment: Most columns had clear documented meaning, so the key, nullability and PII rules were easy to apply. The two calls I am least sure of are CONTACT_NO as PII (it rests on the table being one row per contact person, while S8 warns against uniqueness or key membership alone) and STATUS as false rather than null. A short worked example of an undocumented generic column in S5.4 or S8 would settle STATUS.
- baseline run-05 blocker [S4]: 'Return null for an unsupported description rather than restating its name' left STATUS without a description, although I believe it is a record status flag and a short generic description would be accurate.
- baseline run-05 blocker [I2]: 'false requires a supported non-personal meaning' kept STATUS is_pii at null, although I believe a one-character status code is non-personal and S4 names generic statuses as false.
- baseline run-05 confusing [S4]: Names, types and profiles 'only support' a documented meaning, yet 'generic statuses' is listed as a false example; for an undocumented STATUS column it is unclear whether false is allowed or only null.
- baseline run-05 confusing [S4]: PII examples say 'personal email/phone/address', but this EMAIL is a business address; the later line that contact details of contacts are personal data resolves it, though the two sentences pull apart.
- baseline run-05 confusing [S4]: 'Person-linked customer or employee IDs' are PII, but uniqueness or key membership 'alone does not establish PII'; for CONTACT_NO I relied on the one-row-per-contact-person Object description to answer true.
- baseline run-05 comment: STATUS was the hardest call: with no documented meaning I returned a null description and null PII rather than guess. LAST_NAME and PHONE are unselected siblings, so they are left out of the answer. A one-line rule for undocumented columns with an ambiguous name (null versus a generic name-based description, null versus false) would remove the remaining doubt.
- baseline run-06 blocker [S4]: 'Return null for an unsupported description rather than restating its name' made me leave the STATUS description null, although a plain 'status of the contact record' seemed harmless and useful; I followed the rule.
- baseline run-06 confusing [S4]: S4 says to return null when a description is unsupported, but I1 says to generate descriptions for every selected Attribute; for an undocumented column like STATUS it is unclear which one wins.
- baseline run-06 confusing [S4]: S4 lists 'generic statuses' as a false PII example, but I2 step 4 says false needs a supported non-personal meaning; for an undocumented STATUS flag it is unclear whether PII should be false or null (I chose false).
- baseline run-06 confusing [S4]: The PII examples say 'personal email/phone/address' while this column is a business email of a contact; the later sentence that contact details of contacts are personal data resolves it, but the first reads as if business email might not count.
- baseline run-06 comment: The main judgment calls were CONTACT_NO as a person-linked identifier (PII true) and STATUS as a generic status (PII false, description null). A short rule saying whether an undocumented generic column such as STATUS should be false or null for PII would remove my main hesitation. Key, nullability and scope rules were otherwise clear and easy to apply.

## 2026-10-28 · `r1-bronze_order_lines` · fixture `bronze_order_lines` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 3.0 | 3.0 |
| Blockers cited | S4 ×5 | S5.4 ×3, S7 ×1, S5.3 ×1 |
| Confusing cited | S4 ×10, I3 ×1, I1 ×1, S3 ×1 | S8 ×3, S6 ×2, S5.1 ×2, S9 ×1, S6.2 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-01 blocker [S5.4]: line_status has no registered or saved description and the table texts never mention it, so S5.2 (names cannot create a meaning) and S5.4 forced null; a plain 'Status of the order line.' would help readers but only restates the column name.
- candidate run-01 blocker [S7]: line_status has an all_rows profile with zero nulls in 48,210 rows, but it is not declared NOT NULL and is not a key member, so the rule forced null although I would lean to false from the profile.
- candidate run-01 blocker [S5.3]: For GDSBatchID I left out that a higher value means a later load and the highest per record is the current row, because the column's own evidence only says 'Load batch identifier.'
- candidate run-01 confusing [S6]: Point 2 says the business identifier is the primary key unless the table keeps several rows per business key, but not what the key is then; I assumed identifier plus GDSBatchID for this append-loaded table.
- candidate run-01 confusing [S8]: S5.2 says names and profiles cannot create a meaning, yet S8 asks for false when the evidence shows a non-personal meaning; for line_status (name, type and profile only) I chose false because S8 lists generic statuses, but null is arguable.
- candidate run-01 comment: The multi-instance rule that puts the instance column in the identifier and the marking rule in S6 point 3 were clear. One line saying what the primary key is for append-loaded tables (identifier plus GDSBatchID) would remove my main guess.
- candidate run-02 blocker [S5.4]: line_status has no documented meaning, so I returned null. I believed a plain 'status of the order line' was acceptable, but S5.2 (names never create a meaning) and S5.4 (do not restate the column name) rule it out.
- candidate run-02 confusing [S6]: Point 2 says the business identifier is the primary key unless the table keeps several rows per business key, but it never says what the key is in that case. I inferred business identifier plus GDSBatchID for this append-loaded table.
- candidate run-02 confusing [S5.1]: 'Leave out sample values' versus S5.4 'keep a documented code list': for source_instance I kept ORD_UK and ORD_DE because the registered description lists them, but I am unsure whether that counts as sample values.
- candidate run-02 confusing [S8]: line_status has no documented meaning (description null), yet S8 lists generic statuses as false. I answered false from the table context plus the name, which S5.2 says cannot create a meaning, so it is unclear whether null was expected.
- candidate run-02 confusing [S9]: The closing paragraph mentions locks, manifests and enabled tools, which do not exist in this one-shot call with no tools.
- candidate run-02 comment: The multi-instance load plus GDSBatchID drove the key decisions, and the rest of the prompt was easy to apply. Several rules reward null (line_status description, unit_price nullability), which is safe but leaves a blank for a plainly named column. A short worked example of the key decision for an append-loaded bronze table would remove my main doubt.
- candidate run-03 blocker [S5.4]: line_status has no registered or saved meaning. S5.2 item 3 says a name cannot create a meaning and S5.4 forbids restating the column name, so I returned null, although 'Status of the order line.' seemed right and useful to readers.
- candidate run-03 confusing [S6.2]: When the table keeps several rows per business key (GDSBatchID appends, S2.5), S6.2 does not say what the primary key is, nor whether that case counts as decided for S6.3. I inferred business identifier + source_instance + GDSBatchID and marked those four true.
- candidate run-03 confusing [S5.1]: S5.1 says leave out sample values, but S5.4 says keep a documented code list. The registered description of source_instance lists ORD_UK and ORD_DE; I kept them as a documented code list.
- candidate run-03 confusing [S8]: For line_status the name alone was too weak to write a description (S5.2 item 3), yet S8 lets 'generic statuses' support is_pii false from the same name and table context. The evidence standard for description versus PII is not stated.
- candidate run-03 comment: The key chain S2.5, S6.1 and S6.2 gave a clear table-level decision once combined, and the rest of the rules were precise. The weakest spots are the primary key for append-style bronze tables and columns that have only a name to go on. One worked example for each, such as this order-lines table, would raise confidence.
- baseline run-04 blocker [S4]: 'Return null for an unsupported description rather than restating its name' made me return null for line_status; 'status code of this order line' is probably correct and useful, but nothing documents it beyond its name, type and a small profile.
- baseline run-04 blocker [S4]: is_nullable is false only with a NOT NULL declaration or primary-key membership, so line_status (no nulls in an all_rows profile, but registered nullability is only the default true) stayed null although false is likely the truth.
- baseline run-04 confusing [S4]: The primary-key sentence says the natural key is the primary key unless the table keeps several rows per business key (repeated loads), but never says what the key is then; I assumed natural key plus GDSBatchID because S2 says each load appends changed rows.
- baseline run-04 confusing [S4]: Null guidance pulls two ways: S4 says names, types and profiles only support documented meaning and to return null rather than restate the name, while S1 and I2 say use null only where nothing saved fits or nothing defensible remains.
- baseline run-04 confusing [S4]: 'Never include sample values' versus 'keep the specific detail ... such as a documented code list': I kept (ORD_UK or ORD_DE) in the source_instance description as a documented list, but a reader could call it sample values.
- baseline run-04 confusing [S4]: PII false for line_status leans on the 'generic statuses' example although its meaning is undocumented; 'a column name alone does not establish' and 'null for insufficient evidence' could equally justify null.
- baseline run-04 comment: The instance-column and GDSBatchID rules (S2, S4) made the key decisions easy for this table. The weakest spots are an undocumented column such as line_status and the primary-key wording when loads append several rows per record. The Object description mentions quantity and delivery-date columns that are not among the siblings, so I used it only as loose context.
- baseline run-05 blocker [S4]: is_nullable stays null for line_status although its all_rows profile shows no nulls; the rule allows false only for declared NOT NULL columns or primary-key members, so I could not record that it looks never-null.
- baseline run-05 confusing [S4]: The primary-key rule says the natural key is not the primary key when the table keeps several rows per business key, but never says what the key is then. S2 says GDSBatchID tables append every load, yet S4 does not link the two, so I assumed instance + so_no + line_no + GDSBatchID.
- baseline run-05 confusing [S4]: 'Return null for an unsupported description rather than restating its name' feels in tension with I2 'use null only where nothing defensible remains'. For line_status (only name, CHAR(1) and object context) I could not tell which applies, so I wrote a minimal description with no code meanings.
- baseline run-05 confusing [S4]: Source order is registered description then saved description, yet it also says keep the specific detail of either. For so_no the saved text is more specific than the registered one, so I kept it, but the priority is not explicit.
- baseline run-05 confusing [S4]: 'Never include sample values' versus 'keep a documented code list': the registered source_instance description lists ORD_UK or ORD_DE. I kept them as documented Connection codes, but the line between a sample and a code list is unclear.
- baseline run-05 confusing [I3]: The Object description mentions quantity and requested delivery date, but no such Attribute is in the sibling inventory that S3 calls complete. I treated it as context only and ignored those two items.
- baseline run-05 comment: Most rules were direct to apply: instance column in the natural key, nullability from declared NOT NULL, and PII false for business and technical columns. The one real guess is the primary key for a GDSBatchID table; one sentence in S4 saying the batch id joins the business key would remove it. I built the GDSBatchID description from the S2 loading rules rather than column documentation, which seemed allowed but is not stated.
- baseline run-06 blocker [S4]: is_nullable: line_status has an all_rows profile with no nulls, but false is allowed only for declared NOT NULL or primary-key members, so I left it null although it looks always filled.
- baseline run-06 blocker [S4]: Descriptions: the rule to return null when unsupported kept me from writing even a plain status-of-the-order-line description for line_status, which has no documentation.
- baseline run-06 confusing [S4]: Primary key: the natural key is the primary key unless the table keeps several rows per business key, but the rule does not say what the key is then. I assumed natural key plus GDSBatchID.
- baseline run-06 confusing [I1]: I1 asks for descriptions for every selected Attribute and I2 step 5 says null only where nothing defensible remains, while S4 says return null when unsupported. For a name-only column like line_status it is unclear which wins.
- baseline run-06 confusing [S4]: 'Never include sample values' sits beside 'keep a documented code list'. I kept the instance codes from the registered source_instance description, but it is not clear they are allowed.
- baseline run-06 confusing [S3]: S4 says 'declared NOT NULL' but the input field is attribute_nullability; I assumed false means NOT NULL, and S3 does not say so directly.
- baseline run-06 comment: Most of S4 could be applied almost mechanically, including the instance column joining the natural key and the nullability and PII rules. The weak spots were the primary key for an append-only Bronze table and how much to write for an undocumented column. I used the S2 load rule (highest GDSBatchID is current) in the GDSBatchID description, and the messages do not say whether landscape rules may appear in descriptions.

## 2026-10-28 · `r2-contacts_pii` · fixture `contacts_pii` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 4.0 | 4.0 |
| Blockers cited | S4 ×1 | S8 ×2, S5.4 ×1 |
| Confusing cited | S4 ×9, S5 ×1 | S8 ×5, S9 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-01 blocker [S5.4]: STATUS has no registered or saved description and the table text says nothing about status, so I returned a null description. A plain 'status of the contact record' would be useful, but the no-guessing rules (S5.2 item 3, S5.3) rule it out.
- candidate run-01 blocker [S8]: STATUS is_pii is null because its meaning is undocumented. It is probably a non-personal flag (CHAR(1), two values), but a name or profile alone cannot support false.
- candidate run-01 confusing [S8]: Lists 'contact number whose values each identify one person' as true, but also says uniqueness or key membership alone never establishes PII. For CONTACT_NO I relied on the registered 'unique per contact' plus one row per contact person, which is a judgment call.
- candidate run-01 confusing [S8]: A column like STATUS fits both 'false: generic statuses' and 'null: undocumented, a name alone is not evidence'. I followed null because no description exists, but which bullet wins is not stated.
- candidate run-01 comment: Clear overall; the table-level key decision was easy because CONTACT_NO is documented as unique per contact. EMAIL is unique among non-null values, yet I marked it false for both key findings following the single-key decision in S6. One sentence in S8 saying which bullet wins for an undocumented but generic-looking column would remove the main doubt.
- candidate run-02 blocker [S8]: STATUS is a one-character column with two distinct values, so I believe it is a non-personal flag (S8 even lists generic statuses under false), but the rule that an undocumented column gets null because a name alone is not evidence forced is_pii to null, and S5.2/S5.4 forced a null description.
- candidate run-02 confusing [S8]: Generic statuses are listed under false, while a column whose meaning is undocumented goes to null; a bare STATUS column fits both bullets and the prompt does not say which wins (I chose null).
- candidate run-02 confusing [S9]: The closing paragraph mentions enabled tools, manifests, locks and repair.previous_candidate_omitted, which do not match this one-shot, no-tools task described in S1 and add noise.
- candidate run-02 comment: The rules gave mechanical answers for keys (S6) and nullability (S7) and for the five documented columns. CONTACT_NO is PII because S8 names a contact number whose values each identify one person and the table has one row per contact person, although the plain phrase contact number in its registered description could be mistaken for a phone number. STATUS is the only real judgement call.
- baseline run-03 confusing [S4]: STATUS has no registered or saved description (one character, two distinct values). 'Return null for an unsupported description rather than restating its name' and 'names, types and profiles only support it' point to null, while S1 'Author useful Attribute descriptions' and S1 'Return null only when nothing saved fits the evidence' could also allow a minimal 'status code of the contact record'. It is unclear which is wanted when nothing was saved and nothing is documented; I used null.
- baseline run-03 confusing [S4]: PII false needs evidence that 'establishes' a non-personal meaning, and generic statuses are listed as false, yet an undocumented STATUS column has only name, type and profile as evidence. It is unclear whether false or null is wanted; I used false.
- baseline run-03 comment: The company-versus-contact rule in S4 made ACCOUNT_NO (false) versus CONTACT_NO, FIRST_NAME and EMAIL (true) easy to settle. The main judgement calls were treating CONTACT_NO as a person-linked identifier and handling the undocumented STATUS column. Unselected siblings LAST_NAME and PHONE were used as evidence only and left out of the output.
- candidate run-04 confusing [S8]: Listed under false: 'generic statuses'. Listed under null: 'a column whose meaning is undocumented: a name alone is not evidence'. STATUS here has only a name, CHAR(1) and two distinct values, with no description, so both bullets apply; it could even be a person attribute such as gender. I chose null, but the two bullets point in different directions.
- candidate run-04 confusing [S8]: 'Person-linked identifiers such as a contact number whose values each identify one person' is true, but 'uniqueness, key membership ... alone never establishes PII'. For CONTACT_NO I chose true because the table is one row per contact person and the number is documented as unique per contact. This is a borderline call that the text does not settle.
- candidate run-04 comment: STATUS is the only column with no documented meaning, so its description and PII finding are null (S5.2, S5.4, S8). The key (S6) and nullability (S7) rules were mechanical to apply to this table. One sentence in S8 on how to treat an undocumented status-like column would remove the main doubt.
- baseline run-05 blocker [S4]: STATUS has no registered or saved description, so the 'null rather than restating its name' rule made me return null; a short generic description of a record status flag would have been more useful to a reader.
- baseline run-05 confusing [S4]: The PII examples list 'personal email/phone/address', but the registered EMAIL description says 'Business email address of the contact'. I resolved it with the later sentence that contact details of contacts are personal data, but the two statements can be read differently.
- baseline run-05 confusing [S4]: For STATUS (name, CHAR(1), two distinct values, no description) it is unclear whether the evidence is enough for false ('generic statuses') or should stay null ('a column name alone does not establish PII', 'insufficient evidence').
- baseline run-05 confusing [S4]: 'Keep the specific detail of a registered description' slightly conflicts with 'name a System only for a System-specific code list': I dropped 'in the CRM' from the CREATED_AT description.
- baseline run-05 comment: The contact-versus-company distinction in S4 and the tenant description made ACCOUNT_NO (false) and CONTACT_NO, FIRST_NAME and EMAIL (true) easy to settle. The least settled calls are STATUS (PII false, description null) and CONTACT_NO as a person-linked ID, given the caution that uniqueness or key membership alone does not establish PII. A one-line S4 example of a business email for a named contact person would remove the main ambiguity.
- baseline run-06 confusing [S4]: The description rule says return null rather than restate the name, while I2 step 5 says use null only where nothing defensible remains. For STATUS, which has no documented meaning, it is unclear whether a generic status-code description is wanted; I returned null.
- baseline run-06 confusing [S4]: PII: generic statuses are listed as false, but STATUS has no documented meaning, only its name and a two-code profile. It is unclear whether that establishes a non-personal meaning or should be null; I chose false because a two-value code cannot identify anyone, yet left its description null.
- baseline run-06 confusing [S4]: PII: person-linked identifiers of contacts count as personal data, but uniqueness and key membership alone do not. For CONTACT_NO it is unclear how much beyond 'unique per contact' is needed; I chose true because the Object is one row per contact person.
- baseline run-06 confusing [S5]: The schema is called authoritative, yet the is_pii description inside required_output_schema omits S4's sentence on companies versus people, which is the sentence that separates ACCOUNT_NO from CONTACT_NO.
- baseline run-06 confusing [S4]: 'Keep the specific detail of a registered description' sits beside 'name a System only for code lists or identifier namespaces'; the registered CREATED_AT text says 'in the CRM' and I dropped that phrase.
- baseline run-06 comment: LAST_NAME and PHONE were unselected siblings, so I used them only as evidence and left them out of both maps. The company-versus-person sentence in S4 decided ACCOUNT_NO (false) versus CONTACT_NO, FIRST_NAME and EMAIL (true). FIRST_NAME and STATUS show no nulls in an all_rows profile but stay null for is_nullable under the S4 rule, which I followed as written.

## 2026-10-28 · `r2-bronze_order_lines` · fixture `bronze_order_lines` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 0.0 | 0.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 3.7 | 4.0 |
| Blockers cited | S4 ×6 | S8 ×3, S5.4 ×2, S5.2 ×1, S7 ×1 |
| Confusing cited | S4 ×7, I2 ×2, I3 ×1 | S8 ×3, S5.4 ×3, S6.2 ×2, S6 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- baseline run-01 blocker [S4]: 'Return null for an unsupported description rather than restating its name' made me return null for line_status; 'status of the sales order line' would be true and mildly useful but only restates the name.
- baseline run-01 blocker [S4]: The is_nullable rule allows false only for declared NOT NULL or primary-key members, so line_status stays null even though its all_rows profile shows no nulls; probably intended, but false was the other defensible answer.
- baseline run-01 confusing [S4]: The primary-key sentence says the natural key is the primary key unless the table keeps several rows per business key, but never says what the key is in that case; I assumed natural key plus GDSBatchID.
- baseline run-01 confusing [S4]: Null guidance is worded three ways (S1 'only when nothing saved fits', S4 'unsupported ... restating its name', I2 'nothing defensible remains'); unclear whether a name-level description counts as defensible when nothing is saved.
- baseline run-01 confusing [I3]: Object description says 'one row per product on a confirmed customer order' while the registered natural keys are so_no and line_no; I followed the registered flags rather than treating item_code as part of the grain.
- baseline run-01 comment: Natural-key, nullability and PII rules gave one clear answer per column; the real judgment calls were the primary key of a repeated-load table and the name-only line_status description. I kept the documented instance list in the source_instance description despite 'never include sample values', reading it as a code list, and left the saved so_no text unchanged.
- baseline run-02 blocker [S4]: line_status has no registered or saved description and the Object text never mentions status, so I returned null under 'null rather than restating its name'; I believed a short generic description (status code of the order line) was accurate.
- baseline run-02 blocker [S4]: line_status shows zero nulls in an all_rows profile but is not a primary-key member, so is_nullable stays null because false is allowed only for declared NOT NULL or primary-key members; I believed false was defensible.
- baseline run-02 confusing [S4]: It says the natural key is the primary key unless the table keeps several rows per business key, but never says what the primary key is in that case; I inferred natural key plus GDSBatchID from S2 item 5.
- baseline run-02 confusing [S4]: 'Never include sample values' sits beside 'keep a documented code list'; unclear whether the registered text for source_instance (ORD_UK or ORD_DE) is a code list to keep or sample values to drop. I kept it.
- baseline run-02 confusing [I2]: Step 5 says use null only where nothing defensible remains, while S4 says return null rather than restate the name; unclear if a minimal name-based description counts as defensible.
- baseline run-02 comment: S2 items 3 and 5 plus the key rule in S4 made the instance column and GDSBatchID handling clear: ids repeat per instance, so source_instance joins the business identifier. The Object text says one row per product while the registered flags mark so_no and line_no as the natural key; I followed the registered flags as S4 orders.
- candidate run-03 blocker [S5.2]: Names and profiles can never create a meaning, so line_status got a null description, although 'status of the order line' is very likely correct.
- candidate run-03 blocker [S8]: An undocumented column must be null, so line_status is_pii is null, although a one-character status in an order-lines table is almost certainly non-personal.
- candidate run-03 blocker [S7]: line_status shows 0 nulls in 48,210 rows (all_rows profile) and I would guess it is never empty, but S7 allows only null here.
- candidate run-03 confusing [S8]: 'Generic statuses' is listed as a false example, but undocumented columns must be null because a name alone is not evidence; for line_status it is unclear which applies, and I chose null.
- candidate run-03 confusing [S6]: S6.2 does not say that having GDSBatchID means repeated loads per business key. I linked it to S2.5 and put GDSBatchID in the primary key, but no profile can confirm that (so_no, line_no, source_instance) repeats.
- candidate run-03 confusing [S5.4]: S5.4 says to drop load words from saved or registered descriptions, but S5.1 lets the instance column keep them; I followed S5.1 for source_instance.
- candidate run-03 comment: The prompt is clear and the key, nullability and PII rules were mechanical enough to apply the same way each time. The only real judgement call was line_status, which has no documented meaning, so I left its description and PII finding null. The object description mentions quantity and delivery-date columns that are not in the column list, which I ignored.
- baseline run-04 blocker [S4]: Return null for an unsupported description rather than restating its name: I left line_status null (nothing documented anywhere) although I believed a short 'one-character status code of the order line' would be harmless and mildly useful.
- baseline run-04 blocker [S4]: is_nullable is false only for a declared NOT NULL or a primary-key member: I left line_status null although its all_rows profile shows no nulls and I believed it is probably never empty, because the nullable declaration may be only a default.
- baseline run-04 confusing [S4]: Says the natural key is the primary key unless the table keeps several rows per business key, but never says what the primary key is in that case. I assumed source_instance, so_no, line_no plus GDSBatchID (S2 item 5: each load appends changed rows), so GDSBatchID is a primary-key member but not a natural-key member.
- baseline run-04 confusing [I2]: Says use null only where nothing defensible remains, while S4 says null for an unsupported description rather than restating its name. For an undocumented column like line_status it is unclear whether a minimal name-and-type sentence counts as defensible.
- baseline run-04 confusing [S4]: Says never include sample values, yet also says keep a documented code list from a registered description. I kept (ORD_UK or ORD_DE) for source_instance as a documented code list, but the boundary is not explicit.
- baseline run-04 confusing [S4]: Documented row grain (one row per product on an order, from the Object description) hints at item_code as an alternative key part, while the registered flags name so_no and line_no. I followed the registered flags and did not mix the candidates.
- baseline run-04 comment: The rules and evidence fit together well, and the traps (default nullability, unprofiled columns, unselected siblings, the instance column) were clear. The least certain calls were the primary key for an append-style bronze table and the undocumented line_status description. One worked example of an appended-load primary key in S4 would remove the main guess.
- candidate run-05 blocker [S8]: line_status (1 character, 3 values, order-line table) is very likely not personal data, but 'undocumented means null' forced is_pii null.
- candidate run-05 blocker [S5.4]: 'Status of the order line' is probably true for line_status, but the rule against restating the column name forced a null description.
- candidate run-05 confusing [S8]: 'Generic statuses' are listed under false, yet 'a name alone is not evidence' sends an undocumented status column to null; unclear which wins. I chose null.
- candidate run-05 confusing [S6.2]: 'Table keeps several rows per business key' has no stated test; I inferred repeated loads from GDSBatchID being present (S2.5), since no profile can prove it.
- candidate run-05 confusing [S5.4]: Says drop load words, while S5.1 lets the instance column describe its load role; I kept 'loaded from' for source_instance.
- candidate run-05 comment: The closing paragraph after S9 mentions enabled tools and locks although S1 says no tools exist; harmless but noisy. The object description names quantity and requested delivery date columns that are not in the attribute list, so I ignored them. I put source_instance in both keys and GDSBatchID only in the primary key (S6.1, S6.2).
- candidate run-06 blocker [S5.4]: line_status has no registered or saved description and the table text never mentions status, so null-over-restating (S5.4) and names-are-clues-only (S5.2) left its description null although a plain 'Status of the order line' seemed reasonable.
- candidate run-06 blocker [S8]: line_status is a 1-character code with 3 distinct values that I believe is non-personal, but the undocumented-column rule forced is_pii to null instead of false.
- candidate run-06 confusing [S8]: 'generic statuses' is listed under false, yet a column with undocumented meaning is to be null; line_status fits both and the text does not say which wins.
- candidate run-06 confusing [S5.4]: Unclear whether 'Status of the order line' counts as restating the column name (so null) or as a meaning supported by the table description.
- candidate run-06 confusing [S6.2]: No profile can show that business keys repeat, so it is left implicit whether the mere presence of GDSBatchID (S2.5) is enough to add it to the primary key; I assumed yes.
- candidate run-06 comment: Natural key is so_no, line_no and source_instance (S6.1, two instances in the mapping); the primary key adds GDSBatchID (S2.5, S6.2). is_nullable is null for unit_price and line_status because attribute_nullability true may only be the default (S7). The closing paragraph after S9 mentions 'enabled tools', which does not apply to this one-shot call.

