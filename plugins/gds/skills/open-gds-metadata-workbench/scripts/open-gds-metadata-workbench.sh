#!/bin/sh

set -eu

fail() {
    printf '%s\n' 'ok=false' >&2
    printf 'error=%s\n' "$1" >&2
    exit 2
}

script_directory=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
workbench=$script_directory/../assets/workbench/index.html
[ -f "$workbench" ] && [ ! -L "$workbench" ] || fail 'Bundled Data Workbench is missing or unsafe.'

case "$(uname -s)" in
    Darwin) command -v open >/dev/null 2>&1 || fail 'macOS open command is unavailable.'; open "$workbench" ;;
    Linux) command -v xdg-open >/dev/null 2>&1 || fail 'xdg-open is unavailable.'; xdg-open "$workbench" >/dev/null 2>&1 ;;
    *) fail 'Use the PowerShell launcher on Windows.' ;;
esac

printf '%s\n' 'ok=true'
printf '%s\n' 'opened=true'
printf '%s\n' 'target=default-browser'
