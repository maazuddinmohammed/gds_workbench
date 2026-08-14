#!/bin/sh

set -eu
umask 077

fail() {
    printf '%s\n' 'ok=false' >&2
    printf 'error=%s\n' "$1" >&2
    exit 2
}

workspace_input=$PWD/gds-workspace
tenant_id=''
tenant_code=''
snapshot_id=''
snapshot_usage=''
change_set_id=''
server_status=''
draft_revision=''
outdated_acknowledged=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --workspace|--tenant-id|--tenant-code|--snapshot-id|--snapshot-usage|--change-set-id|--server-status|--draft-revision)
            [ "$#" -ge 2 ] || fail "Missing value for $1."
            option=$1
            value=$2
            shift 2
            case "$option" in
                --workspace) workspace_input=$value ;;
                --tenant-id) tenant_id=$value ;;
                --tenant-code) tenant_code=$value ;;
                --snapshot-id) snapshot_id=$value ;;
                --snapshot-usage) snapshot_usage=$value ;;
                --change-set-id) change_set_id=$value ;;
                --server-status) server_status=$value ;;
                --draft-revision) draft_revision=$value ;;
            esac
            ;;
        --acknowledge-outdated-snapshot)
            outdated_acknowledged=true
            shift
            ;;
        *) fail "Unknown option: $1." ;;
    esac
done

case "$tenant_id" in ''|*[!0-9]*|0) fail 'Tenant ID must be a positive integer.' ;; esac
[ -n "$tenant_code" ] || fail 'Tenant code is required.'
case "$draft_revision" in ''|*[!0-9]*|0) fail 'Draft revision must be a positive integer.' ;; esac
printf '%s\n' "$snapshot_id" | grep -Eq '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$' || fail 'Snapshot ID must be a UUID.'
printf '%s\n' "$change_set_id" | grep -Eq '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$' || fail 'Metadata Change Set ID must be a UUID.'
case "$snapshot_usage" in fresh|reused) ;; *) fail 'Snapshot usage must be fresh or reused.' ;; esac
case "$server_status" in active|validated) ;; *) fail 'Server status must be active or validated.' ;; esac
if [ "$snapshot_usage" = reused ] && [ "$outdated_acknowledged" != true ]; then
    fail 'Reused Snapshot requires explicit outdated-Snapshot acknowledgement.'
fi
if [ "$snapshot_usage" = fresh ] && [ "$outdated_acknowledged" = true ]; then
    fail 'Fresh Snapshot cannot be marked as outdated.'
fi
command -v plutil >/dev/null 2>&1 || fail 'macOS plutil is required.'

case "$workspace_input" in
    /*) workspace_candidate=$workspace_input ;;
    *) workspace_candidate=$PWD/$workspace_input ;;
esac
[ "$(basename "$workspace_candidate")" = 'gds-workspace' ] || fail 'Workspace directory must be named gds-workspace.'
[ -d "$workspace_candidate" ] && [ ! -L "$workspace_candidate" ] || fail 'Workspace directory is missing or unsafe.'
workspace_parent=$(cd "$(dirname "$workspace_candidate")" && pwd -P)
workspace=$workspace_parent/gds-workspace
snapshot=$workspace/metadata-snapshot
manifest=$snapshot/manifest.json
[ -f "$manifest" ] && [ ! -L "$manifest" ] || fail 'Validated metadata-snapshot is required.'
manifest_tenant=$(plutil -extract tenant_code raw "$manifest" 2>/dev/null) || fail 'Snapshot Tenant cannot be read.'
manifest_snapshot=$(plutil -extract snapshot_id raw "$manifest" 2>/dev/null) || fail 'Snapshot ID cannot be read.'
[ "$manifest_tenant" = "$tenant_code" ] || fail 'Snapshot Tenant does not match the Change Set Tenant.'
[ "$manifest_snapshot" = "$snapshot_id" ] || fail 'Snapshot ID does not match the selected Snapshot.'

change_set=$workspace/change-set
if [ -e "$change_set" ] || [ -L "$change_set" ]; then
    fail 'Local change-set already exists; stop and ask whether to reuse it.'
fi
mkdir "$change_set"
mkdir "$change_set/datasets"

state=$change_set/change-set.json
state_temporary=$change_set/change-set.tmp.json
printf '%s\n' '{"_seed":true}' > "$state_temporary"
plutil -insert format_version -string '1.0' "$state_temporary"
plutil -insert tenant -dictionary "$state_temporary"
plutil -insert tenant.tenant_id -integer "$tenant_id" "$state_temporary"
plutil -insert tenant.tenant_code -string "$tenant_code" "$state_temporary"
plutil -insert snapshot -dictionary "$state_temporary"
plutil -insert snapshot.snapshot_id -string "$snapshot_id" "$state_temporary"
plutil -insert snapshot.path -string '../metadata-snapshot' "$state_temporary"
plutil -insert snapshot.usage -string "$snapshot_usage" "$state_temporary"
plutil -insert snapshot.outdated_snapshot_warning_acknowledged -bool "$outdated_acknowledged" "$state_temporary"
plutil -insert server_change_set -dictionary "$state_temporary"
plutil -insert server_change_set.metadata_change_set_id -string "$change_set_id" "$state_temporary"
plutil -insert server_change_set.draft_revision -integer "$draft_revision" "$state_temporary"
plutil -insert server_change_set.status -string "$server_status" "$state_temporary"
plutil -insert datasets -dictionary "$state_temporary"
plutil -remove _seed "$state_temporary"
mv "$state_temporary" "$state"

printf '%s\n' 'ok=true'
printf 'change_set=%s\n' "$change_set"
printf 'tenant_id=%s\n' "$tenant_id"
printf 'tenant_code=%s\n' "$tenant_code"
printf 'snapshot_id=%s\n' "$snapshot_id"
printf 'snapshot_usage=%s\n' "$snapshot_usage"
printf 'metadata_change_set_id=%s\n' "$change_set_id"
printf 'draft_revision=%s\n' "$draft_revision"
printf 'server_status=%s\n' "$server_status"
