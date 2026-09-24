# exam-chuu — 中学受験 過去問練習アプリ

Past-paper practice app: questions cropped from PDF → web answer sheet → auto-grading → email report to parent.
Plan and status: `docs/PLAN.md`.

```
pipeline/   offline PDF → question crops + bank json + answer keys   (python pipeline/run_all.py)
functions/  Firebase Cloud Functions (Python): grade_attempt + email; examcore/ grading lib
web/        Vite SPA (vanilla JS) → Firebase Hosting
scripts/    sync_assets, import_bank (Firestore), set_admin, dev_server (local mock backend)
tests/      pytest (grading + grader + report)
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

Mock mode: no login, attempts stored in the browser, grading + email HTML produced by `dev_server.py`
(result page has a "メールプレビュー" link).

## 2. Firebase setup (once)

Prereqs: Firebase project on **Blaze** plan (Functions + Extensions), Gmail account with an **app password**.

```bash
npm i -g firebase-tools && firebase login
# edit .firebaserc -> your project id
firebase use REPLACE_WITH_FIREBASE_PROJECT_ID

# Console: Authentication > Sign-in method > enable Google
# Console: Project settings > Your apps > Add web app -> copy config into web/.env.local (see web/env.example)
cp functions/env.example functions/.env          # PARENT_EMAIL, APP_URL=https://<project>.web.app

# email extension (SMTP via Gmail app password) — already declared in firebase.json ("extensions" block),
# its params live in extensions/firestore-send-email.env. No ext:install needed:
#   1. edit extensions/firestore-send-email.env: replace REPLACE_SENDER with the sending Gmail address
#   2. deploy the extension; the CLI prompts for the secret SMTP_PASSWORD (Gmail app password, Secret Manager)
firebase deploy --only extensions
#   later changes: edit the .env then re-run the same command (or `firebase ext:configure firestore-send-email`)
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

Two things `deploy.sh` doesn't do, both one-time/rare:

```bash
# extension change (edited extensions/firestore-send-email.env, or first setup):
firebase deploy --only extensions

# after a new parent signs in once with Google (use that Google account's email):
gcloud auth application-default login   # needed once for import_bank.py / set_admin.py (Admin SDK)
python scripts/set_admin.py <parent-google-email> --project REPLACE_WITH_FIREBASE_PROJECT_ID
# (both scripts set GOOGLE_CLOUD_QUOTA_PROJECT=<project> for gcloud user credentials; a service-account key via
#  GOOGLE_APPLICATION_CREDENTIALS works too)
```

Result emails go to `students/{uid}.parentEmail` if set (admin edits in console), else `PARENT_EMAIL`.

## 4. Data flow

```
web (Hosting)  --Auth--> students/{uid}/attempts/{aid}  {status: in_progress -> submitted}
                                   │ Firestore trigger
                          functions.grade_attempt  --reads--> answerKeys/{examId}, exams/{examId}
                                   ├─ update attempt {status: graded, result}
                                   └─ add mail/{id} {to, message{subject, html}}  --> extension --> SMTP
```

Answer keys are never readable from the client (`firestore.rules`); the bank json on Hosting has no answers.

## 5. 学年フィルタ (小5 / 全問)

Each question is tagged with `grade` (5 = 小5までの内容で解ける, 6 = 小6内容が必要) and `topic` in `pipeline/tags/`.
Home screen toggle 「小5までの問題」 opens `#/exam/{id}?g=5`: only 小5 items, shorter time limit, graded on that subset.
Result and email show 分野別 correctness so weak topics stand out. Edit tags, then `python pipeline/build.py && python scripts/sync_assets.py`.

## 6. Subjects and answer types

38 exams are processed: all 24 kyoritsu exams (2024–2026 × 2-1/2-2 × 算数・理科・社会・国語) and 14 shinagawa
exams (2018 + 2026 × 第1回/第2回 × 算数・理科・社会, plus 算数1教科). The home page has a school filter
(すべて / 共立女子 / 品川女子学院). Question types:

| answer_type | input | grading |
|---|---|---|
| number / fraction / ratio | text | exact rational, 全角/単位/帯分数 tolerant |
| choice | radio (正・誤) or text (ア, A) | normalized equality |
| set | text `A・D` | order-free |
| sequence | text `C→B→A` | order matters |
| text | text | normalized equality + variants (別解, 読み) |
| multi | one input per part (AD/BC, Ⅰ/Ⅱ, はじめ/終わり) | all parts |
| essay / manual | textarea | **pending** — parent marks ○/× on the result page (admin claim), Cloud Function regrades |

国語 shows each 大問 as page images (no per-問 crops yet); answers are entered per 問 in the sheet order.

**Shinagawa (品川女子学院)**: only 2018 and 2026 include 問題 PDFs (other years are blank answer sheets, no 国語 at all).
The 模範解答 are scanned handwriting, so `pipeline/answer_key_tree.py` derives one slot per leaf of the question tree
and the answers are transcribed by hand into `pipeline/overrides/answers/shinagawa_*.json` (drawings → `manual`).
社会・理科 share one PDF (`page_range` in `out/exams.json` selects the pages); 理科 大問1 has Ⅰ/Ⅱ sections
(`1-Ⅰ-2-1` style ids).

## 7. Dashboard, weak-topic practice, weekly digest (P3)

- Every graded attempt updates `students/{uid}/topicStats/summary` (topic mastery = recency-weighted accuracy,
  weak = mastery < 60% after 3+ outcomes). The dashboard (`#/dashboard`) shows weekly accuracy, weak topics,
  per-subject tables and topics not yet practised.
- 練習 (`#/practice/{subject}?weak=1|topic=...&g=5`) builds a set across all exams: wrong-before first, then
  unseen, then previously-correct; the attempt stores the item ids and is graded against several answer keys.
- Sunday 20:00 JST the `weekly_digest` function mails a per-subject report with suggested practice links.
