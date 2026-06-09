#!/usr/bin/env zsh
emulate -L zsh
set -euo pipefail

repo_root="${0:A:h}"
"$repo_root/scripts/restow-all"
