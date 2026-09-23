# Pipeline (offline)

```bash
pip install -r requirements.txt
python pipeline/run_all.py            # kyoritsu math (P0)
python pipeline/run_all.py all        # all subjects (P2+)
python -m pytest tests -q
```

Steps: `inventory` -> `segment` -> `render` -> `answer_key` -> `build`.

Outputs in `pipeline/out/`:

| Path | Purpose |
|---|---|
| `exams.json` | inventory of exams and PDF paths |
| `segments/{exam}.json` | 大問/小問 regions (page, y0, y1) |
| `q/{exam}/*.png` | question crops (`q1.png` whole 大問, `q1_stem.png`, `q1-2.png` 小問) |
| `pages/{exam}/` | full pages + `answer.png` for QA |
| `preview/{exam}.html` | contact sheet for visual QA |
| `answers/{exam}.json` | slots + extracted answers + confidence |
| `bank/{exam}.json`, `bank/index.json` | PUBLIC bank (no answers) -> Firebase Hosting |
| `answers_all.json` | SECRET answer keys -> Firestore `answerKeys` |

## min-san.com offline copy (`minsan.py`)

```bash
python pipeline/minsan.py all          # scrape (throttled, resumable) -> render (node svg2png.mjs) -> build
python pipeline/build.py               # merges out/bank/minsan_*.json into index.json / answers_all.json
```

Public listing pages of みんなの算数オンライン (文章題 / 図形問題 / 計算問題, grades 4–6) and their public problem SVGs.
No login, no 解説, no answers -> every item is `answer_type: manual` (parent grades in the result view; the item's
`source` block links to the site's 解説). Exams are `minsan_{bunsho|zukei|keisan}_g{4|5|6}`, topic = site 分野,
`difficulty` = ★ count (1–6). Raw data in `out/minsan/` (items.json, svg/), PNGs in `out/q/minsan/`.
Rendering needs `@resvg/resvg-js` (web devDependency; PyMuPDF drops the SVG clip paths).

Manual fixes: `pipeline/overrides/segments/{exam}.json`, `pipeline/overrides/answers/{exam}.json`
(`{"slots": {"4-3": {"answer": [...], "parts": [...], "answer_type": "multi"}, "4-4": {"delete": true}}}`).
