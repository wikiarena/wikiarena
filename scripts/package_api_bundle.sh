#!/bin/bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: package_api_bundle.sh <output-dir> <version-label>" >&2
  exit 1
fi

output_dir="$1"
version_label="$2"
bundle_path="${output_dir}/wikiarena-api-${version_label}.tar.gz"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

mkdir -p "$output_dir"
rm -f "$bundle_path"

tar \
  --create \
  --gzip \
  --file "$bundle_path" \
  --exclude=".DS_Store" \
  --exclude="__pycache__" \
  --directory "$repo_root" \
  pyproject.toml \
  uv.lock \
  README.md \
  src

printf '%s\n' "$bundle_path"
