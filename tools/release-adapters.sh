#!/bin/sh
# The agent and provider adapters as signed add-ons: generated from the Asterism checkout
# (tools/build-adapter-addons.py there: each addon.py is the adapter module itself), then each one
# signed, zipped and put into the catalog by tools/release.sh. The passphrase is asked once: the key
# goes into an ssh-agent started for this run only.
#   tools/release-adapters.sh           ASTERISM=<checkout> (default ../asterism), KEY=<private key>
# Also dist/adapters-<version>.zip: all of them in one archive for the Asterism packages.
set -eu
cd "$(dirname "$0")/.."
asterism=${ASTERISM:-../asterism}
key=${KEY:-$HOME/.ssh/asterism-addons}
python3 "$asterism/tools/build-adapter-addons.py" .
# An agent of its own (never the session's): the key is gone when the run ends.
eval "$(ssh-agent -s)" >/dev/null
trap 'ssh-agent -k >/dev/null' EXIT
ssh-add -q "$key"
for folder in agent-*/ llm-*/ providers-online/; do
    KEY="$key.pub" sh tools/release.sh "${folder%/}"     # the public key: ssh-keygen signs through the agent
done
# One archive with all of them for the Asterism packages (AppImage build.sh, AUR PKGBUILD): a release
# asset adapters-<version>.
version=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" agent-claude/addon.json)
python3 tools/zip_bundle.py "dist/adapters-$version.zip" agent-*/ llm-*/ providers-online/
sha256sum "dist/adapters-$version.zip"
