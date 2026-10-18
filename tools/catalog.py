"""catalog.json: every add-on with its texts, privacy, capabilities and the SHA-256 of its zip.
Asterism fetches it (and catalog.sig) from this repository's main branch and checks the signature
with the author's built-in key before it uses anything of it."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/uBruckhaus/asterism-addons"
FIELDS = ("id", "name", "version", "api", "kind", "icon", "summary", "description", "privacy", "capabilities",
          "harnesses", "reads", "sends", "detect")
entries = []
for meta_file in sorted(ROOT.glob("*/addon.json")):
    meta = json.loads(meta_file.read_text())
    zip_path = ROOT / "dist" / f"{meta['id']}-{meta['version']}.zip"
    if not zip_path.is_file():
        continue
    data = zip_path.read_bytes()
    entry = {k: meta[k] for k in FIELDS if k in meta}
    entry.update(url=f"{REPO}/releases/download/{meta['id']}-{meta['version']}/{zip_path.name}",
                 size=len(data), sha256=hashlib.sha256(data).hexdigest())
    entries.append(entry)
(ROOT / "catalog.json").write_text(json.dumps({"catalog": 1, "addons": entries}, indent=2, ensure_ascii=False) + "\n")
print(len(entries), "add-ons in catalog.json")
