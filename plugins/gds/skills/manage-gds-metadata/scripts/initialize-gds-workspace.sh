#!/bin/sh

set -eu
umask 077

fail() {
    printf '%s\n' 'ok=false' >&2
    printf 'error=%s\n' "$1" >&2
    exit 2
}

root_input=${1:-"$PWD/gds-workspace"}
case "$root_input" in
    /*) root_candidate=$root_input ;;
    *) root_candidate=$PWD/$root_input ;;
esac

parent_candidate=$(dirname "$root_candidate")
leaf=$(basename "$root_candidate")
[ "$leaf" = "gds-workspace" ] || fail 'Workspace directory must be named gds-workspace.'
[ -d "$parent_candidate" ] || fail 'Workspace parent directory does not exist.'
[ ! -L "$parent_candidate" ] || fail 'Workspace parent cannot be a symbolic link.'

parent=$(cd "$parent_candidate" && pwd -P)
root=$parent/gds-workspace
created=false

if [ -e "$root" ] || [ -L "$root" ]; then
    [ -d "$root" ] || fail 'Workspace path exists but is not a directory.'
    [ ! -L "$root" ] || fail 'Workspace directory cannot be a symbolic link.'
else
    mkdir "$root"
    created=true
fi

ignore=$root/.gitignore
expected_ignore='*
!.gitignore'
if [ -e "$ignore" ] || [ -L "$ignore" ]; then
    [ -f "$ignore" ] || fail 'Workspace .gitignore must be a regular file.'
    [ ! -L "$ignore" ] || fail 'Workspace .gitignore cannot be a symbolic link.'
    current_ignore=$(cat "$ignore")
    [ "$current_ignore" = "$expected_ignore" ] || fail 'Workspace .gitignore has unexpected content.'
else
    printf '%s\n' '*' '!.gitignore' > "$ignore"
fi

for managed in "$root/metadata-snapshot" "$root/change-set"; do
    if [ -e "$managed" ] || [ -L "$managed" ]; then
        [ -d "$managed" ] || fail 'A managed workspace path exists but is not a directory.'
        [ ! -L "$managed" ] || fail 'Managed workspace directories cannot be symbolic links.'
    fi
done

metadata_snapshot_exists=false
change_set_exists=false
[ ! -d "$root/metadata-snapshot" ] || metadata_snapshot_exists=true
[ ! -d "$root/change-set" ] || change_set_exists=true

printf '%s\n' 'ok=true'
printf 'workspace=%s\n' "$root"
printf 'created=%s\n' "$created"
printf 'metadata_snapshot_exists=%s\n' "$metadata_snapshot_exists"
printf 'change_set_exists=%s\n' "$change_set_exists"
