#!/bin/sh
# An older version of an add-on, for older Asterism releases (legacy.json keeps it in the catalog):
# the add-on's folder as of a git revision, with a new version number, signed and zipped as release.sh
# does, without touching the add-on's folder or the catalog (the next release.sh run lists it).
#   tools/release-old.sh <add-on id> <git revision> <version>     e.g. insights 5a1ffc0 1.0.1
# KEY=<private key> overrides ~/.ssh/asterism-addons.
set -eu
cd "$(dirname "$0")/.."
id=${1:?usage: tools/release-old.sh <add-on id> <git revision> <version>}
rev=${2:?git revision}
version=${3:?version}
key=${KEY:-$HOME/.ssh/asterism-addons}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git archive "$rev" "$id" | tar -x -C "$work"
rm -f "$work/$id/MANIFEST.sha256" "$work/$id/SIGNATURE"
find "$work/$id" -name __pycache__ -type d -prune -exec rm -rf {} +
python3 - "$work/$id/addon.json" "$version" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
meta = json.load(open(path))
meta["version"] = version
open(path, "w").write(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
PY
( cd "$work/$id" && find . -type f ! -name MANIFEST.sha256 ! -name SIGNATURE | sed 's|^\./||' | LC_ALL=C sort |
  while read -r f; do sha256sum "$f"; done > MANIFEST.sha256 )
ssh-keygen -q -Y sign -f "$key" -n asterism-addon "$work/$id/MANIFEST.sha256"
mv "$work/$id/MANIFEST.sha256.sig" "$work/$id/SIGNATURE"
mkdir -p dist
chmod -R u=rwX,go=rX "$work/$id"
python3 tools/zip_addon.py "$work/$id" "dist/$id-$version.zip"
echo "$id $version (from $rev): dist/$id-$version.zip — the next tools/release.sh run puts it into the catalog"
