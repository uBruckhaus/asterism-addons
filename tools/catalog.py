"""catalog.json: every add-on with its texts, privacy, capabilities and the SHA-256 of its zip.
Asterism fetches it (and catalog.sig) from this repository's main branch and checks the signature
with the author's built-in key before it uses anything of it."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/uBruckhaus/asterism-addons"
FIELDS = ("id", "name", "version", "api", "kind", "icon", "summary", "description", "privacy", "capabilities",
          "harnesses", "reads", "sends", "detect", "homepage", "needs", "provides")


def entry(meta: dict, zip_path: Path) -> dict:
    data = zip_path.read_bytes()
    found = {k: meta[k] for k in FIELDS if k in meta}
    found.update(url=f"{REPO}/releases/download/{meta['id']}-{meta['version']}/{zip_path.name}",
                 size=len(data), sha256=hashlib.sha256(data).hexdigest())
    return found


# Older versions first (legacy.json): older Asterism releases take an add-on's first entry.
entries = []
for name in json.loads((ROOT / "legacy.json").read_text())["keep"]:
    zip_path = ROOT / "dist" / f"{name}.zip"
    if not zip_path.is_file():          # tools/publish.sh refuses to publish without it
        print(f"legacy.json: no {zip_path.relative_to(ROOT)} yet (tools/release-old.sh makes older versions)")
        continue
    with zipfile.ZipFile(zip_path) as zf:
        meta = json.loads(zf.read(f"{name.rsplit('-', 1)[0]}/addon.json"))
    entries.append(entry(meta, zip_path))
for meta_file in sorted(ROOT.glob("*/addon.json")):
    meta = json.loads(meta_file.read_text())
    zip_path = ROOT / "dist" / f"{meta['id']}-{meta['version']}.zip"
    if zip_path.is_file():
        entries.append(entry(meta, zip_path))
(ROOT / "catalog.json").write_text(json.dumps({"catalog": 1, "addons": entries}, indent=2, ensure_ascii=False) + "\n")
print(len(entries), "add-ons in catalog.json")
