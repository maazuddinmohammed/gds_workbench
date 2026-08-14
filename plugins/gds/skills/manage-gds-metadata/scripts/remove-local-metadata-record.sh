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
key_input=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --change-set|--dataset|--key-file)
            [ "$#" -ge 2 ] || fail "Missing value for $1."
            option=$1
            value=$2
            shift 2
            case "$option" in
                --change-set) change_set_input=$value ;;
                --dataset) dataset_name=$value ;;
                --key-file) key_input=$value ;;
            esac
            ;;
        *) fail "Unknown option: $1." ;;
    esac
done

[ -n "$change_set_input" ] || fail 'Local Change Set path is required.'
[ -n "$key_input" ] || fail 'One canonical-key JSON file is required.'
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
[ "$(basename "$workspace")" = 'gds-workspace' ] || fail 'Local change-set must be directly under gds-workspace.'
change_set=$workspace/change-set
state=$change_set/change-set.json
datasets=$change_set/datasets
[ -f "$state" ] && [ ! -L "$state" ] || fail 'change-set.json is missing or unsafe.'
[ -d "$datasets" ] && [ ! -L "$datasets" ] || fail 'datasets directory is missing or unsafe.'
[ -z "$(find "$change_set" -type l -print -quit)" ] || fail 'Local change-set cannot contain symbolic links.'
snapshot_path=$(plutil -extract snapshot.path raw "$state" 2>/dev/null) || fail 'Snapshot path is missing from local state.'
[ "$snapshot_path" = '../metadata-snapshot' ] || fail 'Snapshot path must be ../metadata-snapshot.'

schema=$workspace/metadata-snapshot/schemas/$dataset_name.schema.json
dataset_file=$datasets/$dataset_name.json
[ -f "$schema" ] && [ ! -L "$schema" ] || fail 'Snapshot dataset schema is missing or unsafe.'
[ -f "$dataset_file" ] && [ ! -L "$dataset_file" ] || fail 'Local pending dataset is missing or unsafe.'
case "$key_input" in
    /*) key_file=$key_input ;;
    *) key_file=$PWD/$key_input ;;
esac
[ -f "$key_file" ] && [ ! -L "$key_file" ] || fail 'Canonical key must be a regular, non-symbolic-link JSON file.'
key_size=$(stat -f '%z' "$key_file" 2>/dev/null) || fail 'Canonical key size cannot be read.'
[ "$key_size" -le 1048576 ] || fail 'Canonical key file exceeds 1 MiB.'

remove_output=$(osascript -l JavaScript "$dataset_helper" "$schema" "$dataset_file" "$dataset_name" "$key_file" "$dataset_file" remove 2>/dev/null) || fail "Canonical key or accumulated dataset does not match the Snapshot schema: $dataset_name."
case "$remove_output" in
    action=not_found*) fail 'Canonical key is not present in the local pending dataset.' ;;
    action=removed*) ;;
    *) fail 'Dataset helper output is invalid.' ;;
esac
record_count=$(printf '%s\n' "$remove_output" | sed -n 's/^record_count=//p')
case "$record_count" in ''|*[!0-9]*) fail 'Resulting record count is invalid.' ;; esac
dataset_empty=false
[ "$record_count" -ne 0 ] || dataset_empty=true
dataset_size=$(stat -f '%z' "$dataset_file" 2>/dev/null) || fail 'Resulting dataset size cannot be read.'
dataset_hash=$(shasum -a 256 "$dataset_file" | awk '{print $1}')

printf '%s\n' 'ok=true'
printf 'dataset=%s\n' "$dataset_name"
printf '%s\n' "$remove_output"
printf 'dataset_empty=%s\n' "$dataset_empty"
printf 'bytes=%s\n' "$dataset_size"
printf 'sha256=%s\n' "$dataset_hash"
