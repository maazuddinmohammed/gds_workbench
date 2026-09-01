#!/usr/bin/env bash
set -Eeuo pipefail

database_root=/opt/gds/database

for required_name in \
    POSTGRES_DB \
    POSTGRES_USER \
    GDS_LOCAL_POSTGRES_ADMIN_PASSWORD \
    GDS_LOCAL_WEB_PASSWORD \
    GDS_LOCAL_MCP_PASSWORD \
    GDS_LOCAL_RUN_SENTINEL \
    GDS_LOCAL_ENTRA_TENANT_ID \
    GDS_LOCAL_PRINCIPAL_OBJECT_ID
do
    if [[ -z "${!required_name:-}" ]]; then
        echo "local database initialization refused: missing ${required_name}" >&2
        exit 1
    fi
done

if [[ ! "$GDS_LOCAL_RUN_SENTINEL" =~ ^[0-9a-f]{12}$ ]] \
    || [[ "$POSTGRES_DB" != "gds_local_${GDS_LOCAL_RUN_SENTINEL}" ]] \
    || [[ "$POSTGRES_USER" != "gds_admin_${GDS_LOCAL_RUN_SENTINEL}" ]]; then
    echo "local database initialization refused: invalid run sentinel" >&2
    exit 1
fi

for password_name in \
    GDS_LOCAL_POSTGRES_ADMIN_PASSWORD \
    GDS_LOCAL_WEB_PASSWORD \
    GDS_LOCAL_MCP_PASSWORD
do
    if [[ ! "${!password_name}" =~ ^[0-9a-f]{96}$ ]]; then
        echo "local database initialization refused: invalid generated credential" >&2
        exit 1
    fi
done

if [[ "$GDS_LOCAL_POSTGRES_ADMIN_PASSWORD" == "$GDS_LOCAL_WEB_PASSWORD" ]] \
    || [[ "$GDS_LOCAL_POSTGRES_ADMIN_PASSWORD" == "$GDS_LOCAL_MCP_PASSWORD" ]] \
    || [[ "$GDS_LOCAL_WEB_PASSWORD" == "$GDS_LOCAL_MCP_PASSWORD" ]]; then
    echo "local database initialization refused: credentials must be distinct" >&2
    exit 1
fi

uuid_pattern='^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
if [[ ! "$GDS_LOCAL_ENTRA_TENANT_ID" =~ $uuid_pattern ]] \
    || [[ ! "$GDS_LOCAL_PRINCIPAL_OBJECT_ID" =~ $uuid_pattern ]]; then
    echo "local database initialization refused: invalid local identity" >&2
    exit 1
fi

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -X -v ON_ERROR_STOP=1 -f "$database_root/00_preflight.sql"

release_files=(
    01_reference.sql
    02_core.sql
    03_security.sql
    04_model.sql
    05_workflow_analysis.sql
    06_workflow_conceptual.sql
    07_workflow_logical.sql
    08_workflow_dimensional.sql
    09_workflow_mapping.sql
    10_workflow_code_qa.sql
    11_workflow_eligibility.sql
    12_application_configuration.sql
    13_application_workflow_runs.sql
    14_application_workflow_execution.sql
    15_mcp_change_sets.sql
    16_mcp_metadata_apply.sql
    17_mcp_tool_call_log.sql
    18_runtime_account.sql
    19_runtime_integrity.sql
)

for release_file in "${release_files[@]}"
do
    psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
        -X -v ON_ERROR_STOP=1 --single-transaction \
        -f "$database_root/$release_file"
done

PGOPTIONS="-c gds.local_web_password=${GDS_LOCAL_WEB_PASSWORD} -c gds.local_mcp_password=${GDS_LOCAL_MCP_PASSWORD}" \
    psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
        -X -v ON_ERROR_STOP=1 <<'SQL'
DO $runtime_passwords$
BEGIN
    EXECUTE format(
        'ALTER ROLE %I PASSWORD %L',
        'gds_web_runtime',
        current_setting('gds.local_web_password')
    );
    EXECUTE format(
        'ALTER ROLE %I PASSWORD %L',
        'gds_mcp_runtime',
        current_setting('gds.local_mcp_password')
    );
END;
$runtime_passwords$;
SQL

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -X -v ON_ERROR_STOP=1 -f "$database_root/20_verify_install.sql"

for seed_file in \
    01_metadata_snapshot_demo.sql \
    04_application_reference.sql
do
    psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
        -X -v ON_ERROR_STOP=1 --single-transaction \
        -f "$database_root/seed/$seed_file"
done

local_identity_seed="$(mktemp /tmp/gds-local-identity.XXXXXX.sql)"
local_prompt_seed="$(mktemp /tmp/gds-local-prompts.XXXXXX.sql)"
chmod 600 "$local_identity_seed"
chmod 600 "$local_prompt_seed"
trap 'rm -f "$local_identity_seed" "$local_prompt_seed"' EXIT
sed \
    -e "s/__REPLACE_WITH_EXPECTED_DATABASE_NAME__/${POSTGRES_DB}/g" \
    -e "s/__REPLACE_WITH_ENTRA_TENANT_ID__/${GDS_LOCAL_ENTRA_TENANT_ID}/g" \
    -e "s/__REPLACE_WITH_LOCAL_PRINCIPAL_OBJECT_ID__/${GDS_LOCAL_PRINCIPAL_OBJECT_ID}/g" \
    "$database_root/seed/03_local_super_admin.template.sql" \
    > "$local_identity_seed"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -X -v ON_ERROR_STOP=1 --single-transaction -f "$local_identity_seed"

sed \
    -e "s/__REPLACE_WITH_ENTRA_TENANT_ID__/${GDS_LOCAL_ENTRA_TENANT_ID}/g" \
    -e "s/__REPLACE_WITH_ENTRA_OBJECT_ID__/${GDS_LOCAL_PRINCIPAL_OBJECT_ID}/g" \
    -e "s/__REPLACE_WITH_PRINCIPAL_TYPE__/user/g" \
    "$database_root/seed/05_global_prompt_defaults.template.sql" \
    > "$local_prompt_seed"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -X -v ON_ERROR_STOP=1 --single-transaction -f "$local_prompt_seed"
