"""Zip an add-on folder reproducibly (sorted, fixed time, no extra attributes): <id>/<files>."""
import sys
import zipfile
from pathlib import Path

folder, target = Path(sys.argv[1]), Path(sys.argv[2])
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()):
        info = zipfile.ZipInfo(f"{folder.name}/{path.relative_to(folder).as_posix()}", (2026, 1, 1, 0, 0, 0))
        info.external_attr = 0o644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, path.read_bytes())
