#!/bin/sh
# Build, sign and package one add-on, then rebuild and sign the catalog.
#   tools/release.sh <add-on id>         (asks for the signing key's passphrase, twice)
# KEY=<private key> overrides ~/.ssh/asterism-addons (tests use a throw-away key).
set -eu
cd "$(dirname "$0")/.."
id=${1:?usage: tools/release.sh <add-on id>}
key=${KEY:-$HOME/.ssh/asterism-addons}
[ -f "$id/addon.json" ] || { echo "no add-on $id" >&2; exit 1; }
version=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$id/addon.json")
# 1. the signed list of files (every file but the list and the signature; Python's caches go first:
#    the app refuses an add-on with a file the list does not need)
find "$id" -name __pycache__ -type d -prune -exec rm -rf {} +
( cd "$id" && rm -f MANIFEST.sha256 SIGNATURE &&
  find . -type f ! -name MANIFEST.sha256 ! -name SIGNATURE | sed 's|^\./||' | LC_ALL=C sort |
  while read -r f; do sha256sum "$f"; done > MANIFEST.sha256 )
ssh-keygen -q -Y sign -f "$key" -n asterism-addon "$id/MANIFEST.sha256"
mv "$id/MANIFEST.sha256.sig" "$id/SIGNATURE"
# 2. the zip (the folder itself, owner-readable files only)
mkdir -p dist
rm -f "dist/$id-$version.zip"
chmod -R u=rwX,go=rX "$id"
python3 tools/zip_addon.py "$id" "dist/$id-$version.zip"
# 3. the catalog, signed too
python3 tools/catalog.py
ssh-keygen -q -Y sign -f "$key" -n asterism-addon catalog.json
mv catalog.json.sig catalog.sig
echo "$id $version: dist/$id-$version.zip, catalog.json + catalog.sig"
