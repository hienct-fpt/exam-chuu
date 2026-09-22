"""Run the whole offline pipeline: inventory -> segment -> render -> answer_key -> build.

usage: python pipeline/run_all.py [math|japanese|science|social|all ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import inventory, segment, render, answer_key, build  # noqa: E402


def main() -> None:
    subs = tuple(sys.argv[1:]) or ("math",)
    inventory.main(subjects=None if subs == ("all",) else subs)
    segment.main()
    render.main()
    answer_key.main()
    build.main()


if __name__ == "__main__":
    main()
