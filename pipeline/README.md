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

Manual fixes: `pipeline/overrides/segments/{exam}.json`, `pipeline/overrides/answers/{exam}.json`
(`{"slots": {"4-3": {"answer": [...], "parts": [...], "answer_type": "multi"}, "4-4": {"delete": true}}}`).
