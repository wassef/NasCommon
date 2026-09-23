#!/usr/bin/env bash
# Hand a tagged build of NasCommon to a consumer that installs offline.
#
#   bin/vendor.sh <consumer repo> [tag]      # default tag: the newest v* tag
#
# Builds the wheel from a clean checkout of the tag (never the working tree, so what a consumer
# carries is exactly what the tag says), removes any older nascommon wheel from <consumer>/vendor/
# and copies the new one in. The consumer then points its dependency at the file and re-locks:
#   uv: [tool.uv.sources] nascommon = { path = "vendor/nascommon-<version>-py3-none-any.whl" }
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
consumer="${1:?usage: bin/vendor.sh <consumer repo> [tag]}"
tag="${2:-$(git -C "$here" tag --list 'v*' --sort=-v:refname | head -1)}"
[[ -n "$tag" ]] || { echo "no v* tag to build from" >&2; exit 1; }
[[ -d "$consumer" ]] || { echo "no such consumer: $consumer" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git -C "$here" archive --format=tar "$tag" | tar -x -C "$work"
(cd "$work" && uv build --wheel -q -o dist)
wheel="$(ls "$work"/dist/nascommon-*.whl)"

mkdir -p "$consumer/vendor"
rm -f "$consumer"/vendor/nascommon-*.whl
cp "$wheel" "$consumer/vendor/"
echo "$(basename "$wheel") ($tag) → $consumer/vendor/"
