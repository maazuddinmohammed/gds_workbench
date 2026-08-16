#!/bin/sh

set -eu
umask 077

fail() {
    printf '%s\n' 'ok=false' >&2
    printf 'error=%s\n' "$1" >&2
    exit 2
}

change_set_input=''
dataset_name=''
record_input=''
key_input=''
changes_input=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --change-set|--dataset|--record-file|--key-file|--changes-file)
            [ "$#" -ge 2 ] || fail "Missing value for $1."
            option=$1
            value=$2
            shift 2
            case "$option" in
                --change-set) change_set_input=$value ;;
                --dataset) dataset_name=$value ;;
                --record-file) record_input=$value ;;
                --key-file) key_input=$value ;;
                --changes-file) changes_input=$value ;;
            esac
            ;;
        *) fail "Unknown option: $1." ;;
    esac
done

[ -n "$change_set_input" ] || fail 'Local Change Set path is required.'
if [ -n "$record_input" ]; then
    [ -z "$key_input" ] && [ -z "$changes_input" ] || fail 'Choose full-record or field-edit mode, not both.'
    edit_mode=false
else
    [ -n "$key_input" ] && [ -n "$changes_input" ] || fail 'Field-edit mode requires key and changes JSON files.'
    edit_mode=true
fi
case "$dataset_name" in
    source_object|source_attribute|bronze_object|bronze_attribute|silver_object|silver_attribute|gold_object|gold_attribute|ingestion_object_mapping|ingestion_attribute_mapping|copy_group|member_group|copy_group_control|copy|process_group|process) ;;
    *) fail 'Dataset is not Change Set eligible.' ;;
esac
command -v plutil >/dev/null 2>&1 || fail 'macOS plutil is required.'
command -v osascript >/dev/null 2>&1 || fail 'macOS osascript is required.'
command -v shasum >/dev/null 2>&1 || fail 'macOS shasum is required.'
script_directory=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
dataset_helper=$script_directory/validate-metadata-dataset.js
[ -f "$dataset_helper" ] || fail 'Bundled dataset helper is missing.'

case "$change_set_input" in
    /*) change_set_candidate=$change_set_input ;;
    *) change_set_candidate=$PWD/$change_set_input ;;
esac
[ "$(basename "$change_set_candidate")" = 'change-set' ] || fail 'Local directory must be named change-set.'
[ -d "$change_set_candidate" ] && [ ! -L "$change_set_candidate" ] || fail 'Local change-set is missing or unsafe.'
workspace=$(cd "$(dirname "$change_set_candidate")" && pwd -P)
[ "$(basename "$workspace")" = 'GDS' ] || fail 'Local change-set must be directly under GDS.'
change_set=$workspace/change-set
state=$change_set/change-set.json
datasets=$change_set/datasets
[ -f "$state" ] && [ ! -L "$state" ] || fail 'change-set.json is missing or unsafe.'
[ -d "$datasets" ] && [ ! -L "$datasets" ] || fail 'datasets directory is missing or unsafe.'
[ -z "$(find "$change_set" -type l -print -quit)" ] || fail 'Local change-set cannot contain symbolic links.'
plutil -convert json -o /dev/null "$state" >/dev/null 2>&1 || fail 'change-set.json is not valid JSON.'
snapshot_path=$(plutil -extract snapshot.path raw "$state" 2>/dev/null) || fail 'Snapshot path is missing from local state.'
[ "$snapshot_path" = '../metadata-snapshot' ] || fail 'Snapshot path must be ../metadata-snapshot.'
tenant_code=$(plutil -extract tenant.tenant_code raw "$state" 2>/dev/null) || fail 'Tenant is missing from local state.'
snapshot_id=$(plutil -extract snapshot.snapshot_id raw "$state" 2>/dev/null) || fail 'Snapshot ID is missing from local state.'

snapshot=$workspace/metadata-snapshot
manifest=$snapshot/manifest.json
schema=$snapshot/schemas/$dataset_name.schema.json
[ -f "$manifest" ] && [ ! -L "$manifest" ] || fail 'Referenced metadata-snapshot is missing or unsafe.'
[ -f "$schema" ] && [ ! -L "$schema" ] || fail 'Snapshot dataset schema is missing or unsafe.'
manifest_tenant=$(plutil -extract tenant_code raw "$manifest" 2>/dev/null) || fail 'Snapshot Tenant cannot be read.'
manifest_snapshot=$(plutil -extract snapshot_id raw "$manifest" 2>/dev/null) || fail 'Snapshot ID cannot be read.'
[ "$manifest_tenant" = "$tenant_code" ] || fail 'Snapshot Tenant does not match local Change Set.'
[ "$manifest_snapshot" = "$snapshot_id" ] || fail 'Snapshot ID does not match local Change Set.'

dataset_file=$datasets/$dataset_name.json
if [ -e "$dataset_file" ] || [ -L "$dataset_file" ]; then
    [ -f "$dataset_file" ] && [ ! -L "$dataset_file" ] || fail 'Existing dataset file is unsafe.'
fi
if [ "$edit_mode" = true ]; then
    case "$key_input" in /*) key_file=$key_input ;; *) key_file=$PWD/$key_input ;; esac
    case "$changes_input" in /*) changes_file=$changes_input ;; *) changes_file=$PWD/$changes_input ;; esac
    [ -f "$key_file" ] && [ ! -L "$key_file" ] || fail 'Canonical key must be a regular, non-symbolic-link JSON file.'
    [ -f "$changes_file" ] && [ ! -L "$changes_file" ] || fail 'Field changes must be a regular, non-symbolic-link JSON file.'
    key_size=$(stat -f '%z' "$key_file" 2>/dev/null) || fail 'Canonical key size cannot be read.'
    changes_size=$(stat -f '%z' "$changes_file" 2>/dev/null) || fail 'Field changes size cannot be read.'
    [ "$key_size" -le 16777216 ] || fail 'Canonical key exceeds the 16 MiB limit.'
    [ "$changes_size" -le 16777216 ] || fail 'Field changes exceed the 16 MiB limit.'
    snapshot_rows=$snapshot/data/operational/$dataset_name/rows.jsonl
    [ -f "$snapshot_rows" ] && [ ! -L "$snapshot_rows" ] || fail 'Snapshot dataset rows are missing or unsafe.'
    merge_output=$(osascript -l JavaScript "$dataset_helper" "$schema" "$dataset_file" "$dataset_name" "$key_file" "$changes_file" "$snapshot_rows" "$dataset_file" edit 2>/dev/null) || fail "Field edit does not match the Snapshot schema, key, or uniqueness rules: $dataset_name."
else
    case "$record_input" in /*) record_file=$record_input ;; *) record_file=$PWD/$record_input ;; esac
    [ -f "$record_file" ] && [ ! -L "$record_file" ] || fail 'Input record must be a regular, non-symbolic-link JSON file.'
    record_size=$(stat -f '%z' "$record_file" 2>/dev/null) || fail 'Input record size cannot be read.'
    [ "$record_size" -le 16777216 ] || fail 'Input record exceeds the 16 MiB Stage limit.'
    merge_output=$(osascript -l JavaScript "$dataset_helper" "$schema" "$dataset_file" "$dataset_name" "$record_file" "$dataset_file" 2>/dev/null) || fail "Record or accumulated dataset does not match the Snapshot schema or uniqueness rules: $dataset_name."
fi
case "$merge_output" in
    mode=full-record*|mode=field-edit*) ;;
    *) fail 'Dataset helper output is invalid.' ;;
esac
if [ -f "$dataset_file" ]; then
    dataset_size=$(stat -f '%z' "$dataset_file" 2>/dev/null) || fail 'Resulting dataset size cannot be read.'
    dataset_hash=$(shasum -a 256 "$dataset_file" | awk '{print $1}')
else
    dataset_size=0
    dataset_hash=none
fi

printf '%s\n' 'ok=true'
printf 'dataset=%s\n' "$dataset_name"
printf '%s\n' "$merge_output"
printf 'bytes=%s\n' "$dataset_size"
printf 'sha256=%s\n' "$dataset_hash"
