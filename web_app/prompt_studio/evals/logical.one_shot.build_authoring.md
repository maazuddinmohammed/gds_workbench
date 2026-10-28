# Test log: logical.one_shot.build_authoring

## 2026-10-28 · `r1-sales_two_instances` · fixture `sales_two_instances` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 4.0 | 4.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 3.3 | 4.0 |
| Blockers cited | S5 ×2, I1 ×2 | S7 ×4 |
| Confusing cited | S5 ×9, S4 ×2, I1 ×1, S6 ×1 | S7 ×3, S4 ×2, S5 ×1, S6 ×1, S3.1 ×1, S3.2 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- baseline run-01 blocker [S5]: A Relationship names only one child Attribute and one parent Entity, so the ORD_UK-only scope of Opportunity to Customer (and the instance part of every lookup) can be stated only in the FK Attribute's note and definition and in the basis text, not structurally.
- baseline run-01 confusing [S5]: audit SourceSystemID is defined as the originating source System identifier, but this area has two Connections (ORD_UK, ORD_DE) of one System. S5 says to cite it in the grain and not add a namespace key when it is listed, yet it is unclear whether it separates instances, so I also added SourceInstanceID (natural key from source_instance) and cited both in the grain.
- baseline run-01 confusing [S4]: Step 3 says to note the rule behind a recorded total, while S6 allows a note only for non-straight copies; it is unclear where the TotalAmount rule goes, so I put it in the Attribute definition.
- baseline run-01 confusing [S5]: 'its from cites the child columns' could mean the FK Attribute's from or the Relationship's from; I used the FK Attribute's from, since a Relationship's from is only an entity and attribute.
- baseline run-01 confusing [I1]: naming_instructions does not say whether code or number columns (order_no, line_no, product_code, source_instance) are Identifier Attributes; I ended them all with ID (SourceLineID, SourceProductID, SourceInstanceID) and kept the segment classification as SegmentCode.
- baseline run-01 comment: The evidence was consistent and the empty existing/neighbor lists made the reuse checks trivial. The hardest judgments were instance handling (SourceSystemID versus the source_instance column), the UK-only Opportunity link, and typing Department as reference rather than core. A worked example of a multi-instance Entity with both an audit SourceSystemID and a source_instance column would remove most doubt.
- candidate run-02 blocker [S7]: Because audit_columns lists SourceSystemID I could not add an explicit namespace key Attribute from source_instance, which I think is safer: the audit column is defined as the originating System, and ORD_UK and ORD_DE are two instances of one System (ORDERS_APP).
- candidate run-02 blocker [S7]: The rule that foreign keys are nullable while links are unvalidated forced nullable on SalesOrder.CustomerID and SalesOrderLine.SalesOrderID, although their source columns are non-null and the references look mandatory.
- candidate run-02 confusing [S7]: S6 and S7 say the instance column feeds the audit SourceSystemID, but audit_columns defines it as the 'Originating source System identifier'; it is unclear whether it is filled per instance, and no field exists to say source_instance feeds it (I put that in definitions and in the foreign-key from lists).
- candidate run-02 confusing [S4]: The example name SourceCustomerNo conflicts with naming_instructions (identifiers end in ID), and neither says whether a line number or product code is an identifier; I used Source<Entity>ID for entity identifiers and kept LineNumber and ProductCode.
- candidate run-02 confusing [S5]: Item 3 says to note the rule for a recorded total (TotalAmount), but S4 allows notes only on values that are not straight copies and no derivation rule is documented in this evidence; I added no note.
- candidate run-02 comment: The answer is five Entities (one per subject, UK and German rows merged) and four many_to_one Relationships from the Analysis links, with the CRM opportunity link marked as using the ORD_UK namespace. Judgment calls the prompt leaves open: Department typed reference, Opportunity typed core, and a 'highest GDSBatchID is current' filter noted on the appended source tables. Everything else followed the rules directly.
- baseline run-03 blocker [I1]: naming_instructions asks for relationship names, but a Relationship in required_output_schema has no name field (additionalProperties is false), so I gave none.
- baseline run-03 blocker [I1]: Identifier Attribute names must end with ID, so I named line_no SourceLineID and product_code SourceProductID, although LineNumber and ProductCode would read more clearly.
- baseline run-03 confusing [S5]: SourceSystemID is defined as the originating System, but ORD_UK and ORD_DE are two Connections of one System (S2), so it may not separate the instances. The rule says to cite it in the grain and, when it is audited, does not ask for a namespace Attribute. I cited it and also kept source_instance as a non-null natural key (SourceInstanceID); please say which is intended.
- baseline run-03 confusing [S5]: The type list (BIGINT, DECIMAL(p,s), STRING, DATE, TIMESTAMP) does not say whether inferred VARCHAR(n), CHAR(1) and INT are accepted or should become STRING. I kept the inferred types.
- baseline run-03 confusing [S5]: Every Analysis edge has validation_result null, so the optional-or-unvalidated rule makes every foreign key nullable and asks for a raw identifier copy, even where the source column is registered NOT NULL. It is unclear whether that is intended, and whether the raw copy is needed when the identifier is already a natural key part (SalesOrderLine.order_no).
- baseline run-03 confusing [S5]: A fixed namespace that is not a column (opportunity.erp_customer_no belongs to the UK database only by its description) cannot go in from, which cites columns. I put it in the Attribute note.
- baseline run-03 confusing [S6]: No field says an Entity keeps only the current row (highest GDSBatchID). I used a note on the table source, but S6 only describes notes on Attributes.
- baseline run-03 comment: The ordered design steps and the S5 key rules led to one clear structure, and the I3 checklist matched the schema well. The main gap is an example of one System with two instances where SourceSystemID is audited, because the key decision depends on it. The long S3 and S5 text holds the instance and lookup rules that matter most here, so they are easy to miss on a first read.
- baseline run-04 blocker [S5]: The rule says that when audit_columns lists SourceSystemID I cite it in the grain and add no namespace key Attribute. So I left out an explicit instance key (from source_instance) on Customer, Department, SalesOrder and SalesOrderLine. But ORD_UK and ORD_DE are two Connections of one System (ORDERS_APP) and I1 describes SourceSystemID as a System identifier, so it may not separate them; I believe an explicit instance key would be safer.
- baseline run-04 confusing [S5]: It is unclear whether audit SourceSystemID identifies a System or a Connection (instance). S2 keeps the two apart, but S5 treats 'SourceSystemID/source namespace' as one thing.
- baseline run-04 confusing [S5]: A foreign key's from must include the namespace, but the Opportunity to Customer link needs a fixed value (the UK database) that no CRM column carries. S3 also says never write connection keys, so it is unclear whether naming ORD_UK in a note or basis is allowed.
- baseline run-04 confusing [S4]: S4.3 says to note the rule for a derivable recorded total, but S6 limits note to values that are not straight copies and says to omit definitions the Project description already covers. I put the note in the TotalAmount definition.
- baseline run-04 confusing [S5]: S5 lists BIGINT, DECIMAL, STRING, DATE and TIMESTAMP as types, but the evidence uses VARCHAR(n), CHAR(1) and INT; it is unclear whether to keep them or convert to STRING. Also unclear whether line_no (LineNumber) and product_code (SourceProductID) count as identifiers that must end with ID (I1).
- baseline run-04 comment: The prompt was clear on keys, foreign keys, coverage and the current-row rule for GDSBatchID. Most of my uncertainty is how instances of one System are kept apart, which one explicit line about SourceSystemID versus Connection codes would settle. I kept one Entity per subject across both instances and added no Product, Segment or crosswalk Entities.
- candidate run-05 blocker [S7]: The rule that an unvalidated foreign key is nullable made me mark SalesOrder.CustomerID and SalesOrderLine.SalesOrderID nullable, although their source columns are NOT NULL and the parent is mandatory; I would otherwise have made them non-nullable.
- candidate run-05 confusing [S7]: naming_instructions say identifier Attributes end with ID, but it is not stated whether code or number columns (customer_no, line_no, product_code) count as identifiers; I named them SourceCustomerID, SourceLineID and SourceProductID, which sits oddly beside the S4 example name SourceCustomerNo.
- candidate run-05 confusing [S6]: S6 says the instance column is never a business Attribute and S7 says a foreign key's from cites the parent's namespace; it is not explicit that source_instance should appear in an FK's from, which I did.
- candidate run-05 confusing [S3.1]: Department fits both reference (a short list of codes and names) and core; the type descriptions do not settle it and I chose reference.
- candidate run-05 comment: All needed evidence was inline, and the audit SourceSystemID rule kept the namespace out of the Attributes cleanly. S5 step 3 mentions recorded totals that a documented rule could derive, but no rule is given for total_amount, so I kept it as a plain recorded fact. The main judgment calls were the Department type, the nullable foreign keys and the Source...ID names.
- candidate run-06 blocker [S7]: Foreign keys must be nullable when the link is unvalidated, so SalesOrder.CustomerID and SalesOrderLine.SalesOrderID are nullable although their source columns are registered NOT NULL; I would otherwise have marked them required.
- candidate run-06 confusing [S4]: The example names the identifier SourceCustomerNo, but this run's naming_instructions require identifiers to end in ID; I followed S7 (naming_instructions win), and it is unclear whether line_no and product_code count as identifiers (I used SourceLineID and SourceProductID).
- candidate run-06 confusing [S7]: Unclear whether the audit SourceSystemID must be cited in the grain of a single-instance Entity such as Opportunity; I read 'An Entity from one instance needs none' as exempting it.
- candidate run-06 confusing [S3.2]: It says never write connection keys, while S6 asks the note to state the other System's namespace; I named ORD_UK in prose only, never as a table citation.
- candidate run-06 comment: The evidence was small and consistent, so the structure (five Entities, four foreign keys, audit SourceSystemID in the multi-instance grains, ORD_UK-only Opportunity lookup) followed directly from S6 and S7. The weakest calls were typing Department as reference rather than core and the ID-suffix names for line_no and product_code. A structured way to state a fixed namespace for a cross-System foreign key would help, since it now lives only in note and basis text.

## 2026-10-28 · `r2-sales_two_instances` · fixture `sales_two_instances` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 0/3 | 3/3 |
| Valid answers (schema) | 0/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | – | 4.0 |
| Clarity (1–5) | – | 4.0 |
| Confidence (1–5) | – | 4.0 |
| Blockers cited | – | S7 ×3 |
| Confusing cited | – | S7 ×7, S5 ×4, S3.1 ×2, S6 ×2, I1 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-02 blocker [S7]: The unvalidated-link rule made SalesOrderLine.SalesOrderID and SalesOrder.CustomerID nullable even though the source columns are NOT NULL and a line cannot exist without its order; I believed required was the better design.
- candidate run-02 confusing [S7]: The naming rule says identifier Attributes end with ID, but it is unclear for codes and sequence numbers (product_code, line_no); I used SourceProductID and LineNumber.
- candidate run-02 confusing [S7]: Type mapping is unclear: sources use VARCHAR(n), CHAR(n) and INT while the prompt lists BIGINT, DECIMAL, STRING, DATE, TIMESTAMP; I used STRING for text and kept INT.
- candidate run-02 confusing [S7]: Audit SourceSystemID is never listed, so the instance column (source_instance) is cited nowhere and the namespace part of each business key appears only in grain text.
- candidate run-02 confusing [S5]: Step 3 says to state the rule for a source-recorded total, but no rule is documented for total_amount, so I only noted it is unvalidated against the lines.
- candidate run-02 confusing [S3.1]: reference versus core is unclear for a small Department table with only an id and a name; I chose reference because the profile shows about 14 values.
- candidate run-02 comment: The S4 example and the S6 bullets covered the two-instance case well. The note field exists on Attribute, column source and table source, and S7 says only 'the note', so where to put the SourceSystemID lookup remark was a guess. A worked multi-instance foreign key with its note would remove most remaining doubt.
- candidate run-03 blocker [S7]: The rule that an unvalidated foreign key must be nullable even when the source column is NOT NULL forced nullable on SalesOrder.CustomerID and SalesOrderLine.SalesOrderID, where I believe an order always has a customer and a line always has an order.
- candidate run-03 confusing [S7]: The Databricks type list (BIGINT, DECIMAL, STRING, DATE, TIMESTAMP) has no INT, VARCHAR or CHAR; it is unclear whether to keep INT (I did) and whether VARCHAR(n) and CHAR(1) become STRING (I did).
- candidate run-03 confusing [S6]: The batch and instance columns may not be listed as Attributes, and no rule says where to record that the current row is the highest GDSBatchID or that source_instance fills SourceSystemID; I used notes on the table sources.
- candidate run-03 confusing [S5]: Step 3 says to state a documented derivation rule for a recorded total, but nothing here documents how total_amount is derived, so it is unclear whether to relate it to the line amounts; I kept it as a plain recorded fact.
- candidate run-03 confusing [S3.1]: Department (id and name only) fits both core and reference in logical_entity_types; I chose reference.
- candidate run-03 confusing [S7]: The naming rule that identifier Attributes end with ID does not say whether a line number or a product code counts as an identifier; I used LineNumber and ProductCode.
- candidate run-03 comment: The messages gave enough rules to decide every Entity, key and foreign key without guessing, and the SourceSystemID namespace rules were easy to apply. The weakest spots are the free choices left open: the Entity type for a two-column list, the type mapping, and where to record the latest-load filter. The CRM-to-UK-customer lookup was well covered by S6 and S7 together.
- candidate run-06 blocker [S7]: The rule to make unvalidated foreign keys nullable even when the source column is NOT NULL made me drop the mandatory constraint I believed right for SalesOrder.CustomerID and SalesOrderLine.SalesOrderID, since an order always has a customer and a line always has an order.
- candidate run-06 confusing [S7]: naming_instructions say identifier Attribute names end with ID but do not say whether a line number or a product code counts as an identifier. I named them SourceSalesOrderLineID and SourceProductID; LineNumber and ProductCode may be what is wanted.
- candidate run-06 confusing [S5]: Step 3 says to state the derivation rule for a recorded total, but the evidence documents no rule for total_amount. I kept the fact and wrote that agreement with the line amounts is not validated; it is unclear whether a hypothetical rule should be stated.
- candidate run-06 confusing [S6]: Nothing in the answer shape records that source_instance fills SourceSystemID or that the highest GDSBatchID row is current. I put both in table-source notes; it is unclear whether a note is the intended place for the SourceSystemID fill.
- candidate run-06 confusing [S5]: Department fits both reference (a short list of codes and names) and core (a main business thing with its own identity), and the type descriptions do not decide between them. I chose reference.
- candidate run-06 confusing [S7]: Type guidance lists STRING, BIGINT, DECIMAL, DATE and TIMESTAMP, but the evidence has VARCHAR(n), CHAR(1) and INT. I used STRING for text and kept INT; it is unclear whether those inferred types count as supported.
- candidate run-06 confusing [I1]: Check 7 says no Attribute is a new Entity's <Entity>ID, which could be read to forbid the foreign key SalesOrderID on SalesOrderLine because SalesOrder is also new. I read it as forbidding only an Entity's own generated key, as in the S4 example.
- candidate run-06 comment: The rules for multi-instance tables, the SourceSystemID grain and the cross-System foreign key note were each stated once and were enough to decide. A worked example of a multi-instance child's foreign key note, such as Customer to Department, would remove my main doubt about wording. I made all four foreign keys nullable and fixed the Opportunity lookup to ORD_UK because its column description names the UK database.

