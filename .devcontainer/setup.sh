#!/usr/bin/env bash
set -euo pipefail

backend_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_dir="$(dirname -- "$backend_dir")"

# Preserve the sibling layout referenced by the existing workspace file.
for repo in ei-admin-ui-nextjs ei-ui-nextjs; do
  target="$workspace_dir/$repo"
  if [ ! -e "$target" ]; then
    git clone "https://github.com/khalidrazaa/$repo.git" "$target"
  elif [ ! -d "$target" ]; then
    echo "Cannot set up $repo: $target exists but is not a directory." >&2
    exit 1
  fi
done

cd "$backend_dir"
python -m pip install --user uv
export PATH="$HOME/.local/bin:$PATH"
uv sync --locked

for repo in ei-admin-ui-nextjs ei-ui-nextjs; do
  (cd "$workspace_dir/$repo" && npm ci)
done
