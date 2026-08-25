#!/bin/sh

set -eu

fail() {
    printf '%s\n' 'ok=false' >&2
    printf 'error=%s\n' "$1" >&2
    exit 2
}

[ "$#" -eq 1 ] || [ "$#" -eq 2 ] || fail 'Usage: inspect-metadata-catalog.sh <snapshot-path> [dataset].'

snapshot_input=$1
requested_dataset=${2:-}
case "$requested_dataset" in
    ''|*[!a-z0-9_]*) [ -z "$requested_dataset" ] || fail 'Dataset name is invalid.' ;;
esac
command -v plutil >/dev/null 2>&1 || fail 'macOS plutil is required.'

case "$snapshot_input" in
    /*) snapshot_candidate=$snapshot_input ;;
    *) snapshot_candidate=$PWD/$snapshot_input ;;
esac
[ "$(basename "$snapshot_candidate")" = 'metadata-snapshot' ] || fail 'Snapshot directory must be named metadata-snapshot.'
[ -d "$snapshot_candidate" ] && [ ! -L "$snapshot_candidate" ] || fail 'Snapshot directory is missing or unsafe.'
snapshot_parent=$(cd "$(dirname "$snapshot_candidate")" && pwd -P)
snapshot=$snapshot_parent/metadata-snapshot
catalog=$snapshot/catalog.json
[ -f "$catalog" ] && [ ! -L "$catalog" ] || fail 'catalog.json is missing or unsafe.'
plutil -convert json -o /dev/null "$catalog" >/dev/null 2>&1 || fail 'catalog.json is not valid JSON.'

json_raw() {
    plutil -extract "$1" raw "$catalog" 2>/dev/null || fail "Required catalog value is missing: $1."
}

[ "$(json_raw schema_version)" = '2.0' ] || fail 'Unsupported catalog schema version.'
[ "$(json_raw snapshot_kind)" = 'metadata' ] || fail 'Catalog kind is not metadata.'
[ "$(json_raw database_ids_included)" = 'false' ] || fail 'Catalog must describe ID-free rows.'

section_count=$(json_raw sections)
case "$section_count" in ''|*[!0-9]*) fail 'Catalog section count is invalid.' ;; esac
dataset_total=0
found=false
section_index=0
while [ "$section_index" -lt "$section_count" ]; do
    section_name=$(json_raw "sections.$section_index.name")
    dataset_count=$(json_raw "sections.$section_index.datasets")
    case "$dataset_count" in ''|*[!0-9]*) fail 'Catalog dataset count is invalid.' ;; esac
    dataset_total=$((dataset_total + dataset_count))
    dataset_index=0
    while [ "$dataset_index" -lt "$dataset_count" ]; do
        prefix=sections.$section_index.datasets.$dataset_index
        dataset_name=$(json_raw "$prefix.name")
        if [ -z "$requested_dataset" ]; then
            row_count=$(json_raw "$prefix.row_count")
            search_complete=$(json_raw "$prefix.search_result_complete")
            printf 'dataset=%s|%s|%s|%s\n' "$section_name" "$dataset_name" "$row_count" "$search_complete"
        elif [ "$dataset_name" = "$requested_dataset" ]; then
            [ "$found" = false ] || fail 'Catalog contains a duplicate dataset name.'
            found=true
            printf '%s\n' 'ok=true'
            printf 'section=%s\n' "$section_name"
            printf 'dataset=%s\n' "$dataset_name"
            printf 'label=%s\n' "$(json_raw "$prefix.label")"
            printf 'record_type=%s\n' "$(json_raw "$prefix.record_type")"
            printf 'row_count=%s\n' "$(json_raw "$prefix.row_count")"
            printf 'search_result_complete=%s\n' "$(json_raw "$prefix.search_result_complete")"
            printf 'schema_file=%s\n' "$(json_raw "$prefix.schema_file")"
            printf 'search_file=%s\n' "$(json_raw "$prefix.search_file")"
            printf 'rows_file=%s\n' "$(json_raw "$prefix.rows_file")"

            canonical_count=$(json_raw "$prefix.canonical_key")
            canonical_key=''
            key_index=0
            while [ "$key_index" -lt "$canonical_count" ]; do
                field=$(json_raw "$prefix.canonical_key.$key_index")
                [ -z "$canonical_key" ] || canonical_key=$canonical_key','
                canonical_key=$canonical_key$field
                key_index=$((key_index + 1))
            done
            printf 'canonical_key=%s\n' "$canonical_key"

            search_count=$(json_raw "$prefix.search_fields")
            search_fields=''
            field_index=0
            while [ "$field_index" -lt "$search_count" ]; do
                field=$(json_raw "$prefix.search_fields.$field_index")
                [ -z "$search_fields" ] || search_fields=$search_fields','
                search_fields=$search_fields$field
                field_index=$((field_index + 1))
            done
            printf 'search_fields=%s\n' "$search_fields"
        fi
        dataset_index=$((dataset_index + 1))
    done
    section_index=$((section_index + 1))
done

[ "$dataset_total" -eq 29 ] || fail 'Catalog must contain 29 datasets.'
if [ -z "$requested_dataset" ]; then
    printf '%s\n' 'ok=true'
    printf 'dataset_count=%s\n' "$dataset_total"
elif [ "$found" = false ]; then
    fail 'Dataset is not present in catalog.json.'
fi
