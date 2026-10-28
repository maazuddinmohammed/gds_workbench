# Test log: logical.one_shot.optimize_authoring

## 2026-10-28 · `r1-per_system_duplicates` · fixture `per_system_duplicates` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 2.0 | 3.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 4.0 | 3.0 |
| Blockers cited | S4 ×3, S5 ×3, S8 ×1 | S9 ×3, S5 ×3 |
| Confusing cited | S6 ×4, S4 ×3, S8 ×2, S5 ×2, I1 ×2 | S7 ×6, S5 ×4, S4 ×2, S2 ×1, S3.2 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- baseline run-01 blocker [S4]: Step 3 (keep one of the two Entities) and step 5 (keep saved names) stopped me from giving the merged Entity a neutral name such as Customer and from renaming the Opportunity foreign key CRMCustomerID. The survivor stays named ERPCustomer while holding CRM rows, which I think is a poor name.
- baseline run-01 blocker [S8]: S8 (add a foreign key only for a column an edge names) and S5 (invent no crosswalk) kept me from linking the CRM column erp_customer_no to ERP customers, which I suspect is a real reference. I kept ErpCustomerNo as a plain Attribute and said in its definition that it is not matched.
- baseline run-01 confusing [S4]: Step 3 tie-break: both customer Entities are unlocked with 1 source and 1 Relationship, and no input shows downstream use. I kept ERPCustomer because the unlinked edge already points to it; the prompt does not say what to do on a tie.
- baseline run-01 confusing [S6]: For a saved Attribute it is not stated whether a listed from adds to the saved sources or replaces them (the schema only says saved Entity sources are kept). I listed both columns on the shared Attributes to be safe.
- baseline run-01 confusing [S8]: 'typed like the parent's key' could mean the parent's business key (STRING) or its generated key (BIGINT). S5 says the foreign key is BIGINT, so I used BIGINT.
- baseline run-01 confusing [S5]: A foreign key's from should cite the columns that give the parent's namespace, but the child tables here have no System column. I treated the child's own System as the namespace and said so in the note and basis.
- baseline run-01 confusing [S6]: In One-shot mode Project descriptions are not visible, so I could not tell when a definition may be omitted and wrote one every time.
- baseline run-01 comment: Reading S4 steps 2 and 3 together worked well: adding the link first and keeping the Entity the edge points to meant each Relationship was written only once. A short worked example of a merged multi-System Entity (grain with audit SourceSystemID, shared Attribute with two from columns, re-pointed Relationship, retire) would remove most of my doubts. The first sentences of S1 ('Builds model one Subject Area at a time') read as if a word is missing.
- baseline run-02 blocker [S4]: I believe the merged Entity should have a neutral name such as Customer, because it now holds CRM accounts too. S4.5 says keep saved names, and S4.3 with I3 says keep one Entity and retire the other, so I kept the name ERPCustomer.
- baseline run-02 blocker [S5]: The CRM column erp_customer_no probably points to the ERP customer, and a CRM-to-ERP Relationship would likely be right. No description or Context record says it holds an ERP id and cross-System matching needs explicit evidence, so I kept it as a plain Attribute with no Relationship.
- baseline run-02 confusing [S4]: The survivor rule (locked, else more sources, Relationships and downstream use) does not decide this case: both Entities have one source and one Relationship, and downstream use is not shown. I broke the tie with ERPCustomer because it is the parent in the Invoice edge. It is also unclear whether a merge may use a new neutral name; the S5 example says 'Customer grain'.
- baseline run-02 confusing [S6]: It is not stated whether a listed Entity source or Attribute from adds to or replaces the saved ones, so I listed the saved and the added values together.
- baseline run-02 confusing [I1]: naming_instructions say identifier Attribute names end with ID, but saved names such as SourceCustomerNo and ErpCustomerNo end with No, and S5 says keep saved names. I kept the saved names.
- baseline run-02 confusing [S5]: A foreign key's from should cite the columns that find the parent 'including its namespace', but when the namespace is the child's own System no column carries it (SourceSystemID is an audit column). I described the lookup in note instead.
- baseline run-02 comment: The input matches the S4.3 example (CRMCustomer and ERPCustomer), so the merge steps were easy to follow. A rule for naming a merged Entity and for breaking ties between equal candidates would remove my main doubts. I left the Invoice link nullable and unvalidated as S5 asks.
- candidate run-03 blocker [S9]: Could not add a Customer-to-Customer foreign key for t2.erp_customer_no (S6 describes a CRM account storing its ERP customer number) because no unlinked_analysis_edges item names that column; I kept it as a plain nullable Attribute.
- candidate run-03 blocker [S5]: Step 5 (keep saved names, rename only for a clear error) stopped me renaming the foreign keys SalesOrder.ERPCustomerID and Opportunity.CRMCustomerID to CustomerID, although both now point to the shared Customer and still carry System names.
- candidate run-03 confusing [S5]: Step 3 says keep one duplicate and retire the other, but S6 forbids naming an Entity after a System and step 5 allows renames only for clear errors. With both ERPCustomer and CRMCustomer System-named, it is unclear whether to keep one under its System name or create a neutral Customer and retire both (I did the latter). The I1 step 6 check, keeps one Entity and retires the other, reads like the former.
- candidate run-03 confusing [S7]: A foreign key's from should cite the child columns that look up the parent's full business identity including its namespace, but the namespace comes from the audit SourceSystemID, which table_index cannot cite. I stated it in the note instead.
- candidate run-03 confusing [S4]: The example shows a nullable=false foreign key from an Analysis edge, while S7 says an unvalidated reference is nullable. This edge has validation_result null, so I used nullable true even though the saved source Attribute was not nullable.
- candidate run-03 comment: I merged the per-System customer copies into one new Customer (sources t1 and t2, namespace through the audit SourceSystemID in the grain), re-pointed both Relationships and retired both old Entities. I replaced Invoice.SourceCustomerNo with a nullable CustomerID foreign key from t4.customer_no. Saved definitions such as 'VatNo from t1.vat_no.' look generated, so I wrote short definitions instead of relying on Project descriptions.
- baseline run-04 blocker [S4]: I believed the merged Entity should get a neutral name such as Customer, but S4.3 says keep one Entity and S4.5 says a rename means a new record plus retiring the old, so the survivor stays named ERPCustomer even though it now also holds CRM accounts.
- baseline run-04 blocker [S5]: I believed the Invoice foreign key's from should also cite the namespace, but that is the audit SourceSystemID, which may not be listed or cited, so it is described in the note only.
- baseline run-04 blocker [S5]: erp_customer_no on the CRM account looks like an ERP customer number, but S2 item 3 and S5 want a description or Context record and forbid inventing a crosswalk, so I carried it as a plain Attribute and added no link.
- baseline run-04 confusing [S4]: S4.3 says to keep the Entity with more sources, Relationships and downstream use, but here both are equal and downstream use is not shown; no tie-break is given (I picked ERPCustomer because the pending Invoice edge points at it).
- baseline run-04 confusing [S8]: S8 says a new foreign key is typed like the parent's key and S4.4 says align to the parent key's type, while S5 says the foreign key is BIGINT; the parent's business key is STRING and its generated key BIGINT, so I followed S5.
- baseline run-04 confusing [I1]: naming_instructions says identifier Attribute names end with ID, but saved keys end with No (SourceCustomerNo) and S5 says keep saved names; unclear which wins for a carried-over identifier such as ErpCustomerNo (I kept the saved name).
- baseline run-04 confusing [S6]: It says saved Entity sources are kept, but not whether from on a saved Attribute adds to or replaces its saved columns; I listed both the saved and the new column.
- baseline run-04 comment: S4.3 maps almost one-to-one onto this input, so the uncertainty is mostly about naming and tie-breaks rather than structure. A sentence in S4.3 on whether a merged Entity gets a neutral name, and how to break ties between equal Entities, would remove my main guesses. The S5 requirement that a foreign key's from cite its namespace also needs an example for single-System children.
- candidate run-05 blocker [S9]: Foreign keys may only be added for a column an unlinked edge names, so I could not link t2.erp_customer_no to the shared Customer, which S6 (References across Systems) describes as the right pattern for a CRM account that stores an ERP customer number. I kept ErpCustomerNo as a plain nullable Attribute.
- candidate run-05 blocker [S5]: Step 5 and S7 say keep saved names, and no details are given for SalesOrder or Opportunity, so I left the System-named foreign keys ERPCustomerID and CRMCustomerID in place although they now point to the shared Customer; a neutral CustomerID would be cleaner.
- candidate run-05 confusing [S5]: Step 3 says keep one of the two Entities, but both candidates are named after a System, which S6 forbids, and step 5 allows renaming only for a clear error (new record plus retire). It never says whether to create a neutral Entity and retire both; I created Customer and retired ERPCustomer and CRMCustomer, but keeping one would also read as compliant.
- candidate run-05 confusing [S7]: A foreign key should be nullable when the reference is 'unvalidated', but the S4 example uses nullable false and the saved source column is NOT NULL. I used nullable true on Invoice.CustomerID because the edge's validation_result is null.
- candidate run-05 confusing [S7]: The foreign key's 'from' must cite the child columns used to look up the parent's identity 'including its namespace', but here the namespace is the audit SourceSystemID, which is not a child column I can cite. I explained the namespace in a note and in the Relationship basis instead.
- candidate run-05 confusing [S2]: Point 4 says the GDS/GDS/GDS codes only show where a table is stored and the business System is its source's System, yet this run gives no source_context or ingestion_mapping, so I could only infer ERP versus CRM from the erp and crm schema names.
- candidate run-05 confusing [S7]: naming_instructions say identifier Attribute names end with ID, but saved names such as SourceCustomerNo, VatNo and ErpCustomerNo end with No, and S5 says keep saved names. I carried VatNo and ErpCustomerNo over unchanged and named only the new shared key SourceCustomerID.
- candidate run-05 comment: The S4 Invoice-to-Customer example matched this case and made the link step easy. The main gap is the survivor choice and its name when every duplicate is named after a System; a sentence such as 'if the candidates are named after Systems, create a neutral Entity and retire them all' would remove the guess. A short rule for the nullability of a foreign key whose source column is NOT NULL but whose edge is unvalidated would also help.
- candidate run-06 blocker [S5]: Step 5 (keep saved names) with S9 (add a foreign key only for an edge-named column) stopped me renaming SalesOrder.ERPCustomerID and Opportunity.CRMCustomerID to CustomerID, so two foreign keys to the shared Customer still carry System names.
- candidate run-06 blocker [S9]: S6 treats a CRM column holding the ERP customer number as a foreign key into the shared Entity, but no edge names t2.erp_customer_no, so I kept it as a plain nullable Attribute instead of a self-reference.
- candidate run-06 confusing [S5]: Step 3 says keep one duplicate and retire the other, but S6 forbids naming an Entity after a System and step 5 says keep saved names; both duplicates are System-named, so it is unclear whether to keep ERPCustomer or make a neutral Customer (I made Customer and retired both).
- candidate run-06 confusing [S5]: Step 2 adds the link to the edge's parent (ERPCustomer) before step 3 retires that parent; the prompt never says to point the new Relationship at the survivor, so I did.
- candidate run-06 confusing [S3.2]: Step 3 ranks survivors by downstream use, but model_summary shows only is_locked and counts; with 1 source and 1 Relationship each there is no tie-break.
- candidate run-06 confusing [S7]: The naming rule says identifier names end with ID, yet saved names (SourceOrderNo, ErpCustomerNo) end with No and S7 says keep saved names; I used SourceCustomerID for the new shared key and kept ErpCustomerNo.
- candidate run-06 confusing [S7]: A foreign key's from must cite the columns that find the parent's full identity including its namespace, but the namespace (audit SourceSystemID) is not a table_index column; I cited only t4.customer_no and put the namespace in the note.
- candidate run-06 confusing [S4]: Omit definition when the Project description defines the column, but one-shot mode shows no column descriptions (saved ones read like 'VatNo from t1.vat_no.'), so I wrote a definition for every Attribute.
- candidate run-06 comment: Merge, namespace-in-grain and the Invoice link were clear. The one real judgment call was a neutral Customer instead of a System-named survivor; one sentence in step 3 would settle it. I made the Invoice foreign key nullable because the edge's validation_result is null.

## 2026-10-28 · `r2-per_system_duplicates` · fixture `per_system_duplicates` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 0/3 | 3/3 |
| Valid answers (schema) | 0/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | – | 3.0 |
| Clarity (1–5) | – | 4.0 |
| Confidence (1–5) | – | 4.0 |
| Blockers cited | – | S6 ×2 |
| Confusing cited | – | S9 ×4, S5 ×3, S7 ×3, S3.2 ×1, S2 ×1, I1 ×1, S4 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-01 blocker [S6]: t2.erp_customer_no looks like a reference to the ERP customer number, but no Analysis link names it, so I kept it as a plain Attribute and did not link or match CRM and ERP customers.
- candidate run-01 confusing [S5]: Step 3 says to re-point a Relationship by listing it again with the same from, but step 5 says to rename a System-named foreign key (new Attribute plus retire the old one, whose Relationship then follows). Both apply to SalesOrder.ERPCustomerID and Opportunity.CRMCustomerID; I used step 5 and wrote new Relationships from the new CustomerID Attributes.
- candidate run-01 confusing [S9]: It allows a new foreign key only for a column an unlinked_analysis_edges item names, yet S5 step 5 needs new CustomerID Attributes from t3.customer_no and t5.account_id, which appear only in the saved Relationship basis text. 'Typed like the parent's key' also clashes with S7 (BIGINT), because the parent's business key in model_summary is STRING.
- candidate run-01 confusing [S3.2]: SalesOrder and Opportunity are not in entity_details, so I could not see their saved foreign-key source columns, nullability or definitions; I inferred the columns from the Relationship basis and set nullable true.
- candidate run-01 confusing [S7]: naming_instructions want identifier names to end in ID, but saved names (SourceCustomerNo, ErpCustomerNo) end in No and S5 says keep saved names; for the new Customer I used SourceCustomerID (as in the S7 example) and ErpCustomerID, and kept VatNo as a non-identifier.
- candidate run-01 confusing [S2]: Every table_index entry has the lake codes GDS/GDS/GDS and no source_context is given, so the ERP and CRM Systems (the namespaces) are visible only from the schemas erp and crm and from the Entity names.
- candidate run-01 comment: S5 step 3 and S6 cover the ERP/CRM merge well, and the S4 example matches the Invoice link closely. The only guesses were the renamed foreign keys on SalesOrder and Opportunity, whose saved details were not shown. One sentence saying that a renamed foreign key replaces the re-pointed Relationship would remove the main ambiguity.
- candidate run-02 confusing [S5]: Step 3 says to re-point each Relationship to the survivor with the same from, but step 5 says to rename the System-named foreign key (new Attribute plus retiring the old one, which also retires its Relationship). Both cannot apply to one foreign key and the text does not say which wins; I renamed and did not re-point.
- candidate run-02 confusing [S9]: A new foreign key is allowed only for a column named by unlinked_analysis_edges, yet S5 step 5 needs new CustomerID foreign keys on SalesOrder and Opportunity, which are not in entity_details or the edges; I took t3.customer_no and t5.account_id from their saved Relationship basis text.
- candidate run-02 confusing [S7]: 'Keep saved names' conflicts with the naming_instructions rule that identifier names end with ID when saved Attributes (SourceCustomerNo, ErpCustomerNo) move into a new neutral Entity; I used ID names (SourceCustomerID, ErpCustomerID).
- candidate run-02 confusing [I1]: Check 6 says every column must exist in table_index, but table_index lists tables only, so columns cannot be verified; I used only columns named in entity_details, the edge or a saved Relationship basis.
- candidate run-02 confusing [S4]: A definition may be omitted when the column's Project description already defines it, but descriptions are not visible and saved definitions look like placeholders ('VatNo from t1.vat_no.'), so I wrote a definition for every Attribute.
- candidate run-02 comment: The Customer merge, the Invoice link and the rename of the System-named foreign keys follow the steps closely. CRM's erp_customer_no looks like a reference to the ERP key, but with no Analysis link I kept it as a plain nullable Attribute as S6 says. I made the three new foreign keys nullable because their links are unvalidated or of unknown validation.
- candidate run-06 blocker [S6]: t2.erp_customer_no looks like a reference to the ERP customer key and I think a link would be right, but with no Analysis edge S6 says keep it a plain Attribute, so ErpCustomerNo stays plain and the same company stays two Customer rows.
- candidate run-06 confusing [S5]: Step 3 says re-point a Relationship by listing it again with the same from, while step 5 says rename the foreign key (ERPCustomerID to CustomerID), which retires that from. With a new neutral Customer I applied step 5: new CustomerID Attribute, new Relationship, old Attribute retired.
- candidate run-06 confusing [S9]: 'Add a foreign key only for a column an unlinked_analysis_edges item names' conflicts with the S5 step 5 renames on SalesOrder and Opportunity, whose columns (t3.customer_no, t5.account_id) are in no edge and whose details are not in entity_details. I followed S5 and took the columns from the Relationship basis text.
- candidate run-06 confusing [S9]: 'Typed like the parent's key' reads as the parent's business key type (STRING), but S7 and the S4 example say the foreign key is BIGINT. I used BIGINT.
- candidate run-06 confusing [S7]: naming_instructions say identifier names end with ID, but saved names such as SourceCustomerNo and ErpCustomerNo end with No, and it is unclear whether that is a clear error to fix. I used SourceCustomerID for the new shared key and kept ErpCustomerNo and VatNo as saved.
- candidate run-06 comment: Since SalesOrder and Opportunity details are not inline, I inferred their foreign key source columns from the Relationship basis text. The merge flow (neutral Customer, audit SourceSystemID in the grain, retire both System-named Entities) was easy to follow from S5 step 3, S6 and S7. A short worked example of a System-named merge that also renames foreign keys would remove the doubts above.

## 2026-10-28 · `r3-per_system_duplicates` · fixture `per_system_duplicates` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 0/3 | 3/3 |
| Valid answers (schema) | 0/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | – | 3.0 |
| Clarity (1–5) | – | 4.0 |
| Confidence (1–5) | – | 4.0 |
| Blockers cited | – | S5 ×3, S6 ×1 |
| Confusing cited | – | S5 ×5, S4 ×3, S6 ×1, I1 ×1, S7 ×1, S2 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-01 blocker [S5]: Step 5 allows renaming a foreign key only when its Entity's details are shown, so SalesOrder.ERPCustomerID and Opportunity.CRMCustomerID could only be re-pointed and keep names of retired Entities, although I believe CustomerID would be the better name.
- candidate run-01 confusing [S6]: The namespace rules assume source_context and ingestion_mapping, which are not given. table_index shows GDS for tenant, system and connection on every table, so the ERP and CRM Systems could only be read from the schema names erp and crm and from the Entity names.
- candidate run-01 confusing [S5]: Step 3 says merge only when grains and business identities clearly match, yet it names CRMCustomer and ERPCustomer as the example to merge. Here the grains are different keys (SourceCustomerNo, SourceAccountID) and only the definitions suggest one subject, so how clear is clear enough is not stated.
- candidate run-01 confusing [I1]: Check 6 says a merge leaves one Entity and retires the others, while S5 step 3 says to create a neutral Entity and retire all the System-named duplicates. I followed S5.
- candidate run-01 confusing [S7]: S7 and S5 step 5 say keep saved names and use Source<Entity>ID, while naming_instructions says identifier names end with ID. Saved names such as ErpCustomerNo and VatNo end with No, and it is unclear whether Attributes moved unchanged into a new neutral Entity should keep them. I kept them and used SourceCustomerID only for the merged key.
- candidate run-01 comment: The merge path is well covered by S5 step 3 and S6, and the rule to cite audit SourceSystemID in the grain is easy to apply. A short worked example of a neutral merge with a shared key Attribute would settle the naming and note questions I hit. I kept ErpCustomerNo as a plain nullable Attribute because no Analysis link supports a reference.
- candidate run-03 blocker [S5]: After merging ERPCustomer and CRMCustomer, SalesOrder.ERPCustomerID and Opportunity.CRMCustomerID should be renamed CustomerID, but their Entities' details are not shown, so I could only re-point the Relationships; the names still point at retired System-named Entities.
- candidate run-03 blocker [S6]: The CRM column erp_customer_no looks like a reference to ERP customers, but with no Analysis link I kept it as a plain Attribute, so ERP and CRM Customer rows stay unmatched.
- candidate run-03 confusing [S5]: 'Keep saved names' versus the naming instruction that identifiers end with ID: unclear whether Attributes moved into the new merged Entity (ErpCustomerNo, VatNo) keep their old names or follow the ID rule. I kept them and named only the shared business key SourceCustomerID.
- candidate run-03 confusing [S4]: Notes are for values that are not a straight copy, including a combination of sources, but an Attribute fed by two tables (SourceCustomerID, CustomerName) is a straight copy per row; unclear whether it needs a note. I added none.
- candidate run-03 confusing [S5]: Merging ERP and CRM customers as one thing while S7 says to invent no crosswalk means the same real customer still appears once per System. I assumed that is intended, separated by SourceSystemID in the grain.
- candidate run-03 comment: The merge into a neutral Customer, the re-pointed Relationships and the Invoice foreign key with the ERP namespace in its note follow the steps directly. A worked example of a System-named merge where the child Entities' details are not shown would remove my main doubt. Column descriptions are missing, so several definitions rest on column names only.
- candidate run-06 blocker [S5]: Step 5 with S9 allows renaming a foreign key only when its Entity's details are shown. SalesOrder and Opportunity are not in entity_details, so I only re-pointed their Relationships; ERPCustomerID and CRMCustomerID keep System-named names after the merge, which I believe is wrong, and the SourceSystemID lookup note had to go into the Relationship basis.
- candidate run-06 confusing [S2]: No source_context is given and table_index shows only the lake codes (GDS / GDS / GDS), so the business System of t1 to t5 is not stated. I inferred ERP and CRM from the schema names and Entity definitions, yet the namespace rules in S6 and S7 depend on knowing the Systems.
- candidate run-06 confusing [S5]: Keep saved names (step 5, S7) versus the naming_instructions rule that identifier names end with ID: unclear whether Attributes moved into a new Entity (ErpCustomerNo, VatNo) should be renamed. I kept them and named only the merged key SourceCustomerID.
- candidate run-06 confusing [S4]: The Invoice example adds a foreign key to Customer with no note about SourceSystemID, while S7 requires that note when the namespace is the audit SourceSystemID.
- candidate run-06 confusing [S4]: A list in from means both 'fed by several tables' and 'lookup on several columns', so it is not obvious whether a note is needed to show that SourceCustomerID and CustomerName are a union of per-table copies, not a combination of columns.
- candidate run-06 confusing [S5]: Step 3 says merge only when grains clearly match, and S7 says cross-System matching needs explicit evidence. I read the first as merging Entities and the second as not matching rows, but the line between them could be stated.
- candidate run-06 comment: Clear enough that the merge, the re-pointed Relationships and the Invoice link followed directly from S5 and S6. Showing SalesOrder and Opportunity in entity_details whenever a merge re-points their Relationships would let the System-named foreign keys be fixed. S6 says the instance column fills SourceSystemID, but does not say what fills it when the copies are different Systems.

## 2026-10-28 · `r4-dups` · fixture `per_system_duplicates` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 2.0 | 3.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 4.0 | 4.0 |
| Blockers cited | S5 ×4, S4 ×3 | S6 ×3 |
| Confusing cited | S4 ×6, S5 ×4, I1 ×2, S6 ×2, S2 ×1, S8 ×1 | S5 ×6, S3.2 ×2, S2 ×1, S4 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- baseline run-01 blocker [S4]: Step 5 (keep saved names; rename only for a clear error) stopped me giving the survivor a neutral name like Customer. It is still called ERPCustomer while holding CRM accounts, and Opportunity.CRMCustomerID now points at it. A rename means a new Entity plus retiring both, with unknown downstream risk.
- baseline run-01 blocker [S5]: No crosswalk without explicit evidence: I did not relate CRM ErpCustomerNo to ERP SourceCustomerNo although the name suggests a match. It is kept as a plain nullable Attribute.
- baseline run-01 confusing [S4]: Step 3 tie-break counts downstream use, but model_summary and entity_details carry none, and both Entities tie on sources (1 each) and Relationships (1 each). I chose ERPCustomer because the Invoice edge targets it and gives it a second Relationship.
- baseline run-01 confusing [S5]: Type of a foreign key: S5 says BIGINT, S8 says typed like the parent's key, S3 and S4 compare with the parent key's type. The parent's natural key is STRING and its generated key BIGINT. I used BIGINT, like the saved foreign keys.
- baseline run-01 confusing [S5]: A foreign key's from must cite the lookup columns including the namespace, but from only accepts table columns, so audit SourceSystemID can only go in a note or basis. Unsaid: whether saved children of the survivor (SalesOrder.ERPCustomerID) now need the namespace too; I left it.
- baseline run-01 confusing [S4]: Step 3 says to re-point the other Entity's Relationship first and then retire the Entity, whose Relationships follow. I assumed the re-pointed Opportunity Relationship survives the retire.
- baseline run-01 confusing [I1]: audit_columns declares SourceSystemID nullable, while S5 says natural keys are never nullable and the grain uses it as part of the key. Also naming_instructions say identifier names end with ID, but saved keys such as SourceCustomerNo end with No; I kept them under S4 step 5.
- baseline run-01 confusing [S2]: table_index shows only GDS lake codes and no source_context is given, so the per-System split (ERP vs CRM) is inferred from schema and Entity names only.
- baseline run-01 comment: S4 step 3 names exactly this pair, so the merge path was clear and the schema constrained the output well. The least clear part is how a multi-System merge should treat names and the foreign keys of children that stay. A short worked example of a merge, with its re-pointed Relationship, would remove most of my doubts.
- baseline run-02 blocker [S4]: Step 5 (keep saved names) and step 3 (keep one) made me keep the survivor name ERPCustomer and the child key names ERPCustomerID and CRMCustomerID, although the survivor now holds CRM accounts too. A neutral name such as Customer reads better, but it needs a new Entity, retiring both, and re-pointing every Relationship.
- baseline run-02 blocker [S5]: Cross-System matching needs explicit evidence (also S2 item 3), so I added no link from the CRM column erp_customer_no to ERP customers, although the name suggests one. No description or Context record says the column holds the ERP's id.
- baseline run-02 confusing [S4]: Step 3 says keep one of the two Entities, step 5 says keep saved names, and the S5 example calls a multi-System Entity Customer. It is not stated whether the survivor keeps its System-prefixed name or gets a neutral one.
- baseline run-02 confusing [S4]: Step 3 tie-break (more sources, Relationships and downstream use): both Entities have 1 source and 1 Relationship, and the input shows no downstream use. I chose ERPCustomer only because the Invoice edge points at it, which is a guess about the intended order.
- baseline run-02 confusing [S6]: For a saved Attribute whose from gains a column (SourceCustomerNo), it is unclear whether from replaces or adds to the saved list. I sent the complete list, but for Entity sources S6 says saved ones are kept, so I sent only t2.
- baseline run-02 confusing [I1]: naming_instructions say identifier Attributes end with ID, but saved identifiers end with No (SourceCustomerNo, ErpCustomerNo). It is unclear whether the carried-over ErpCustomerNo should be renamed; I kept the saved name.
- baseline run-02 confusing [S5]: A foreign key's from should cite the child columns that look up the parent's identity including its namespace, but here the namespace is the audit SourceSystemID, which is not a table_index column. I cited only t4.customer_no and described the namespace in the note.
- baseline run-02 comment: I followed S4 step 3 literally for the merge: ERPCustomer survives with t2 added, the Opportunity link is re-pointed and CRMCustomer is retired, so coverage stays at 5 of 5 Objects. The unvalidated Invoice edge became a nullable BIGINT foreign key with the raw SourceCustomerNo kept. Physical column descriptions are not inline, so I wrote definitions for the new Attributes instead of relying on Project descriptions.
- candidate run-03 blocker [S6]: t2.erp_customer_no looks like a CRM-to-ERP customer reference, but with no active Analysis link or Context record the rule makes it a plain Attribute, so I added no foreign key and no cross-System match.
- candidate run-03 confusing [S5]: Renaming a foreign key says to keep the saved definition, but the saved definitions here repeat the retired name ('ERPCustomerID from t3.customer_no.'), so I wrote new definitions as the S4 example does.
- candidate run-03 confusing [S3.2]: table_index shows every table as GDS/GDS/GDS and source_context and ingestion_mapping are null, so separate ERP and CRM Systems with one instance each is only inferred from the schema and Entity names; the ERP/CRM namespace notes and the missing SourceInstanceCode rest on that.
- candidate run-03 confusing [S5]: Names says keep saved names but also to name new-Entity Attributes by naming_instructions; it is unclear whether non-key numbers such as VatNo and ErpCustomerNo count as identifiers, so I renamed them to end in ID (VatID, ErpCustomerID).
- candidate run-03 comment: The second S4 example matches this input closely, so the merge, rename and retire steps were easy to follow. I wrote the Attribute definitions from column names alone because S9 says descriptions are not inline, so the wording may differ from what the business meant. One sentence saying which columns count as identifiers for the ID-suffix rule would remove the last naming guess.
- baseline run-04 blocker [S4]: Step 3 (keep one Entity, retire the other) and step 5 (keep saved names) made me keep the System-coded name ERPCustomer for an Entity that now also holds CRM rows; I believed a neutral name such as Customer was right.
- baseline run-04 blocker [S5]: Keep saved names (with S4 step 5) made me keep SourceCustomerNo and ErpCustomerNo, although I1 naming_instructions say identifier Attributes end with ID; I thought SourceCustomerID and ErpCustomerID would follow the settings better.
- baseline run-04 blocker [S5]: Cross-System matching needs explicit evidence, and S8 limits new foreign keys to edge columns, so I added no Relationship or crosswalk for t2.erp_customer_no even though I believed it likely holds the ERP customer number.
- baseline run-04 confusing [S4]: The step 3 tie-break (more sources, Relationships, downstream use) cannot choose between ERPCustomer and CRMCustomer: both are unlocked with one source and one Relationship, and no downstream use is shown. I chose ERPCustomer because the Invoice edge points at it.
- baseline run-04 confusing [S5]: The foreign key's from must cite the child columns that look up the parent's identity including its namespace, but the namespace is the audit SourceSystemID, which cannot be listed or cited. I cited only t4.customer_no and described the namespace in note and basis.
- baseline run-04 confusing [S8]: S8 says the foreign key is typed like the parent's key, but S5 says the foreign key is BIGINT; the parent's business key is STRING and only its generated key is BIGINT. I used BIGINT.
- baseline run-04 confusing [S6]: It is not stated whether a listed from or sources on a saved record replaces or adds to the saved values. I gave both columns for the shared Attributes and only the added table t2 for the Entity sources.
- baseline run-04 confusing [S4]: Step 2 asks for a supported cardinality, but the edge has validation_result null and no measured cardinality. I inferred many_to_one from the grains and keys and made the key nullable.
- baseline run-04 comment: The merge steps were clear because S4 step 3 names this exact pair. A short worked example of a merge answer (survivor, re-pointed Relationship, retire) and a rule for the survivor's name would remove most of my guesses. The second sentence of S1 is garbled (Builds model one Subject Area at a time, so they can leave links...), so its subject is unclear.
- candidate run-05 blocker [S6]: CRM's erp_customer_no looks like a reference to the ERP customer key, but no active Analysis link or Context record names it, so I could not add a Customer-to-Customer foreign key and kept it as a plain Attribute.
- candidate run-05 confusing [S5]: Step 5 says the renamed foreign key keeps 'the saved nullable and definition', but the saved definitions are placeholders such as 'ERPCustomerID from t3.customer_no.' that name the retired Attribute; it is unclear whether to copy them or rewrite them (I rewrote them, as the S4 example does).
- candidate run-05 confusing [S5]: Step 5 says Attributes of a new Entity are named by naming_instructions, while 'keep saved names' and I1 step 5 ('fix only clear naming errors') point the other way; unclear whether moved Attributes such as ErpCustomerNo (I renamed it to ERPCustomerID) or VatNo (I kept it) must follow the ID rule.
- candidate run-05 confusing [S2]: table_index puts every table under GDS / GDS / GDS and source_context and ingestion_mapping are null, so the business System of each table is not given; S6 and S7 still ask for the System namespace in notes and for audit SourceSystemID, so I inferred ERP and CRM from the schema names and Entity definitions.
- candidate run-05 comment: The second S4 example matches this input closely, but there Opportunity is not in entity_details and is only re-pointed, while here it is in entity_details, so I followed the S5 rename rule instead of copying the example. A short note that the Opportunity branch of the example depends on entity_details membership would avoid that trap. The rest of S4, S5 and S7 was consistent.
- candidate run-06 blocker [S6]: t2.erp_customer_no (the CRM account's ERP customer number) looks like a reference to the ERP customer key, but with no active Analysis link or Context record I kept it as a plain nullable Attribute (ErpCustomerID) instead of a self-referencing foreign key on Customer.
- candidate run-06 confusing [S5]: Renaming a foreign key says to carry over the saved definition, but the saved definitions here are stubs such as 'ERPCustomerID from t3.customer_no.' that name the retired Attribute, so I wrote a short real definition instead (as the S4 example does). It also does not say which basis the renamed foreign key's new Relationship should carry; I reused the saved Analysis basis and added 'renamed after the merge'.
- candidate run-06 confusing [S5]: Step 5 says keep saved names, yet also says Attributes of a new Entity are new records named by naming_instructions. For the new Customer I renamed the identifiers (SourceCustomerNo and ErpCustomerNo to ...ID) and kept VatNo and SegmentCode, because it is not stated whether a VAT number counts as an identifier.
- candidate run-06 confusing [S4]: S4 says to omit definition when the single source column's Project description already defines it, but S9 says column descriptions are not inline and every new Attribute needs a definition; I wrote a definition for every new Attribute.
- candidate run-06 confusing [S3.2]: source_context and ingestion_mapping are null and table_index shows every table under GDS/GDS/GDS, so which System each table comes from is only inferable from the schema names (erp, crm) and Entity names; I used that for the ERP and CRM namespace notes.
- candidate run-06 comment: The S4 merge example matches this input closely, so the Customer merge, the foreign key renames and the Invoice link were easy to follow. S5 steps 3 and 5 both cover the same Relationship (re-point versus rename) and needed a second read; a one-line decision rule would help. I did not add SourceInstanceCode because nothing shows more than one instance per System.

