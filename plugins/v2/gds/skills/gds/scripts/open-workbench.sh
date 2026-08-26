#!/usr/bin/env bash
set -euo pipefail

script_path=${BASH_SOURCE[0]}
if [[ -L "$script_path" ]]; then
  echo "open-workbench: launcher must not be a symbolic link" >&2
  exit 1
fi
script_dir=$(cd -P -- "$(dirname -- "$script_path")" && pwd)
index_path="$script_dir/../workbench/index.html"
if [[ ! -f "$index_path" || -L "$index_path" ]]; then
  echo "open-workbench: bundled index.html is missing or unsafe" >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin)
    if [[ -d "/Applications/Google Chrome.app" ]]; then
      open -a "Google Chrome" "$index_path"
    elif [[ -d "/Applications/Microsoft Edge.app" ]]; then
      open -a "Microsoft Edge" "$index_path"
    else
      echo "open-workbench: install Chrome or Edge, then rerun this launcher" >&2
      exit 1
    fi
    ;;
  Linux)
    browser=""
    for candidate in google-chrome microsoft-edge chromium chromium-browser; do
      if command -v "$candidate" >/dev/null 2>&1; then
        browser=$(command -v "$candidate")
        break
      fi
    done
    if [[ -z "$browser" ]]; then
      echo "open-workbench: install Chrome, Edge, or Chromium, then rerun this launcher" >&2
      exit 1
    fi
    "$browser" "$index_path" >/dev/null 2>&1 &
    ;;
  *)
    echo "open-workbench: open $index_path in Chrome or Edge" >&2
    exit 1
    ;;
esac
