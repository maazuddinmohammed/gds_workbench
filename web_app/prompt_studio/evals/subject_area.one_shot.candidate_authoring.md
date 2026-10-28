# Test log: subject_area.one_shot.candidate_authoring

## 2026-10-28 · `r1-enterprise_40` · fixture `enterprise_40` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 3/3 | 3/3 |
| Valid answers (schema) | 3/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | 4.7 | 3.0 |
| Clarity (1–5) | 4.0 | 4.0 |
| Confidence (1–5) | 4.0 | 4.0 |
| Blockers cited | – | – |
| Confusing cited | S4 ×6, S5 ×3, S3 ×1, S1 ×1, I3 ×1 | S5 ×3, S6 ×3, S1 ×2, S4 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- baseline run-01 confusing [S5]: The aim of about 5 to 12 tables and the split trigger of roughly 400 columns or 20 tables do not say what to do when the order-to-cash block is about 15 tables but under 100 columns: 'up to about 20 tables is fine' and 'aim for 5 to 12' point different ways, and I3 adds 'unless the evidence says otherwise' without saying what counts. The Order Capture, Fulfilment, Invoicing example reads like a prompt to split even though both split triggers are far from met.
- baseline run-01 confusing [S3]: S3 calls column_count the main measure of design work, but with tables of 3 to 9 columns every candidate area is far under 'a few hundred columns', so only the table count ever constrains the answer.
- baseline run-01 confusing [S4]: Step 4 keeps same-subject tables from different Systems in one area and step 6 shares master tables into every area that uses them; it is unclear whether a shared customer table must travel with its cross-System twin (CRM account) into each area, or whether one common area is enough. I used one common area and shared only the ERP customer elsewhere.
- baseline run-01 confusing [S4]: Step 4 and S5 speak of tables from different Systems or Systems repeating a structure, but the two HR member-firm table sets (cds_ and cym_) come from the same System (HR_SUITE); I applied the same-subject rule by analogy.
- baseline run-01 confusing [S1]: S1 asks for coherent business capabilities of workable size, while the output schema description says 'broad business domains' and the name example is 'Sales or Support'; the expected granularity is unclear.
- baseline run-01 comment: I split the order-to-cash tables into Order Capture, Fulfilment and Invoicing to keep every area within 5 to 12 tables, sharing customer, order, product, currency and payment-terms tables as S4 step 6 asks; one 15-table area would also have fit S5. The ERP customer and CRM account sit together in the CRM area, both HR member-firm table sets share one area, and only the load log and staging copy are unassigned. I added customer addresses to Fulfilment and Invoicing from the 'billing and delivery' description alone, since no column or link ties them to those documents.
- candidate run-02 confusing [S5]: Steps 3, 4 and 6 allow two readings for the CRM tables beyond the customer account: join the order-to-cash area (never one area per System), or form their own area that shares the ERP customer table. Only the CRM and ERP customer accounts are forced together, so I merged all CRM tables into one Sales and Marketing area.
- candidate run-02 confusing [S6]: A typical area has 10 to 30 tables and merging starts below about 5, so nothing says what to do with 5 to 9 tables. Finance has 5 own tables plus the shared currency table, and I kept it as its own distinct domain.
- candidate run-02 confusing [S5]: S3 says examples are never facts about this run, yet the S5 examples (Sales with quotes, orders, deliveries and invoices; the cds_ and cym_ HR copies) match this run's tables exactly, so they read as hints rather than illustrations.
- candidate run-02 comment: Most of the answer followed directly from the rules: copies together, shared currency table, technical tables unassigned. The CRM merge and the small Finance area are the two judgment calls I am least sure of. A sentence on areas of 5 to 9 tables and on whether a second System's sales-side tables join the sales area would remove them.
- baseline run-03 confusing [S5]: Split or merge is unclear when each process has only two own tables. Order Capture, Fulfilment and Invoicing are named as split points, but one- or two-table areas must be merged. I kept one 14-table Order to Cash area (86 columns) because small, tightly joined tables are allowed up to about 20.
- baseline run-03 confusing [S4]: Step 6 says to share a master table into every area that uses it, while step 4 and I3 want cross-System twins of one subject together. It is unclear whether a shared customer table (t1) in a second area must bring its CRM twin (t21) along; I kept the pair together in one area only.
- baseline run-03 confusing [S4]: Step 6 does not say whether a master's own code columns count as use of a reference table. Customer has currency_code and payment_terms_code but table_links has no edge from t1 to currency or payment terms, so I left them out of the customer area.
- baseline run-03 comment: The whole scope has only about 230 columns, so table count and process boundaries drove the sizing, not the column limits. The technical log t39 and the staging copy t40 went to unassigned under S4 step 8. A one-line rule on sharing a master together with its cross-System twin would remove my main doubt.
- baseline run-04 confusing [S4]: Step 4 (keep CRM and ERP customer accounts together) and step 6 (put a customer table in every area that uses it) do not say what follows when a shared master goes into a second area: must its other-System twin (t21) and its attribute table (t2) come too? I put t1 and t21 together in both areas and kept t2 and t22 only with their own process.
- baseline run-04 confusing [S5]: I3 repeats only the 'about 5 to 12 tables' band, while S5 also allows about 20 for small, tightly joined tables; the Order to Cash chain (16 tables, 99 columns) sits between, so I had to judge. 'A few hundred columns' never binds here because these tables have 3 to 9 columns, and the schema description's 'broad business domains' (not a numbered section) points to larger areas than S5 does.
- baseline run-04 confusing [S4]: Step 4 speaks of different source_systems, but the HR tables are one System (HR_SUITE) in two parallel member-firm table sets (cds_ and cym_). I kept them together as one subject, but nothing says same-System parallel table sets count the same way, and step 3's warning about name prefixes could be read either way.
- baseline run-04 confusing [I3]: The opening line promises the ordered design and area size guidance 'below', but only the final checks follow; those rules are in S4 and S5 of the system message.
- baseline run-04 comment: S2 is long for a grouping task; only its lake-code and gds_batch_id parts helped me read table_index and the HR columns. The rules were easy to follow once I found S5's 20-table allowance, but a reader who only sees I3 might split the Order to Cash chain and design the order tables in three areas. I left t40 (customer staging) unassigned under S4 step 8 even though its name points at customers.
- candidate run-05 confusing [S1]: S1 names Customers and Products as example broad domains, but S5.3 and S5.6 treat customers and products as subjects inside Sales that are shared with other areas. It is unclear whether a separate Customers area is ever wanted, for example for the ERP and CRM customer copies; I kept them inside Sales.
- candidate run-05 confusing [S6]: S6 calls 10 to 30 tables typical and says to merge areas under about 5 tables, but Finance has only 6 tables (5 of its own plus shared Currency). It does not say whether such an area should stay separate or merge into Sales; I kept it separate as a distinct domain.
- candidate run-05 confusing [S4]: The schema describes unassigned as tables that fit no area yet, while S4 and S5.8 allow only technical, staging, log, audit or control tables there. The two descriptions suggest different thresholds.
- candidate run-05 comment: I chose three broad areas (Sales including the CRM pipeline, Finance, Human Resources) because S6 says to split only above about 40 tables or 800 columns, and I shared only Currency (t14) between Sales and Finance because the table links support it. Most row counts are a uniform 10000, so they gave little signal. S5.4 names the cds_ and cym_ prefixes, which match this input exactly even though S2 and S3 say examples are not facts about the run.
- candidate run-06 confusing [S1]: Customers and Products are listed as example domains, but S5.3 and S5.6 treat customers and products as subjects or shared master tables inside Sales. There is no tie-breaker for whether the CRM tables plus the customer tables (about 8 tables, above the S6 merge threshold of 5) should be a separate Customers area or part of Sales. I folded them into Sales because of 'prefer a few broad areas' and 'never one area per System'.
- candidate run-06 confusing [S6]: A typical area is 10 to 30 tables, but only areas under about 5 tables are told to merge. A distinct 5 to 9 table area such as the general ledger (5 own tables, 6 with the shared currency) falls in an unspecified zone, and 'large, distinct domain' is not defined.
- candidate run-06 confusing [S5]: 'Look-alike groups' (S5.4, S6) are not defined in S2, which only describes instances of a System. I inferred from the cds_/cym_ example that they are same-shaped table sets inside one Connection.
- candidate run-06 comment: The examples in S5.4 (CRM and ERP customer accounts, the cds_ and cym_ HR copies) match this run's tables exactly, so this run cannot show whether the copy rules work beyond those examples. The only real judgment calls were folding CRM into Sales and keeping a small but distinct Finance area. Everything else followed directly from the rules.

## 2026-10-28 · `r2-enterprise_40` · fixture `enterprise_40` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 0/3 | 3/3 |
| Valid answers (schema) | 0/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | – | 3.0 |
| Clarity (1–5) | – | 4.0 |
| Confidence (1–5) | – | 4.0 |
| Blockers cited | – | – |
| Confusing cited | – | S6 ×3, S5 ×1, S2 ×1, S4 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-02 confusing [S6]: Nothing says how to tell whether a 5 to 9 table group is a distinct domain or only part of a larger one. CRM has 6 tables and could be argued either way; I merged it into Sales because item 4 of S5 names CRM and ERP customer accounts as copies to keep in one area.
- candidate run-02 comment: The rules led to one clear answer: Sales (with CRM), Finance, Human Resources, and the two technical tables unassigned. S2 items 3 and 5 (ids per instance, bronze loading) did not affect this task. The name Sales is a loose fit for an area that also holds campaigns and leads, and the prompt gives no naming hint for mixed-System areas.
- candidate run-03 confusing [S6]: There is no test for whether a 5 to 9 table area is a 'distinct domain' (keep) or 'only a part of a larger domain' (merge). The 6-table CRM set could be either, so merging it into Sales was a judgment call, backed by S5 step 3 (no area per System) and step 4 (CRM and ERP customer accounts together).
- candidate run-03 confusing [S5]: Minor: stg_customer_tmp is a staging copy of customers, so step 4 (keep copies together) could pull it into the customer area, while step 8 names staging tables as unassigned. I used step 8 because it is the more specific rule.
- candidate run-03 comment: The prompt covered every tricky part of this input explicitly: CRM and ERP customer copies, the CDS and CYM look-alike HR sets, and the technical tables. The data shows the batch column as gds_batch_id while S2 writes GDSBatchID, which is harmless here. Finance only reaches 6 tables by counting the shared currency table, which S6 allows.
- candidate run-05 confusing [S6]: No test for when a 5 to 9 table group, such as the 6 CRM tables, is a distinct domain rather than part of a larger one. With S5 step 4 (never one area per System) and the 2 to 4 area range for 40 tables, both 3 areas (CRM inside Sales) and 4 areas (CRM separate) look valid.
- candidate run-05 confusing [S2]: Point 5 names the batch column GDSBatchID, but the evidence columns are written gds_batch_id. It is easy to guess they are the same, but this is not stated.
- candidate run-05 confusing [S4]: The output schema describes unassigned as tables that fit no area yet, which reads softer than S5 step 8 (only technical, staging, log, audit or control tables).
- candidate run-05 comment: Copies together (CDS with CYM, CRM account with ERP customer), the shared currency table, the two technical tables left unassigned and the empty retire list followed directly from S5 and I1. Putting CRM inside Sales is the one judgement call, supported by S1's preference for few broad areas and the t21 to t1 link.

## 2026-10-28 · `r3-enterprise_40` · fixture `enterprise_40` · 6 runs

| Measure | baseline | candidate |
|---|---|---|
| Results returned | 0/3 | 3/3 |
| Valid answers (schema) | 0/3 | 3/3 |
| Expected items found | 0/0 (–) | 0/0 (–) |
| Forbidden items returned | 0 | 0 |
| Other items per valid answer | – | 3.0 |
| Clarity (1–5) | – | 4.0 |
| Confidence (1–5) | – | 4.0 |
| Blockers cited | – | – |
| Confusing cited | – | S6 ×3, S5 ×1, S4 ×1 |

Suggested verdict: **not enough valid answers to compare**

Review notes:
- candidate run-01 confusing [S6]: The merge test (merge when most of an area's links point into the larger area, 'such as CRM opportunities that point at the customers of Sales') does not match this data literally: only 1 of 6 CRM links (account to ERP customer) leaves CRM, so the test alone would keep CRM separate. I merged CRM into Sales because S5 step 4 puts CRM and ERP customer accounts in one area and S6 expects about 2 to 4 areas for 40 tables.
- candidate run-01 comment: Everything else mapped cleanly: ERP order-to-cash plus CRM became Sales, the general ledger stayed a distinct 6-table Finance area sharing currency with Sales, both HR member-firm sets went into one area, and the log and staging tables went to unassigned. The S6 merge test could say how to count a link from a copy (CRM account) to its twin (ERP customer). The evidence column gds_batch_id is spelled differently from GDSBatchID in S2 but did not affect the grouping.
- candidate run-03 confusing [S6]: The merge test for a 5 to 9 table area is 'most of its links point into that area's tables', but only 1 of CRM's 6 links goes to Sales (t21 to t1), so read literally CRM stays separate; the CRM example in the same bullet suggests the opposite.
- candidate run-03 confusing [S5]: Step 4 says CRM and ERP customer accounts belong in one area and step 3 forbids one area per System, schema or prefix, which favors merging CRM into Sales; it is unclear whether those override the S6 link test, or whether t1 and t21 should instead be listed in both a Sales and a CRM area.
- candidate run-03 comment: The technical tables, the CDS/CYM look-alike groups and the shared currency table were clear from S5 steps 4, 6 and 8. The one real judgement call was CRM: I merged it into Sales (21 tables) because its account is a copy of the ERP customer and S1 prefers a few broad areas, and a separate CRM area is the other defensible reading. One sentence saying which of S5 step 4 and the S6 link test wins would remove that doubt.
- candidate run-06 confusing [S6]: The test 'merge when most of its links point into that area's tables' is hard to apply to CRM here: only one link (t21 to t1) leaves the six CRM tables, yet S5 step 4 says CRM and ERP customer accounts must share an area. It was unclear whether CRM should be its own 5 to 9 table area (with t1 shared) or part of Sales; I merged it, guided by the CRM-opportunities example and the 'prefer a few broad areas' line in S1.
- candidate run-06 confusing [S4]: The example JSON uses ids t1, t2, t5 and t9, with t9 unassigned, and these ids are real tables in this run (t9 is an invoice). S2 and S3 say examples are not facts about the run, so I ignored it, but the clash could mislead a less careful reader.
- candidate run-06 comment: The steps are easy to follow, and this 40-table run maps cleanly onto Sales, Finance and Human Resources with the two technical tables left unassigned. The only real judgment call was CRM, which I put in Sales because the CRM account is a copy of the ERP customer and the contacts, opportunities and activities hang off it. A one-line worked example of counting links that point into an area would make that call less of a guess.

