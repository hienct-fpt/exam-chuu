"""Copy pipeline output (public bank + question crops) into web/public for Vite/Hosting.

Crops a bank shows as text (bank["texts"], pipeline/qtext.py) are not copied."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "out"
PUB = ROOT / "web" / "public"

as_text = set()
for f in (OUT / "bank").glob("*.json"):
    bank = json.loads(f.read_text(encoding="utf-8"))
    if isinstance(bank, dict):
        as_text.update(bank.get("texts") or {})


def skip_text_crops(src: str, names: list[str]) -> set[str]:
    rel = Path(src).relative_to(OUT).as_posix()
    return {n for n in names if f"{rel}/{n}" in as_text}


for name in ("bank", "q"):
    src, dst = OUT / name, PUB / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=skip_text_crops if name == "q" else None)
    print(f"[sync] {src} -> {dst} ({sum(1 for _ in dst.rglob('*') if _.is_file())} files)")
print(f"[sync] {len(as_text)} crops shown as text, not copied")
