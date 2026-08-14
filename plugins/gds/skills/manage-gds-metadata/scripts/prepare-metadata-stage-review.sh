#!/bin/sh

set -eu
umask 077

fail() {
    printf '%s\n' 'ok=false' >&2
    printf 'error=%s\n' "$1" >&2
    exit 2
}

change_set_input=''
change_set_id=''
expected_revision=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --change-set|--change-set-id|--expected-draft-revision)
            [ "$#" -ge 2 ] || fail "Missing value for $1."
            option=$1
            value=$2
            shift 2
            case "$option" in
                --change-set) change_set_input=$value ;;
                --change-set-id) change_set_id=$value ;;
                --expected-draft-revision) expected_revision=$value ;;
            esac
            ;;
        *) fail "Unknown option: $1." ;;
    esac
done

[ -n "$change_set_input" ] || fail 'Local Change Set path is required.'
[ -n "$change_set_id" ] || fail 'Metadata Change Set ID is required.'
case "$expected_revision" in ''|*[!0-9]*|0) fail 'Expected draft revision must be positive.' ;; esac
command -v plutil >/dev/null 2>&1 || fail 'macOS plutil is required.'
command -v osascript >/dev/null 2>&1 || fail 'macOS osascript is required.'
command -v shasum >/dev/null 2>&1 || fail 'macOS shasum is required.'
script_directory=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
local_validator=$script_directory/validate-local-change-set.sh
review_builder=$script_directory/build-stage-review.js
[ -x "$local_validator" ] || fail 'Bundled local Change Set validator is missing.'
[ -f "$review_builder" ] || fail 'Bundled Stage review builder is missing.'

case "$change_set_input" in
    /*) change_set_candidate=$change_set_input ;;
    *) change_set_candidate=$PWD/$change_set_input ;;
esac
[ "$(basename "$change_set_candidate")" = 'change-set' ] || fail 'Local directory must be named change-set.'
[ -d "$change_set_candidate" ] && [ ! -L "$change_set_candidate" ] || fail 'Local change-set is missing or unsafe.'
workspace=$(cd "$(dirname "$change_set_candidate")" && pwd -P)
[ "$(basename "$workspace")" = 'gds-workspace' ] || fail 'Local change-set must be directly under gds-workspace.'
change_set=$workspace/change-set
snapshot=$workspace/metadata-snapshot
state=$change_set/change-set.json
datasets=$change_set/datasets
review=$change_set/review.json
[ -f "$state" ] && [ ! -L "$state" ] || fail 'change-set.json is missing or unsafe.'
[ -d "$datasets" ] && [ ! -L "$datasets" ] || fail 'datasets directory is missing or unsafe.'
if [ -e "$review" ] || [ -L "$review" ]; then
    [ -f "$review" ] && [ ! -L "$review" ] || fail 'Existing Stage review is unsafe.'
fi

current_change_set_id=$(plutil -extract server_change_set.metadata_change_set_id raw "$state" 2>/dev/null) || fail 'Local Metadata Change Set ID is missing.'
current_revision=$(plutil -extract server_change_set.draft_revision raw "$state" 2>/dev/null) || fail 'Local draft revision is missing.'
[ "$current_change_set_id" = "$change_set_id" ] || fail 'Metadata Change Set ID does not match local state.'
[ "$current_revision" = "$expected_revision" ] || fail 'Expected revision does not match local state.'
"$local_validator" "$change_set" "$change_set_id" "$expected_revision" >/dev/null || fail 'Local Change Set must pass validation before review.'

set -- "$change_set" "$snapshot" "$review"
dataset_count=0
for dataset_file in "$datasets"/*.json; do
    [ -e "$dataset_file" ] || continue
    dataset_name=$(basename "$dataset_file" .json)
    dataset_hash=$(shasum -a 256 "$dataset_file" | awk '{print $1}')
    set -- "$@" "$dataset_name" "$dataset_hash"
    dataset_count=$((dataset_count + 1))
done
[ "$dataset_count" -gt 0 ] || fail 'At least one local dataset is required for Stage review.'
review_output=$(osascript -l JavaScript "$review_builder" "$@" 2>/dev/null) || fail 'Stage review could not be built from the Snapshot baseline.'
[ -f "$review" ] && [ ! -L "$review" ] || fail 'Stage review output is missing or unsafe.'

printf '%s\n' 'ok=true'
printf 'review=%s\n' "$review"
printf 'metadata_change_set_id=%s\n' "$change_set_id"
printf 'draft_revision=%s\n' "$expected_revision"
printf '%s\n' "$review_output"
