"""Zip signed add-on folders into one archive for the Asterism packages (AppImage, AUR):
<id>/<file> for each folder, only the files its MANIFEST.sha256 lists plus MANIFEST.sha256 and
SIGNATURE, sorted, fixed time.   zip_bundle.py <target.zip> <folder>..."""
import sys
import zipfile
from pathlib import Path

target, folders = Path(sys.argv[1]), [Path(f) for f in sys.argv[2:]]
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
    for folder in sorted(folders, key=lambda f: f.name):
        manifest = (folder / "MANIFEST.sha256").read_text()
        if not (folder / "SIGNATURE").is_file():
            sys.exit(f"{folder.name} is not signed")
        names = sorted([line.split("  ", 1)[1] for line in manifest.splitlines()] + ["MANIFEST.sha256", "SIGNATURE"])
        for name in names:
            info = zipfile.ZipInfo(f"{folder.name}/{name}", (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, (folder / name).read_bytes())
print(f"{len(folders)} add-ons in {target}")
