-- Default SQL Generation Guide. Models may already exist.
-- Replace the three placeholders with one existing active Super Admin identity.
-- Exact replay is a no-op. Conflicts are never overwritten.
-- Adds guide configuration only; existing Models, Mapping and Runs are unchanged.

DO $global_sql_generation_guide_seed$
DECLARE
    v_entra_tenant_text TEXT := '__REPLACE_WITH_ENTRA_TENANT_ID__';
    v_entra_object_text TEXT := '__REPLACE_WITH_ENTRA_OBJECT_ID__';
    v_principal_type TEXT := '__REPLACE_WITH_PRINCIPAL_TYPE__';
    v_guide application.sql_generation_guide%ROWTYPE;
    v_version application.sql_generation_guide_version%ROWTYPE;
    v_code CONSTANT VARCHAR := 'atlas.databricks.transformation';
    v_name CONSTANT VARCHAR := 'Atlas Databricks transformation SQL';
    v_description CONSTANT VARCHAR := 'Default Databricks query conventions for complete applied Mapping.';
    v_content CONSTANT TEXT := $guide$
Translate complete applied Object and Attribute Mapping into Databricks SQL.
Preserve Mapping grain, joins, predicates, source roles, casts, null handling,
System reconciliation and dependency order. Never invent missing business rules.

Use exact input identities and Attribute names from the frozen source context.
Generated transformation SQL uses resolved schema.object references, with the
catalog supplied by runtime. Quote each identifier with Databricks backticks when
required. Preserve source placement and modeled Logical/Dimensional lookup names;
never substitute target placement or guess coordinates. Full catalog.schema.object
coordinates remain part of evidence context and governed evidence/Validation
queries. The framework resolves output schema/table, catalog, registration and
loading; do not write to the target.

Build meaningful preparation, join/filter and projection stages with uniquely
named, unqualified CREATE OR REPLACE TEMPORARY VIEW statements. Declare each
temporary dependency earlier in the same artifact; later stages reuse prior
results. A simple Mapping can use one view and a final SELECT. Do not repeat the
whole pipeline in every stage or depend on another artifact's temporary state.

Finish with one explicit SELECT of the mapped output columns in modeled order.
Apply confirmed generated-surrogate, framework-audit and Type 2 population rules:
omit framework-populated columns from the transformation output; preserve mapped
natural keys, foreign keys, optional Source audit fields and SourceSystemID.
Do not add SELECT *, defaults, deduplication, TRY_CAST or history maintenance
unless approved Mapping specifically requires the relevant transformation.

Honor the selected combined or per-System file layout. Assign each selected
contributing System exactly once; combine branches only according to Mapping's
evidenced collision/reconciliation policy. Preserve confirmed runtime parameters
without substituting test values, profiling batch filters or an invented latest batch.

Return SQL-only artifacts with no Markdown, prose, placeholders for missing logic
or explanatory comments. Temporary-view preparation and the final read query are
allowed; persistent DDL, INSERT, MERGE, UPDATE, DELETE, orchestration and deployment
are not transformation output. Generation and static validation do not execute SQL
or establish business correctness. Report missing or conflicting Mapping evidence.
$guide$;
    v_digest CHAR(64);
BEGIN
    IF v_entra_tenant_text LIKE '%__REPLACE_%'
       OR v_entra_object_text LIKE '%__REPLACE_%'
       OR v_principal_type LIKE '%__REPLACE_%' THEN
        RAISE EXCEPTION 'replace every SQL generation guide seed identity placeholder';
    END IF;
    IF v_principal_type NOT IN ('user', 'service_principal')
       OR v_entra_tenant_text::UUID = '00000000-0000-0000-0000-000000000000'::UUID
       OR v_entra_object_text::UUID = '00000000-0000-0000-0000-000000000000'::UUID THEN
        RAISE EXCEPTION 'SQL generation guide seed requires a valid nonzero Entra identity';
    END IF;
    PERFORM 1
      FROM security.entra_principal_identity AS identity
      JOIN security.principal AS principal USING (principal_id, principal_type)
     WHERE identity.entra_tenant_id = v_entra_tenant_text::UUID
       AND identity.entra_object_id = v_entra_object_text::UUID
       AND identity.principal_type = v_principal_type
       AND identity.is_active AND principal.is_active AND principal.is_super_admin
     FOR SHARE OF identity, principal;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'SQL generation guide requires Super Admin';
    END IF;

    -- Serialize installation against governed default changes.
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('application.sql_generation_guide.default', 0)
    );
    IF EXISTS (
        SELECT 1 FROM application.sql_generation_guide
         WHERE is_default AND lower(sql_generation_guide_code) <> v_code
    ) THEN
        RAISE EXCEPTION 'SQL generation guide seed will not replace an existing default';
    END IF;
    v_digest := encode(sha256(convert_to(v_content, 'UTF8')), 'hex');
    SELECT * INTO v_guide
      FROM application.sql_generation_guide
     WHERE lower(sql_generation_guide_code) = v_code
     FOR UPDATE;
    IF FOUND THEN
        IF v_guide.sql_generation_guide_name <> v_name
           OR v_guide.sql_generation_guide_description IS DISTINCT FROM v_description
           OR NOT v_guide.is_active OR NOT v_guide.is_default
           OR (SELECT count(*) FROM application.sql_generation_guide_version
                WHERE sql_generation_guide_id = v_guide.sql_generation_guide_id) <> 1
           OR NOT EXISTS (
               SELECT 1 FROM application.sql_generation_guide_version
                WHERE sql_generation_guide_id = v_guide.sql_generation_guide_id
                  AND sql_generation_guide_version_number = 1
                  AND sql_generation_guide_version_status = 'published'
                  AND sql_generation_guide_digest = v_digest
                  AND sql_generation_guide_content = v_content
           ) THEN
            RAISE EXCEPTION 'SQL generation guide seed conflicts with existing guide history';
        END IF;
        RETURN;
    END IF;

    SELECT * INTO STRICT v_guide FROM application.save_sql_generation_guide(
        v_entra_tenant_text::UUID, v_entra_object_text::UUID, v_principal_type::VARCHAR,
        NULL::BIGINT, v_code, v_name, v_description, TRUE, TRUE, NULL::TIMESTAMPTZ
    );
    SELECT * INTO STRICT v_version FROM application.save_sql_generation_guide_draft(
        v_entra_tenant_text::UUID, v_entra_object_text::UUID, v_principal_type::VARCHAR,
        v_guide.sql_generation_guide_id, NULL::BIGINT, v_content, NULL::TIMESTAMPTZ
    );
    PERFORM application.transition_sql_generation_guide_version(
        v_entra_tenant_text::UUID, v_entra_object_text::UUID, v_principal_type::VARCHAR,
        v_version.sql_generation_guide_version_id, 'draft'::VARCHAR, 'published'::VARCHAR
    );
END;
$global_sql_generation_guide_seed$;
