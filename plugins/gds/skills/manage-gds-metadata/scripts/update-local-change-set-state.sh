#!/bin/sh

set -eu
umask 077

fail() {
    printf '%s\n' 'ok=false' >&2
    printf 'error=%s\n' "$1" >&2
    exit 2
}

change_set_input=$PWD/GDS/change-set
change_set_id=''
expected_revision=''
server_revision=''
server_status=''
staged_dataset=''
staged_sha256=''
staged_pairs=''

while [ "$#" -gt 0 ]; do
    case "$1" in
        --change-set|--change-set-id|--expected-current-revision|--server-revision|--server-status|--staged-dataset|--staged-sha256|--staged-pair)
            [ "$#" -ge 2 ] || fail "Missing value for $1."
            option=$1
            value=$2
            shift 2
            case "$option" in
                --change-set) change_set_input=$value ;;
                --change-set-id) change_set_id=$value ;;
                --expected-current-revision) expected_revision=$value ;;
                --server-revision) server_revision=$value ;;
                --server-status) server_status=$value ;;
                --staged-dataset) staged_dataset=$value ;;
                --staged-sha256) staged_sha256=$value ;;
                --staged-pair)
                    [ -z "$staged_pairs" ] || staged_pairs="$staged_pairs "
                    staged_pairs="${staged_pairs}${value}"
                    ;;
            esac
            ;;
        *) fail "Unknown option: $1." ;;
    esac
done

if [ -n "$staged_dataset" ] || [ -n "$staged_sha256" ]; then
    [ -n "$staged_dataset" ] && [ -n "$staged_sha256" ] || fail 'Staged dataset and SHA-256 must be supplied together.'
    [ -z "$staged_pairs" ] || fail 'Use either the single staged dataset options or staged pairs.'
    staged_pairs="$staged_dataset=$staged_sha256"
fi

case "$expected_revision" in ''|*[!0-9]*|0) fail 'Expected current revision must be positive.' ;; esac
case "$server_revision" in ''|*[!0-9]*|0) fail 'Server revision must be positive.' ;; esac
case "$server_status" in active|validated) ;; *) fail 'Server status must be active or validated.' ;; esac
[ -n "$change_set_id" ] || fail 'Metadata Change Set ID is required.'
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
[ "$(basename "$workspace")" = 'GDS' ] || fail 'Local change-set must be directly under GDS.'
change_set=$workspace/change-set
state=$change_set/change-set.json
state_temporary=$change_set/change-set.state.tmp.json
[ -f "$state" ] && [ ! -L "$state" ] || fail 'change-set.json is missing or unsafe.'
[ ! -e "$state_temporary" ] && [ ! -L "$state_temporary" ] || fail 'A previous state update is incomplete; do not overwrite it.'
plutil -convert json -o /dev/null "$state" >/dev/null 2>&1 || fail 'change-set.json is not valid JSON.'
current_change_set_id=$(plutil -extract server_change_set.metadata_change_set_id raw "$state" 2>/dev/null) || fail 'Local Metadata Change Set ID is missing.'
current_revision=$(plutil -extract server_change_set.draft_revision raw "$state" 2>/dev/null) || fail 'Local draft revision is missing.'
[ "$current_change_set_id" = "$change_set_id" ] || fail 'Metadata Change Set ID does not match local state.'
[ "$current_revision" = "$expected_revision" ] || fail 'Expected revision does not match local state.'
[ "$(plutil -type datasets "$state" 2>/dev/null)" = 'dictionary' ] || fail 'Local dataset state is invalid.'
[ "$server_revision" -ge "$expected_revision" ] || fail 'Server revision cannot move backwards.'

stage_recorded=false
stage_count=0
validated_pairs=''
if [ -n "$staged_pairs" ]; then
    [ "$server_status" = active ] || fail 'A Stage result must return active status.'
    [ "$server_revision" -eq $((expected_revision + 1)) ] || fail 'A Stage result must increment revision by exactly one.'
    seen_datasets='|'
    for staged_pair in $staged_pairs; do
        pair_dataset=${staged_pair%%=*}
        pair_sha=${staged_pair#*=}
        [ "$pair_dataset" != "$staged_pair" ] || fail 'Each staged pair must be dataset=sha256.'
        case "$pair_dataset" in
            source_object|source_attribute|bronze_object|bronze_attribute|silver_object|silver_attribute|gold_object|gold_attribute|ingestion_object_mapping|ingestion_attribute_mapping|copy_group|member_group|copy_group_control|copy|process_group|process) ;;
            *) fail 'Staged dataset is not Change Set eligible.' ;;
        esac
        case "$seen_datasets" in *"|$pair_dataset|"*) fail 'A staged dataset can be supplied only once.' ;; esac
        seen_datasets="${seen_datasets}${pair_dataset}|"
        printf '%s\n' "$pair_sha" | grep -Eq '^[0-9A-Fa-f]{64}$' || fail 'Staged SHA-256 is invalid.'
        stage_count=$((stage_count + 1))
        [ "$stage_count" -le 16 ] || fail 'At most 16 staged datasets may be recorded.'

        dataset_file=$change_set/datasets/$pair_dataset.json
        [ -f "$dataset_file" ] && [ ! -L "$dataset_file" ] || fail 'Staged local dataset file is missing or unsafe.'
        dataset_schema=$workspace/metadata-snapshot/schemas/$pair_dataset.schema.json
        [ -f "$dataset_schema" ] && [ ! -L "$dataset_schema" ] || fail 'Snapshot dataset schema is missing or unsafe.'
        count_line=$(osascript -l JavaScript "$dataset_validator" "$dataset_schema" "$dataset_file" "$pair_dataset" 2>/dev/null) || fail 'Staged local dataset does not match its schema or uniqueness rules.'
        case "$count_line" in record_count=*) record_count=${count_line#record_count=} ;; *) fail 'Dataset validator output is invalid.' ;; esac
        actual_sha256=$(shasum -a 256 "$dataset_file" | awk '{print $1}')
        normalized_staged_sha=$(printf '%s' "$pair_sha" | tr '[:upper:]' '[:lower:]')
        [ "$actual_sha256" = "$normalized_staged_sha" ] || fail 'Dataset changed after the reviewed SHA-256 was produced.'
        [ -z "$validated_pairs" ] || validated_pairs="$validated_pairs "
        validated_pairs="${validated_pairs}${pair_dataset}:${actual_sha256}:${record_count}"
    done

    cp "$state" "$state_temporary"
    for validated_pair in $validated_pairs; do
        pair_dataset=${validated_pair%%:*}
        pair_remainder=${validated_pair#*:}
        actual_sha256=${pair_remainder%%:*}
        record_count=${pair_remainder#*:}
        dataset_file=$change_set/datasets/$pair_dataset.json
        current_sha256=$(shasum -a 256 "$dataset_file" | awk '{print $1}')
        [ "$current_sha256" = "$actual_sha256" ] || fail 'Dataset changed while Stage state was being recorded.'
        if plutil -type "datasets.$pair_dataset" "$state_temporary" >/dev/null 2>&1; then
            plutil -remove "datasets.$pair_dataset" "$state_temporary"
        fi
        plutil -insert "datasets.$pair_dataset" -dictionary "$state_temporary"
        plutil -insert "datasets.$pair_dataset.file" -string "datasets/$pair_dataset.json" "$state_temporary"
        plutil -insert "datasets.$pair_dataset.record_count" -integer "$record_count" "$state_temporary"
        plutil -insert "datasets.$pair_dataset.staged_sha256" -string "$actual_sha256" "$state_temporary"
        plutil -insert "datasets.$pair_dataset.staged_revision" -integer "$server_revision" "$state_temporary"
    done
    stage_recorded=true
else
    cp "$state" "$state_temporary"
    if [ "$server_revision" -gt "$expected_revision" ]; then
        plutil -replace datasets -dictionary "$state_temporary"
    fi
fi

plutil -replace server_change_set.draft_revision -integer "$server_revision" "$state_temporary"
plutil -replace server_change_set.status -string "$server_status" "$state_temporary"
mv "$state_temporary" "$state"

printf '%s\n' 'ok=true'
printf 'change_set=%s\n' "$change_set"
printf 'metadata_change_set_id=%s\n' "$change_set_id"
printf 'previous_revision=%s\n' "$expected_revision"
printf 'draft_revision=%s\n' "$server_revision"
printf 'server_status=%s\n' "$server_status"
printf 'stage_recorded=%s\n' "$stage_recorded"
if [ "$stage_recorded" = true ]; then
    printf 'staged_dataset_count=%s\n' "$stage_count"
    for validated_pair in $validated_pairs; do
        pair_dataset=${validated_pair%%:*}
        pair_remainder=${validated_pair#*:}
        actual_sha256=${pair_remainder%%:*}
        record_count=${pair_remainder#*:}
        printf 'staged_dataset=%s|%s|%s\n' "$pair_dataset" "$record_count" "$actual_sha256"
    done
    if [ "$stage_count" -eq 1 ]; then
        printf 'dataset=%s\n' "$pair_dataset"
        printf 'record_count=%s\n' "$record_count"
        printf 'staged_sha256=%s\n' "$actual_sha256"
    fi
fi
