#!/bin/sh

set -eu

fail() {
    printf '%s\n' 'ok=false' >&2
    printf 'error=%s\n' "$1" >&2
    exit 2
}

[ "$#" -eq 2 ] || [ "$#" -eq 3 ] || fail 'Usage: validate-metadata-snapshot.sh <snapshot-path> <expected-tenant-code> [expected-snapshot-id].'

snapshot_input=$1
expected_tenant_code=$2
expected_snapshot_id=${3:-}

[ -n "$expected_tenant_code" ] || fail 'Expected Tenant code is required.'
command -v plutil >/dev/null 2>&1 || fail 'macOS plutil is required.'
command -v shasum >/dev/null 2>&1 || fail 'macOS shasum is required.'

case "$snapshot_input" in
    /*) snapshot_candidate=$snapshot_input ;;
    *) snapshot_candidate=$PWD/$snapshot_input ;;
esac

[ "$(basename "$snapshot_candidate")" = 'metadata-snapshot' ] || fail 'Snapshot directory must be named metadata-snapshot.'
[ -d "$snapshot_candidate" ] || fail 'Snapshot directory does not exist.'
[ ! -L "$snapshot_candidate" ] || fail 'Snapshot directory cannot be a symbolic link.'

snapshot_parent=$(cd "$(dirname "$snapshot_candidate")" && pwd -P)
snapshot=$snapshot_parent/metadata-snapshot
manifest=$snapshot/manifest.json
catalog=$snapshot/catalog.json

[ -f "$manifest" ] && [ ! -L "$manifest" ] || fail 'manifest.json is missing or unsafe.'
[ -f "$catalog" ] && [ ! -L "$catalog" ] || fail 'catalog.json is missing or unsafe.'
[ -d "$snapshot/schemas" ] && [ ! -L "$snapshot/schemas" ] || fail 'schemas directory is missing or unsafe.'
[ -d "$snapshot/data" ] && [ ! -L "$snapshot/data" ] || fail 'data directory is missing or unsafe.'
[ -z "$(find "$snapshot" -type l -print -quit)" ] || fail 'Snapshot cannot contain symbolic links.'
plutil -convert json -o /dev/null "$manifest" >/dev/null 2>&1 || fail 'manifest.json is not valid JSON.'
plutil -convert json -o /dev/null "$catalog" >/dev/null 2>&1 || fail 'catalog.json is not valid JSON.'

json_raw() {
    plutil -extract "$1" raw "$2" 2>/dev/null || fail "Required JSON value is missing: $1."
}

schema_version=$(json_raw schema_version "$manifest")
snapshot_kind=$(json_raw snapshot_kind "$manifest")
snapshot_id=$(json_raw snapshot_id "$manifest")
tenant_code=$(json_raw tenant_code "$manifest")
database_ids_included=$(json_raw database_ids_included "$manifest")
logical_dataset_count=$(json_raw counts.logical_dataset_count "$manifest")
file_count=$(json_raw counts.file_count "$manifest")
declared_expanded_bytes=$(json_raw counts.expanded_bytes "$manifest")
row_count=$(json_raw counts.row_count "$manifest")
schema_count=$(json_raw schemas.dataset_count "$manifest")
foundational_count=$(json_raw sections.foundational.dataset_count "$manifest")
reference_count=$(json_raw sections.reference.dataset_count "$manifest")
operational_count=$(json_raw sections.operational.dataset_count "$manifest")
catalog_path=$(json_raw catalog.path "$manifest")
catalog_hash=$(json_raw catalog.sha256 "$manifest")
member_count=$(json_raw members "$manifest")

[ "$schema_version" = '2.0' ] || fail 'Unsupported Snapshot schema version.'
[ "$snapshot_kind" = 'metadata' ] || fail 'Snapshot kind is not metadata.'
[ "$database_ids_included" = 'false' ] || fail 'Snapshot must be ID-free.'
if [ -n "$expected_snapshot_id" ]; then
    [ "$snapshot_id" = "$expected_snapshot_id" ] || fail 'Snapshot ID does not match the MCP result.'
fi
[ "$tenant_code" = "$expected_tenant_code" ] || fail 'Snapshot Tenant does not match the selected Tenant.'
[ "$logical_dataset_count" = '29' ] || fail 'Snapshot must contain 29 logical datasets.'
[ "$schema_count" = '29' ] || fail 'Snapshot must contain 29 dataset schemas.'
[ "$foundational_count" = '5' ] || fail 'Foundational dataset count is invalid.'
[ "$reference_count" = '8' ] || fail 'Reference dataset count is invalid.'
[ "$operational_count" = '16' ] || fail 'Operational dataset count is invalid.'
[ "$catalog_path" = 'catalog.json' ] || fail 'Manifest catalog path is invalid.'

case "$member_count:$file_count:$declared_expanded_bytes:$row_count" in
    *[!0-9:]*|:*|*::*|*:) fail 'Manifest counts must be non-negative integers.' ;;
esac
[ "$file_count" -eq $((member_count + 1)) ] || fail 'Manifest file count is inconsistent.'

seen_paths=''
actual_expanded_bytes=$(stat -f '%z' "$manifest" 2>/dev/null) || fail 'Cannot read manifest size.'
index=0
while [ "$index" -lt "$member_count" ]; do
    member_path=$(json_raw "members.$index.path" "$manifest")
    member_hash=$(json_raw "members.$index.sha256" "$manifest")
    member_size=$(json_raw "members.$index.size_bytes" "$manifest")

    case "$member_path" in
        ''|/*|*\\*|*//*|.|..|./*|../*|*/.|*/..|*/./*|*/../*|*[!A-Za-z0-9._/-]*) fail 'Manifest contains an unsafe member path.' ;;
    esac
    normalized_path=$(printf '%s' "$member_path" | tr '[:upper:]' '[:lower:]')
    case "$seen_paths" in
        *"|$normalized_path|"*) fail 'Manifest contains a duplicate member path.' ;;
    esac
    seen_paths=$seen_paths'|'$normalized_path'|'

    member=$snapshot/$member_path
    [ -f "$member" ] && [ ! -L "$member" ] || fail "Snapshot member is missing or unsafe: $member_path."
    case "$member_size" in
        ''|*[!0-9]*) fail "Snapshot member size is invalid: $member_path." ;;
    esac
    actual_size=$(stat -f '%z' "$member" 2>/dev/null) || fail "Cannot read Snapshot member size: $member_path."
    [ "$actual_size" = "$member_size" ] || fail "Snapshot member size mismatch: $member_path."
    actual_hash=$(shasum -a 256 "$member" | awk '{print $1}')
    [ "$actual_hash" = "$member_hash" ] || fail "Snapshot member hash mismatch: $member_path."
    actual_expanded_bytes=$((actual_expanded_bytes + actual_size))
    index=$((index + 1))
done

actual_file_count=$(find "$snapshot" -type f | wc -l | tr -d '[:space:]')
[ "$actual_file_count" = "$file_count" ] || fail 'Snapshot contains missing or unexpected files.'
[ "$actual_expanded_bytes" = "$declared_expanded_bytes" ] || fail 'Snapshot expanded-byte count is inconsistent.'
actual_catalog_hash=$(shasum -a 256 "$catalog" | awk '{print $1}')
[ "$actual_catalog_hash" = "$catalog_hash" ] || fail 'Catalog hash does not match the manifest.'

catalog_schema_version=$(json_raw schema_version "$catalog")
catalog_snapshot_kind=$(json_raw snapshot_kind "$catalog")
catalog_database_ids=$(json_raw database_ids_included "$catalog")
[ "$catalog_schema_version" = '2.0' ] || fail 'Catalog schema version is invalid.'
[ "$catalog_snapshot_kind" = 'metadata' ] || fail 'Catalog kind is invalid.'
[ "$catalog_database_ids" = 'false' ] || fail 'Catalog must describe ID-free rows.'

printf '%s\n' 'ok=true'
printf 'snapshot=%s\n' "$snapshot"
printf 'snapshot_id=%s\n' "$snapshot_id"
printf 'tenant_code=%s\n' "$tenant_code"
printf 'member_count=%s\n' "$member_count"
printf 'logical_dataset_count=%s\n' "$logical_dataset_count"
printf 'row_count=%s\n' "$row_count"
printf 'expanded_bytes=%s\n' "$actual_expanded_bytes"
