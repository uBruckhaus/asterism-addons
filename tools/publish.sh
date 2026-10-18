#!/bin/sh
# After release.sh / release-adapters.sh: every zip in dist/ as the asset of its GitHub release
# (<id>-<version>, the URL the catalog names), then catalog.json + catalog.sig pushed to main, where
# Asterism reads them. Releases that exist already are left as they are.
#   tools/publish.sh
set -eu
cd "$(dirname "$0")/.."
[ -f catalog.json ] && [ -f catalog.sig ] || { echo "no signed catalog: run tools/release.sh first" >&2; exit 1; }
for zip in dist/*.zip; do
    tag=$(basename "$zip" .zip)
    if gh release view "$tag" >/dev/null 2>&1; then
        echo "$tag: released already"
        continue
    fi
    case "$tag" in
        adapters-*) notes="All signed agent and provider add-ons in one archive, for the Asterism packages (AppImage, AUR)." ;;
        *) notes=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('summary', ''))" \
                   "${tag%-*}/addon.json") ;;
    esac
    gh release create "$tag" "$zip" --title "$tag" --notes "$notes"
done
git add catalog.json catalog.sig
git diff --cached --quiet || git commit -q -m "Catalog: $(python3 -c "import json; print(len(json.load(open('catalog.json'))['addons']))") add-ons"
git push -q
echo "published; Asterism reads the catalog within six hours (or at once after Settings › Add-ons › Open)"
