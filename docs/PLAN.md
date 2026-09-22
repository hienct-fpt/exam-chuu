# Exam Practice App — Implementation Plan

Target: 中学受験 past papers (共立女子 = kyoritsu, 品川女子学院 = shinagawa) → per-question web practice,
auto-grading, email report to parent, topic-level weakness analysis.

## 0. Source data audit (done 2026-09-22)

| Source | Years | Contents | Status |
|---|---|---|---|
| kyoritsu_past | 2024–2026, 2 sessions (2-1, 2-2) × 4 subjects | 問題 / 模範解答 / 解答用紙, all vector PDF, text extractable | **Full use — 24 exams** |
| shinagawa_past 2018, 2026 | 第1回/第2回/算数1教科/表現力総合型 | 問題 (算数, 社会理科 only; **no 国語 問題**), 解答 = **scanned image** (2026 has garbage OCR layer) | Use 算数/理科/社会; answer key needs vision/manual |
| shinagawa_past 2015–2017, 2019–2025 | all | **解答用紙 only** (blank answer sheets, no questions, no answers) | Not usable for practice |

Extraction facts:
- Page size 516×729pt (B5). 大問 marker = digit, font 12.8pt, x≈60. 小問 marker = ①②/⑴⑵, font 9.9pt, x≈79.
- Math text extraction breaks fractions / brackets / figures → **render each question as a cropped PNG from PDF** (PyMuPDF, 2–3× zoom). Text kept only for search + topic tagging. This gives "same as PDF" fidelity.
- Kyoritsu 模範解答 = 解答用紙 with answers overlaid; text order scrambled → recover mapping by (x,y) position vs. blank sheet cells, then human verify.
- Tools available: Python 3.11, PyMuPDF 1.26, pdfplumber, pypdf, Node 22. No tesseract.

## 1. Architecture

```
pipeline/  (Python, run offline once per exam)
  01_inventory.py      scan folders -> exams.json (school, year, session, subject, paths)
  02_segment.py        detect 大問/小問 bboxes per page -> questions.json (+ manual overrides.json)
  03_render.py         crop -> public/q/{exam_id}/{q_id}.png (+ full page PNGs for context)
  04_answer_key.py     模範解答 -> answers.json (coordinate match; scanned -> Claude vision draft)
  05_tag_topics.py     Claude API auto-tag topic/subtopic/difficulty -> topics.json (review in admin)
  06_build.py          merge -> data/bank.json (single source of truth for web app)

server/  (SUPERSEDED by Firebase — see §6; logic below moves into functions/)
  api: exams, questions, attempts, results, analytics
  grading.py           per answer_type normalizers + compare
  analytics.py         topic mastery, weakness ranking, practice-set generator
  mailer.py            SMTP (Gmail app password) / Resend -> HTML report
  admin: fix bbox, fix answer, fix topic, manual-grade 記述

web/  (static SPA, vanilla JS or React+Vite)
  Exam mode            full paper, timer (45 min), sheet-like answer inputs
  Practice mode        by topic / by weakness / wrong-again
  Result view          correct/wrong, model answer overlay, per-大問 score
  Dashboard            topic radar, trend, recommended practice
```

Data model (SQLite):
- `exam(id, school, year, session, subject, time_limit, pdf_paths)`
- `question(id, exam_id, big_no, small_no, page, bbox, image_path, text, answer_type, answer_json, points, topic_id, subtopic, difficulty)`
- `attempt(id, student_id, exam_id|null, mode, started_at, submitted_at)`
- `response(attempt_id, question_id, raw_answer, normalized, is_correct|null, graded_by[auto|manual], time_sec)`
- `topic(id, subject, name, parent_id)`

## 2. Function plan by module

### 2.1 Pipeline
| Fn | Input → Output | Notes |
|---|---|---|
| `inventory(root)` | folder tree → list[Exam] | parse filenames `2-1入試_算数_問題.pdf`, `第１回_算数問題.pdf`; normalize 全角 digits |
| `detect_big_questions(page)` | spans size≥12 & x<70 & isdigit → [(no, y)] | kyoritsu pattern; shinagawa variants → per-school rule table |
| `detect_small_questions(page, big_range)` | ①②③ / ⑴⑵⑸ / (1)(2) at x≈79 → [(no, y)] | 国語 問一/問二 = vertical text, right-to-left columns → x-based split |
| `build_bboxes(markers, page_h)` | marker y-list → bbox per question (y_i .. y_{i+1}), full width | cross-page continuation; padding; overrides.json wins |
| `render_crop(pdf, page, bbox, zoom=2.5)` | → PNG | also render 大問 header (shared 問題文 / 図) as separate "stem" image |
| `extract_answer_key(model_pdf, blank_pdf)` | diff text spans by position → {q_id: answer} | confidence score; low → flag for review |
| `vision_answer_key(image)` | scanned 解答 → draft JSON | Claude API, always human-reviewed |
| `auto_tag(question_text, image)` | → {topic, subtopic, difficulty 1–5, answer_type} | Claude API, batched, cached |
| `build_bank()` | merge all → bank.json | validate: every question has answer + topic |

### 2.2 Grading (`grading.py`)
| answer_type | normalize | compare |
|---|---|---|
| `number` | 全角→半角, strip units (cm, g, 点, 秒後), commas, spaces | float eq, tolerance 1e-6 |
| `fraction` | accept `3/4`, `０.７５`, 帯分数 `1 1/4` | reduce → compare rational |
| `ratio` | `2：3` / `2:3` / `2 : 3` | reduce both sides |
| `choice` | ア/イ/ウ/エ, A–D, 全角 | set equality (multi-select order-free) |
| `text` | NFKC kana normalize, strip 、。 | exact or allowlist of variants |
| `multi` | ordered parts (AD=?, BC=?) | per-part grading, partial points |
| `essay` (記述) | — | `is_correct=null`, manual grade via admin / email link; optional LLM rubric hint |

### 2.3 Analytics (`analytics.py`)
- `topic_stats(student)` → per topic: attempts, correct, accuracy, last_seen, avg_time
- `mastery(topic)` = exponentially-weighted accuracy (recent attempts weigh more); need ≥3 attempts for "confident"
- `weak_topics(student, k=3)` → lowest confident mastery; tie-break by topic frequency in past papers
- `practice_set(student, topic, n=10)` → priority: wrong before > never seen > correct long ago; mix difficulty
- `trend(student, subject)` → weekly accuracy series

### 2.4 Email (`mailer.py`)
- Trigger: attempt submit (exam mode) + weekly digest (cron)
- Body: score / 満点, per-大問 table, wrong list (question thumbnail + student answer + model answer), topic radar (inline SVG), pending 記述 count + grade link
- Provider: Gmail SMTP app password (`SMTP_USER/SMTP_PASS`, recipient `hienct@fpt.com`). Fallback: Resend API.

### 2.5 Web UI
- Exam mode: left = question crop (zoom/pan), right = inputs mirroring 解答用紙 cells; timer; autosave localStorage; submit → grade → result.
- Result: green/red per cell, model-answer toggle, "retry wrong only".
- Practice mode: pick topic or "weak topics" auto; 10-question sets; instant feedback.
- Dashboard: radar per subject, mastery bars, trend line, recommended next set.
- Admin (parent): bbox editor (drag on page image), answer-key editor, topic override, manual grading queue.

## 3. Topic taxonomy (initial; refine after auto-tag)
- 算数: 計算 / 単位・割合・食塩水 / 速さ・旅人算 / 数の性質・倍数約数 / 規則性・数列 / 場合の数 / 平面図形-角度 / 平面図形-面積・相似 / 立体図形-体積・表面積 / 文章題-和差・つるかめ・仕事算 / グラフ・水量変化 / 論理・推理
- 理科: 物理(力・てこ・電気・光音) / 化学(水溶液・気体・燃焼) / 生物(植物・動物・人体) / 地学(天体・気象・地層) / 実験考察
- 社会: 地理(日本・世界・産業・地図) / 歴史(古代〜近現代) / 公民(憲法・政治・経済・国際) / 時事 / 資料読み取り
- 国語: 漢字・語彙 / 文法・敬語 / 説明文読解 / 物語文読解 / 記述 / 詩・短歌

## 4. Phases

| Phase | Deliverable | Scope |
|---|---|---|
| **P0 – Pipeline (kyoritsu 算数 only)** | bank.json + crops for 6 算数 exams, verified answer keys | prove segmentation + answer-key matching; overrides tooling |
| **P1 – MVP web** | Exam mode + auto grade + result page + SQLite; email on submit | single student, PIN only |
| **P2 – All kyoritsu subjects** | 理科/社会/国語 segmentation (vertical text), essay manual grading, admin UI | 24 exams |
| **P3 – Topics & analytics** | auto-tag + review, dashboard, weak-topic practice sets, weekly digest | |
| **P4 – Shinagawa** | 2018 + 2026 算数/理科/社会; vision-drafted answer keys | 国語 impossible (no 問題 PDF) |

## 5. Open decisions (defaults chosen; change if needed)
1. Hosting: **Firebase** (Hosting + Firestore + Functions + Auth). Decided 2026-09-22, see §6.
2. Email: Firebase extension `firestore-send-email` over Gmail SMTP app password. Need a sending account.
3. 記述 grading: manual by parent via link in email. LLM suggestion later.
4. Stack: Python pipeline + Python Cloud Functions (shared `examcore/` grading package) + vanilla JS (Vite) SPA.
5. Shinagawa 2015–2025: skip (no 問題 files). Confirm whether another source exists.

## 6. Firebase deployment (replaces FastAPI + SQLite)

Decision: keep Python **pipeline** offline (unchanged). Replace `server/` with Firebase services.

| Need | Firebase service | Notes |
|---|---|---|
| Static SPA + question PNG crops + exam metadata JSON | **Hosting** | `web/dist` + `public/q/**.png` + `public/bank/{exam_id}.json` (questions WITHOUT answers). 10 GB free; crops ~150 MB |
| Answer keys, attempts, responses, topic stats | **Firestore** | answer keys readable only by Functions (rules deny client) |
| Grading + analytics on submit | **Cloud Functions 2nd gen (Python 3.11)** | reuse `grading.py` / `analytics.py` from pipeline; `on_document_created(attempts/{id})` |
| Email to parent | **Extension: Trigger Email from Firestore** (`firebase/firestore-send-email`) | function writes doc to `mail/`; extension sends via Gmail SMTP app password. Zero mail code |
| Weekly digest | **Functions `scheduler_fn.on_schedule`** | Cloud Scheduler, e.g. `every sunday 20:00` Asia/Tokyo |
| Login | **Auth** (Google sign-in) | parent UID → custom claim `admin: true`; student = other account |
| Admin edits (bbox / answer / topic / manual grade) | SPA admin pages + Firestore writes gated by `admin` claim | |

Requires **Blaze plan** (Functions + Extensions). Cost at family scale ≈ ¥0 (free quotas cover it).

### Firestore schema
```text
exams/{examId}                    {school, year, session, subject, timeLimit, questionCount}
answerKeys/{examId}               {qId: {type, answer, points, variants[]}}   ← no client read
topics/{topicId}                  {subject, name, parent}
questionMeta/{examId}             {qId: {topicId, difficulty}}   (also in bank json; Firestore copy for overrides)
students/{uid}                    {name, parentEmail, role}
students/{uid}/attempts/{aId}     {examId|null, mode, startedAt, submittedAt, answers:{qId: raw}, status}
students/{uid}/attempts/{aId}/result  {score, max, perBig:{}, perQ:{qId:{ok, normalized, correct}}, pendingEssay:[]}
students/{uid}/topicStats/{topicId}   {attempts, correct, mastery, lastSeen}
mail/{autoId}                     {to, message:{subject, html}}   ← extension consumes
```

### Function list (Python, `functions/main.py`)
- `grade_attempt` — trigger `on_document_updated(students/{uid}/attempts/{aId})` when `status == "submitted"` → load answerKey → grade → write `result` → update `topicStats` → write `mail/` doc.
- `manual_grade` — `https_fn.on_call`, admin only: set essay result, recompute score, re-mail if requested.
- `weekly_digest` — `scheduler_fn.on_schedule("every sunday 20:00", timezone="Asia/Tokyo")` → per student topic radar + weak topics → `mail/`.
- `practice_set` — `on_call`: returns question ids for weak topic (reads topicStats + questionMeta, no answers).
- `import_bank` — admin `on_call` or CLI script with Admin SDK: upload `answers.json` → `answerKeys/`, `topics.json` → `questionMeta/`.

### Security rules (sketch)
```text
match /answerKeys/{doc}      { allow read, write: if false; }              // functions only (Admin SDK bypasses)
match /students/{uid}/{doc=**} { allow read, write: if request.auth.uid == uid || isAdmin(); }
match /exams/{d}, /topics/{d}, /questionMeta/{d} { allow read: if request.auth != null; allow write: if isAdmin(); }
match /mail/{d}              { allow read, write: if false; }
function isAdmin() { return request.auth.token.admin == true; }
```

### Repo layout
```text
exam-chuu/
  pipeline/            Python, offline → out/bank/*.json, out/q/**.png, out/answers.json
  web/                 Vite SPA → dist/
  functions/           Python Cloud Functions (imports pipeline/grading.py via shared package `examcore/`)
  firebase.json        hosting.public = web/dist ; rewrites SPA ; functions runtime python311
  firestore.rules
  .firebaserc
```

### Deploy steps
```bash
npm i -g firebase-tools
firebase login
firebase init hosting firestore functions   # functions: Python
firebase ext:install firebase/firestore-send-email   # SMTP: smtps://user@gmail.com:APP_PASSWORD@smtp.gmail.com:465, collection: mail
python pipeline/06_build.py && cp -r pipeline/out/q web/public/q && cp -r pipeline/out/bank web/public/bank
python scripts/import_bank.py            # Admin SDK → answerKeys, questionMeta, exams
cd web && npm run build && cd ..
firebase deploy --only hosting,firestore:rules,functions
```

### Phase impact
- P1 MVP = Hosting + Auth + Firestore + `grade_attempt` + email extension.
- P3 analytics = `topicStats` maintained by `grade_attempt`; dashboard reads it directly (no extra function).
- Zero-billing fallback (Spark plan): grade client-side with answers in bank json (student can peek), email via EmailJS from browser. Not recommended.

## 7. P0 status (2026-09-22) — DONE

Delivered:
- `pipeline/` inventory -> segment -> render -> answer_key -> build (`run_all.py`), README inside.
- 6 kyoritsu 算数 exams: 36 大問, 134 answer slots, 162 PNG crops (7 MB), `out/bank/*.json` (public) + `out/answers_all.json` (secret).
- All 134 answers verified by eye against 模範解答 images. 26 needed manual overrides (`pipeline/overrides/answers/`).
- `examcore/grading.py` (number / fraction / ratio / text / multi, variants, 全角, units, mixed numbers) + 18 tests green.

Learnings that change P2+:
- 模範解答 layouts differ by year (2024/25 inline text, 2026 Calibri values). Heuristic extraction gets ~80%; human review pass is mandatory, overrides tooling works.
- 大問 without ①② use あ〜く fill-in slots; some ③ contain あ〜え sub-slots -> modeled as `multi` with `parts`.
- Crop trimming must ignore page-sized drawing rects (frame/background) or bottom extends to page end.
- Next: P1 web MVP (Firebase Hosting + Auth + Firestore + `grade_attempt` function + email extension) using `bank/*.json` and `answers_all.json`.

## 8. P1 status (2026-09-22) — BUILT, NOT YET DEPLOYED

Delivered (deploy-ready, see README.md):
- `firebase.json`, `.firebaserc`, `firestore.rules` (answerKeys/mail client-inaccessible; students own their attempts; in_progress -> submitted only), `firestore.indexes.json`, `extensions/firestore-send-email.env`.
- `functions/` Python 2nd-gen: `grade_attempt` Firestore trigger (students/{uid}/attempts/{aid} status=submitted -> grade -> write result -> queue `mail/` doc). Pure `grader.py` + `report.py` (HTML email with per-大問 table, all items, wrong-question crops, app link). `examcore/` moved here.
- `web/` Vite vanilla-JS SPA: Google login, exam list with best score, exam mode (crops + 解答用紙-like inputs, parts for AD/BC etc., timer, debounced autosave, resume in-progress), result view (score, per-大問, per-item ○×, expected + variants, thumbnails, wrong-only filter), history. Backend facade with Firebase impl + mock impl (localStorage + `scripts/dev_server.py`).
- `scripts/`: `sync_assets.py`, `import_bank.py` (exams + answerKeys to Firestore), `set_admin.py`, `dev_server.py`.
- Tests: pytest 21 (grading, grader, report) + vitest 3 (home / exam->submit->result / history in jsdom). `npm run build` OK (467 kB firebase chunk).

Verified locally end-to-end in mock mode: Vite proxy -> dev_server -> grader -> result + email HTML (`pipeline/out/preview/email_sample.html`).

Blocked on user (cannot be done from this machine):
1. Create Firebase project, Blaze plan, enable Google sign-in, add web app -> fill `web/.env.local`, `.firebaserc`, `functions/.env`.
2. Gmail app password for `firestore-send-email` (SMTP_PASSWORD secret).
3. Run: `firebase deploy`, `python scripts/import_bank.py`, `python scripts/set_admin.py <parent email>`.
Notes: Java 8 on this PC -> Firebase emulators unavailable (need Java 11+). Points are 1 per item (no 配点 in PDFs).
