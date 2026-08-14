#!/bin/sh

set -eu

fail() {
    printf '%s\n' 'ok=false' >&2
    printf 'error=%s\n' "$1" >&2
    exit 2
}

[ "$#" -eq 3 ] || [ "$#" -eq 4 ] || fail 'Usage: validate-local-change-set.sh <change-set-path> <expected-change-set-id> <expected-draft-revision> [--require-staged].'
change_set_input=$1
expected_change_set_id=$2
expected_draft_revision=$3
require_staged=false
if [ "$#" -eq 4 ]; then
    [ "$4" = '--require-staged' ] || fail 'Unknown local validation option.'
    require_staged=true
fi
case "$expected_draft_revision" in ''|*[!0-9]*|0) fail 'Expected draft revision must be a positive integer.' ;; esac
command -v plutil >/dev/null 2>&1 || fail 'macOS plutil is required.'
command -v osascript >/dev/null 2>&1 || fail 'macOS osascript is required.'
command -v shasum >/dev/null 2>&1 || fail 'macOS shasum is required.'
script_directory=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
dataset_validator=$script_directory/validate-metadata-dataset.js
[ -f "$dataset_validator" ] || fail 'Bundled dataset validator is missing.'

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
for root_entry in "$change_set"/* "$change_set"/.[!.]* "$change_set"/..?*; do
    if [ ! -e "$root_entry" ] && [ ! -L "$root_entry" ]; then
        continue
    fi
    case "$(basename "$root_entry")" in
        change-set.json|datasets) ;;
        *) fail 'Local change-set contains an unexpected root entry.' ;;
    esac
done
plutil -convert json -o /dev/null "$state" >/dev/null 2>&1 || fail 'change-set.json is not valid JSON.'

state_raw() {
    plutil -extract "$1" raw "$state" 2>/dev/null || fail "Required Change Set value is missing: $1."
}

format_version=$(state_raw format_version)
tenant_id=$(state_raw tenant.tenant_id)
tenant_code=$(state_raw tenant.tenant_code)
snapshot_id=$(state_raw snapshot.snapshot_id)
snapshot_path=$(state_raw snapshot.path)
snapshot_usage=$(state_raw snapshot.usage)
outdated_acknowledged=$(state_raw snapshot.outdated_snapshot_warning_acknowledged)
change_set_id=$(state_raw server_change_set.metadata_change_set_id)
draft_revision=$(state_raw server_change_set.draft_revision)
server_status=$(state_raw server_change_set.status)
datasets_type=$(plutil -type datasets "$state" 2>/dev/null) || fail 'Local dataset state is missing.'

[ "$format_version" = '1.0' ] || fail 'Unsupported local Change Set format.'
case "$tenant_id" in ''|*[!0-9]*|0) fail 'Local Tenant ID is invalid.' ;; esac
[ -n "$tenant_code" ] || fail 'Local Tenant code is invalid.'
[ "$snapshot_path" = '../metadata-snapshot' ] || fail 'Snapshot path must be ../metadata-snapshot.'
case "$snapshot_usage:$outdated_acknowledged" in
    fresh:false|reused:true) ;;
    *) fail 'Snapshot usage and warning acknowledgement are inconsistent.' ;;
esac
[ "$change_set_id" = "$expected_change_set_id" ] || fail 'Metadata Change Set ID does not match the server draft.'
[ "$draft_revision" = "$expected_draft_revision" ] || fail 'Draft revision does not match the server draft.'
case "$server_status" in active|validated) ;; *) fail 'Local server status is invalid.' ;; esac
[ "$datasets_type" = 'dictionary' ] || fail 'Local dataset state must be a JSON object.'

staged_dataset_names=$(plutil -extract datasets raw "$state" 2>/dev/null) || fail 'Local dataset state cannot be read.'
staged_dataset_count=0
for staged_name in $staged_dataset_names; do
    case "$staged_name" in
        source_object|source_attribute|bronze_object|bronze_attribute|silver_object|silver_attribute|gold_object|gold_attribute|ingestion_object_mapping|ingestion_attribute_mapping|copy_group|member_group|copy_group_control|copy|process_group|process) ;;
        *) fail 'Local state contains an unknown staged dataset.' ;;
    esac
    [ "$(plutil -type "datasets.$staged_name" "$state" 2>/dev/null)" = 'dictionary' ] || fail "Staged dataset state is invalid: $staged_name."
    [ -f "$change_set/datasets/$staged_name.json" ] && [ ! -L "$change_set/datasets/$staged_name.json" ] || fail "Staged dataset file is missing: $staged_name."
    staged_dataset_count=$((staged_dataset_count + 1))
done
[ "$staged_dataset_count" -le 16 ] || fail 'Local state contains too many staged datasets.'

snapshot=$workspace/metadata-snapshot
manifest=$snapshot/manifest.json
[ -f "$manifest" ] && [ ! -L "$manifest" ] || fail 'Referenced metadata-snapshot is missing or unsafe.'
manifest_tenant=$(plutil -extract tenant_code raw "$manifest" 2>/dev/null) || fail 'Snapshot Tenant cannot be read.'
manifest_snapshot=$(plutil -extract snapshot_id raw "$manifest" 2>/dev/null) || fail 'Snapshot ID cannot be read.'
[ "$manifest_tenant" = "$tenant_code" ] || fail 'Snapshot Tenant does not match local Change Set.'
[ "$manifest_snapshot" = "$snapshot_id" ] || fail 'Snapshot ID does not match local Change Set.'

dataset_count=0
summary_lines=''
for dataset_file in "$datasets"/* "$datasets"/.[!.]* "$datasets"/..?*; do
    if [ ! -e "$dataset_file" ] && [ ! -L "$dataset_file" ]; then
        continue
    fi
    [ -f "$dataset_file" ] && [ ! -L "$dataset_file" ] || fail 'datasets may contain only regular JSON files.'
    dataset_filename=$(basename "$dataset_file")
    case "$dataset_filename" in
        *.json) dataset_name=${dataset_filename%.json} ;;
        *) fail 'datasets may contain only .json files.' ;;
    esac
    case "$dataset_name" in
        source_object|source_attribute|bronze_object|bronze_attribute|silver_object|silver_attribute|gold_object|gold_attribute|ingestion_object_mapping|ingestion_attribute_mapping|copy_group|member_group|copy_group_control|copy|process_group|process) ;;
        *) fail "Dataset is not Change Set eligible: $dataset_name." ;;
    esac
    dataset_size=$(stat -f '%z' "$dataset_file" 2>/dev/null) || fail "Cannot read dataset size: $dataset_name."
    [ "$dataset_size" -le 16777216 ] || fail "Dataset exceeds the 16 MiB Stage limit: $dataset_name."
    dataset_schema=$snapshot/schemas/$dataset_name.schema.json
    [ -f "$dataset_schema" ] && [ ! -L "$dataset_schema" ] || fail "Snapshot dataset schema is missing: $dataset_name."
    count_line=$(osascript -l JavaScript "$dataset_validator" "$dataset_schema" "$dataset_file" "$dataset_name" 2>/dev/null) || fail "Dataset does not match its schema or uniqueness rules: $dataset_name."
    case "$count_line" in record_count=*) record_count=${count_line#record_count=} ;; *) fail "Dataset validator output is invalid: $dataset_name." ;; esac
    case "$record_count" in ''|*[!0-9]*) fail "Dataset record count is invalid: $dataset_name." ;; esac
    dataset_hash=$(shasum -a 256 "$dataset_file" | awk '{print $1}')
    staged=false
    staged_revision=''
    if plutil -type "datasets.$dataset_name" "$state" >/dev/null 2>&1; then
        staged_file=$(state_raw "datasets.$dataset_name.file")
        staged_count=$(state_raw "datasets.$dataset_name.record_count")
        staged_hash=$(state_raw "datasets.$dataset_name.staged_sha256")
        staged_revision=$(state_raw "datasets.$dataset_name.staged_revision")
        [ "$staged_file" = "datasets/$dataset_name.json" ] || fail "Staged dataset path is invalid: $dataset_name."
        case "$staged_count" in ''|*[!0-9]*) fail "Staged dataset record count is invalid: $dataset_name." ;; esac
        case "$staged_revision" in ''|*[!0-9]*|0) fail "Staged dataset revision is invalid: $dataset_name." ;; esac
        printf '%s\n' "$staged_hash" | grep -Eq '^[0-9a-f]{64}$' || fail "Staged dataset SHA-256 is invalid: $dataset_name."
        [ "$staged_revision" -le "$draft_revision" ] || fail "Staged dataset revision is ahead of local state: $dataset_name."
        if [ "$staged_count" = "$record_count" ] && [ "$staged_hash" = "$dataset_hash" ]; then
            staged=true
        fi
    fi
    if [ "$require_staged" = true ] && [ "$staged" = false ]; then
        fail "Dataset is not synchronized with a successful Stage: $dataset_name."
    fi
    summary_lines=$summary_lines"dataset=$dataset_name|$record_count|$dataset_size|$dataset_hash|$staged|$staged_revision
"
    dataset_count=$((dataset_count + 1))
done
[ "$dataset_count" -le 16 ] || fail 'Local Change Set contains too many datasets.'

printf '%s' "$summary_lines"
printf '%s\n' 'ok=true'
printf 'change_set=%s\n' "$change_set"
printf 'tenant_id=%s\n' "$tenant_id"
printf 'tenant_code=%s\n' "$tenant_code"
printf 'snapshot_id=%s\n' "$snapshot_id"
printf 'snapshot_usage=%s\n' "$snapshot_usage"
printf 'metadata_change_set_id=%s\n' "$change_set_id"
printf 'draft_revision=%s\n' "$draft_revision"
printf 'server_status=%s\n' "$server_status"
printf 'dataset_count=%s\n' "$dataset_count"
