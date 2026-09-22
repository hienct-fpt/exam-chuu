"""Copy pipeline output (public bank + question crops) into web/public for Vite/Hosting."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "out"
PUB = ROOT / "web" / "public"

for name in ("bank", "q"):
    src, dst = OUT / name, PUB / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"[sync] {src} -> {dst} ({sum(1 for _ in dst.rglob('*') if _.is_file())} files)")
