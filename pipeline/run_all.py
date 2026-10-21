"""Run the whole offline pipeline: inventory -> segment -> render -> kaisetsu -> qtext -> answer keys -> build.

usage: python pipeline/run_all.py [all | math japanese science social ...]   (default: all)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import inventory, segment, render, kaisetsu, seitouritsu, qtext, answer_key, answer_key_generic, build  # noqa: E402


def main() -> None:
    subs = tuple(sys.argv[1:]) or ("all",)
    inventory.main(subjects=None if subs == ("all",) else subs)
    segment.main()
    render.main()
    kaisetsu.main()              # 組分け 解説 crops (after render: it wipes q/)
    seitouritsu.main()           # 組分け 全受験者の平均点 (正答率一覧, 結果 column never read) -> functions/
    qtext.main()                 # text-only 算数・理科・社会 crops -> html (bank["texts"])
    answer_key.main()            # math (position-matched 模範解答)
    answer_key_generic.main()    # science / social (table cells), japanese (vertical columns), shinagawa (tree + transcribed overrides)
    build.main()


if __name__ == "__main__":
    main()
