"""Run the whole offline pipeline: inventory -> segment -> render -> answer keys -> build.

usage: python pipeline/run_all.py [all | math japanese science social ...]   (default: all)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import inventory, segment, render, answer_key, answer_key_generic, build  # noqa: E402


def main() -> None:
    subs = tuple(sys.argv[1:]) or ("all",)
    inventory.main(subjects=None if subs == ("all",) else subs)
    segment.main()
    render.main()
    answer_key.main()            # math (position-matched 模範解答)
    answer_key_generic.main()    # science / social (table cells) and japanese (vertical columns)
    build.main()


if __name__ == "__main__":
    main()
