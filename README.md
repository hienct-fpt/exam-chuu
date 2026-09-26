# exam-chuu — 中学受験 過去問練習アプリ

Past-paper practice app: questions cropped from PDF → web answer sheet → auto-grading → dashboard for the parent.
Plan and status: `docs/PLAN.md`.

```
pipeline/   offline PDF → question crops + bank json + answer keys   (python pipeline/run_all.py)
functions/  Firebase Cloud Functions (Python): grade_attempt; examcore/ grading lib
web/        Vite SPA (vanilla JS) → Firebase Hosting
scripts/    sync_assets, import_bank (Firestore), set_admin, dev_server (local mock backend)
tests/      pytest (grading + grader)
```

## 1. Local development (no Firebase needed)

```bash
pip install -r requirements.txt
python pipeline/run_all.py              # builds pipeline/out (crops, bank, answers)
python pipeline/minsan.py all && python pipeline/build.py   # optional: min-san.com offline copy (grade 4–6 pool, manual grading)
python scripts/sync_assets.py           # -> web/public/bank, web/public/q
python -m pytest tests -q

python scripts/dev_server.py            # mock grader on :8790 (uses functions/ code)
cd web && npm install && npm run dev:mock   # http://localhost:5173  (VITE_MOCK=1: localStorage attempts)
```

Mock mode: no login, attempts stored in the browser, grading result computed by `dev_server.py`.

## 2. Firebase setup (once)

Prereqs: Firebase project on **Blaze** plan (Functions).

```bash
npm i -g firebase-tools && firebase login
# edit .firebaserc -> your project id
firebase use REPLACE_WITH_FIREBASE_PROJECT_ID

# Console: Authentication > Sign-in method > enable Google
# Console: Project settings > Your apps > Add web app -> copy config into web/.env.local (see web/env.example)
```

## 3. Deploy

```bash
# the Firebase CLI analyzes functions/main.py locally with functions/venv (Python 3.11) — create it once:
py -3.11 -m venv functions/venv && functions/venv/Scripts/pip install -r functions/requirements.txt   # Windows
# python3.11 -m venv functions/venv && functions/venv/bin/pip install -r functions/requirements.txt    # mac/linux

scripts/deploy.sh          # sync pipeline output -> build web -> firestore/functions/hosting -> import data
# scripts/deploy.sh --full    # also regenerate pipeline output first (pipeline/run_all.py; slow, needs source PDFs)
# scripts/deploy.sh --minsan  # also refresh the min-san bank first (pipeline/minsan.py build + pipeline/build.py)
# scripts/deploy.sh --help    # all options (--skip-import, --skip-tests, --project)
```

One thing `deploy.sh` doesn't do, one-time/rare:

```bash
# after a new parent signs in once with Google (use that Google account's email):
gcloud auth application-default login   # needed once for import_bank.py / set_admin.py (Admin SDK)
python scripts/set_admin.py <parent-google-email> --project REPLACE_WITH_FIREBASE_PROJECT_ID
# (both scripts set GOOGLE_CLOUD_QUOTA_PROJECT=<project> for gcloud user credentials; a service-account key via
#  GOOGLE_APPLICATION_CREDENTIALS works too)
```

## 4. Data flow

```
web (Hosting)  --Auth--> students/{uid}/attempts/{aid}  {status: in_progress -> submitted}
                                   │ Firestore trigger
                          functions.grade_attempt  --reads--> answerKeys/{examId}, exams/{examId}
                                   └─ update attempt {status: graded, result}, students/{uid}/topicStats
```

Answer keys are never readable from the client (`firestore.rules`); the bank json on Hosting has no answers.
The parent reviews results and marks 記述/作図 items ○/× directly on the result page (admin claim) — no email.

## 5. 学年フィルタ (小5 / 全問)

Each question is tagged with `grade` (5 = 小5までの内容で解ける, 6 = 小6内容が必要) and `topic` in `pipeline/tags/`.
Home screen toggle 「小5までの問題」 opens `#/exam/{id}?g=5`: only 小5 items, shorter time limit, graded on that subset.
The result page shows 分野別 correctness so weak topics stand out. Edit tags, then `python pipeline/build.py && python scripts/sync_assets.py`.

## 6. Subjects and answer types

61 school exams are processed: 24 kyoritsu (2024–2026 × 2-1/2-2 × 算数・理科・社会・国語), 23 shinagawa
(2018 + 2023–2026 × 第1回/第2回 × 算数・理科・社会, plus 算数1教科), 8 chuo (2026 × 1回/2回 × 算数・理科・社会・国語)
and 6 sakaehigashi (2025–2026 × 算数・理科・社会), plus the min-san.com offline copy (§ below). The home page has
a school filter (すべて / 共立女子 / 品川女子学院中等部 / 栄東中学校 / 中央大学附属 / みんなの算数). Question types:

| answer_type | input | grading |
|---|---|---|
| number / fraction / ratio | text | exact rational, 全角/単位/帯分数 tolerant |
| choice | radio (正・誤) or text (ア, A) | normalized equality |
| set | text `A・D` | order-free |
| sequence | text `C→B→A` | order matters |
| text | text | normalized equality + variants (別解, 読み) |
| multi | one input per part (AD/BC, Ⅰ/Ⅱ, はじめ/終わり) | all parts |
| essay / manual | textarea | **pending** — parent marks ○/× on the result page (admin claim), Cloud Function regrades |

国語 (kyoritsu, chuo) shows each 大問 as page images (no per-問 crops — `japanese.py` splits by page only, no
marker tree); answers are entered per 問 in the sheet order. Because every item in a page-only 大問 resolves to
the same crop (the last page), `web/src/views/exam.js`'s shared-image render path still draws the earlier pages
(`stem_image` / `stem_images`) first — without that, a multi-page 大問's passage/earlier-question pages never
render (fixed 2026-09; if a 国語 exam looks like it's missing pages, check that path first before the data).

**Shinagawa (品川女子学院)**: only 2018 and 2026 include 問題 PDFs (other years are blank answer sheets, no 国語 at all).
The 模範解答 are scanned handwriting, so `pipeline/answer_key_tree.py` derives one slot per leaf of the question tree
and the answers are transcribed by hand into `pipeline/overrides/answers/shinagawa_*.json` (drawings → `manual`).
社会・理科 share one PDF (`page_range` in `out/exams.json` selects the pages); 理科 大問1 has Ⅰ/Ⅱ sections
(`1-Ⅰ-2-1` style ids).

**Chuo (中央大学附属)**: 算数・理科・社会 have real per-問 crops via `SUBJECT_RULES["chuo_math"/"chuo_science"/"chuo_social"]`
in `segment.py` (chuo's 大問 box-digit sits further right than kyoritsu's, and `（１）`-style markers split across
3 spans/fonts — both handled there without touching kyoritsu's thresholds). 国語 stays page-only, same as kyoritsu.
社会's answers are AI-read descriptions (`answer_type: manual`, no scanned 解答用紙), not auto-extracted; grade/topic
were tagged per item by reading each question, not defaulted from the 大問 (see § 5 rubric: 地理→5, 歴史/公民/時事→6
for 社会; base-curriculum 生物・地層 → 5 vs 回路・波・気体計算・天体 → 6 for 理科).

**Known gap**: chuo and sakaehigashi are NOT in `pipeline/inventory.py` (`inventory.main()` only scans
`schools=("kyoritsu", "shinagawa")` and **overwrites** `out/exams.json`) — their `out/exams.json` entries,
`overrides/answers/`, `overrides/segments/` and `tags/` files were added by hand in an earlier session, not by
a reproducible scan step. Running `python pipeline/run_all.py` wipes them from the index. `out/answers/chuo_*.json`
is also hand-authored, not generated by `answer_key_generic.py` (chuo has no scanned 解答用紙/模範解答 for it to read —
that script just prints "missing sheet/answer, skip" for every chuo exam and leaves `out/answers` untouched); after
editing an `overrides/answers/chuo_*.json`, copy the same slots into `out/answers/{exam_id}.json` by hand, then
`python pipeline/build.py`. Add a `scan_chuo`/`scan_sakaehigashi` to `inventory.py` to make this reproducible.

**Sakaehigashi (栄東中学校)**: all 6 PDFs (算数・理科・社会 × 2025/2026) are scanned images with **no text layer**,
so the font/position marker detection above can't run — every 大問 still falls back to one shared image per big
question (`shared_image: true` for every item). Per-問 segmentation there needs OCR or a vision-model pass over
each page (similar to how `answer_key_ai.py` already reads scanned 模範解答 for other exams); not done yet.

## 7. Dashboard, weak-topic practice (P3)

- Every graded attempt updates `students/{uid}/topicStats/summary` (topic mastery = recency-weighted accuracy,
  weak = mastery < 60% after 3+ outcomes). The dashboard (`#/dashboard`) shows weekly accuracy, weak topics,
  per-subject tables and topics not yet practised.
- 練習 (`#/practice/{subject}?weak=1|topic=...&g=5`) builds a set across all exams: wrong-before first, then
  unseen, then previously-correct; the attempt stores the item ids and is graded against several answer keys.
