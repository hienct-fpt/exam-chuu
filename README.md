# exam-chuu — 中学受験 過去問練習アプリ

Past-paper practice app: questions cropped from PDF → web answer sheet → auto-grading → dashboard for the parent.

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
The mock user テスト生徒 has the parent (admin) view by default; `npm run dev:mock:student` (`VITE_MOCK_ADMIN=0`)
runs it as a plain student. Both share the same localStorage attempts. The topbar button 「生徒ビューへ / 保護者ビューへ」
switches the role at runtime (kept in localStorage `exam-chuu.mockRole`, which then wins over `VITE_MOCK_ADMIN`).

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
The 保護者 page (`#/parent`, nav link shown only with the admin claim) lists the pending 採点待ち attempts of the
parent's **linked** children, a per-child summary (教科別 accuracy, weak topics), and `#/parent/<uid>` with the
full attempt history; results open as `#/result/<attemptId>?uid=<childUid>` so the ○/× writes go to the child's doc.

Linking a child: the parent creates an invite code on `#/parent` (single-use, 24h, `invites/{code}`); the child
signs in with their own Google account and enters it on `#/join` (or opens the copied `#/join/<code>` link). The
`redeem_invite` callable writes `students/{child}.parents` + `students/{parent}.children`; `unlink_child` removes
the link. Clients can't write those fields, and `firestore.rules` lets a parent read / grade linked children only.

A child without a Google account opens the invite link signed out and creates a **ログインID + パスワード** account
(`create_child_account` callable: Auth user `<id>@kids.exam-chuu.invalid`, linked in the same step, only with a valid
code). They then log in with that ID on the login screen; the parent can set a new password from `#/parent/<uid>`
(`reset_child_password`). Requires **Authentication → Sign-in method → Email/Password** enabled in the Firebase console.

## 5. 学年フィルタ (小5 / 全問)

Each question is tagged with `grade` (5 = 小5までの内容で解ける, 6 = 小6内容が必要) and `topic` in `pipeline/tags/`.
Home screen toggle 「小5までの問題」 opens `#/exam/{id}?g=5`: only 小5 items, shorter time limit, graded on that subset.
The result page shows 分野別 correctness so weak topics stand out. Edit tags, then `python pipeline/build.py && python scripts/sync_assets.py`.

**取るべき問題** (`#/toru`, child; `#/toru/?uid=<child>` read-only for the parent): 組分け questions that ≥ N % of all
test-takers got right (N = 40/50/60/70, default 50) but whose latest answer was wrong or blank — the points that cost the
most 偏差値 — with one practice set per 教科. The 正答率 per question comes from the 正答率一覧 (`seitouritsu.py` keeps
`points` / `rates` per row in `functions/kumiwake_population.json`, still read left of the 結果 column only); `build.py`
puts it on each 組分け item as `rate` when the rows line up with the answer slots (same count, same 配点).

**偏差値シミュレーター** (parent's child page): `hensachi_report` also exports each target 回's model (max per 教科, pass
line, sigmaC) and the child's level per 教科, and `kumiwake_report` the max / SD per 教科 — `web/src/simulator.js` recomputes
the same estimate in the browser: "+N点 in this 教科" -> 推定偏差値 / 合格可能性, points to the 80% line, and per 組分け
round the 偏差値 per point. The 取るべき問題 page shows what getting that list right would have done to the latest round.
(Production summaries get the new fields on the child's next graded attempt.)

**まちがいの原因**: on the result page every wrong / blank answer has a cause picker (ケアレスミス / 知らなかった / 時間切れ /
むずかしすぎ) -> `attempt.mistakes.{sid}`. `firestore.rules` lets the student change only `mistakes` (+`updatedAt`) on a
graded attempt and a linked parent `manualGrades` / `mistakes`; the grading trigger ignores it (regrades on manualGrades
only). The parent's child page counts causes per 教科 (`web/src/mistakes.js`) with advice for the biggest one.

**今週の課題 weighted by the gap**: `goals.weekly_assignments(..., gaps=subject_gaps(goals["subjects"]))` — the やり直し
time is split per 教科 ∝ (target − level + 0.02) (`pick_review`: each 教科 within its share, leftover to the biggest
gap); new exams keep the queue order of the sets but within one set the biggest gap goes first (`gap_order`). The
assignments carry `gaps` / `reviewShares`, shown as 「やり直しの時間の配分」 under 今週の課題. No level yet -> no weighting.

## 6. Subjects and answer types

**解き方 (worked explanations)**: every 共立・品川・中央 question has one (1,588 total). Source: `pipeline/explanations/{exam_id}.json`
(`{"explanations": {slot_id: text}}`, for exams with an official key — the key files stay untouched) or an `explanation` field
on the slot in `overrides/answers` (中央, whose keys we made ourselves, `unofficial: true`). `build.py` puts it in the secret
answer key only; the grader copies it into the result, so it appears under 「解き方を見る」 after submitting (and in the
parent's 問題と答え preview). 組分け uses the official 解説 images instead, みんなの算数 links to the site's 解説.

95 exams are processed: 27 kyoritsu (2024–2026 × 2-1/2-2 × 算数・理科・社会・国語, plus 2023 2-1 × 算数・理科・社会 —
scanned spreads, crops in `overrides/segments`, keys transcribed into `overrides/answers`; no 国語 in the source), 23 shinagawa
(2018 + 2023–2026 × 第1回/第2回 × 算数・理科・社会, plus 算数1教科), 15 chuo (2026 × 1回/2回 × 算数・理科・社会・国語; 2024 第1回 × 4 subjects and 2025 第1回 × 算数・理科・社会 —
scanned, crops/keys in overrides, official 解答 except 2024 国語 which is AI-made `unofficial`),
6 sakaehigashi (2025–2026 × 算数・理科・社会) and 24 kumiwake
(四谷大塚 公開組分けテスト 5年 第1〜6回 × 4 subjects), plus the min-san.com offline copy (§ below). The home page has
a school filter (すべて / 共立女子 / 品川女子学院中等部 / 栄東中学校 / 中央大学附属 / 四谷大塚 組分け /
みんなの算数). Question types:

| answer_type | input | grading |
|---|---|---|
| number / fraction / ratio | text | exact rational, 全角/単位/帯分数 tolerant |
| choice | radio (正・誤) or text (ア, A) | normalized equality |
| set | text `A・D` | order-free |
| sequence | text `C→B→A` | order matters |
| text | text | normalized equality + variants (別解, 読み) |
| multi | one input per part (AD/BC, Ⅰ/Ⅱ, はじめ/終わり) | all parts; a part `ア・ウ` is order-free, `a\|b` = alternatives |
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
No official 解答 could be found, so all 8 keys were solved by us (AI, 算数・理科 cross-checked by an independent
second solve) and carry `"unofficial": true` + an `explanation` (解き方) per slot — the result page shows them after
grading with an 「AI作成・非公式」 badge; only the 記述 stay parent-graded; grade/topic
were tagged per item by reading each question, not defaulted from the 大問 (see § 5 rubric: 地理→5, 歴史/公民/時事→6
for 社会; base-curriculum 生物・地層 → 5 vs 回路・波・気体計算・天体 → 6 for 理科).

**Source folders**: every school keeps its PDFs in its own git-ignored `{school}_past/` folder, one sub-folder per
year, and `pipeline/inventory.py` rebuilds `out/exams.json` from the file names (`scan_kyoritsu`, `scan_shinagawa`,
`scan_kumiwake`, `scan_chuo`, `scan_sakaehigashi`): `chuo_past/2026年度/`, `sakaehigashi_past/{2025,2026}年度/`,
`shinagawa_past/{2023,2024,2025}年度_入試問題解答/` (the scanned `品川女子学院_{year}年…` files). The scanned exams
(chuo 社会, sakaehigashi, shinagawa 2023–25, kyoritsu 2023) keep their crops and answer keys as full lists in
`overrides/segments/{exam_id}.json` (`"bigs": [...]`) and `overrides/answers/{exam_id}.json` (`"slots": [...]`);
`answer_key_generic.py` / `answer_key_tree.py` copy such a list to `out/answers/`, so editing the override +
`python pipeline/run_all.py` (or `answer_key_generic.py <exam_id>` + `build.py`) is enough.

**Kumiwake (四谷大塚 公開組分けテスト, 5年 2026 第1〜6回)**: `kumiwake_past/` (git-ignored) is scanned by
`inventory.scan_kumiwake()` into `kumiwake_2026_r{1-6}_{subject}` (第6回 came without 回答 sheets). The `…回答.pdf` files are **the child's own scored
answer sheets** (handwriting, ○/✓, name), not 模範解答: they are kept as `files.scored_sheet` and never shipped or
read as keys. The question PDFs have a text layer: 算数's ⑴⑵ are glyphs of an `Fx-*` font whose text is unrelated
kanji (唄欝蔚鰻姥厩浦瓜 → ⑴…⑻, remapped in `SUBJECT_RULES["kumiwake_math"]`), 理科 uses 問１ + (1), 社会 問１; the
`2026－組①－５－算－2` footers are noise; ruby above a question's first line needs `pad_top`; a 大問 whose figure sits
beside several sub questions gets `whole: true` and is shown as one image (`build.py`). 国語 is two tiers per page
(上段/下段) and several 大問 can share a tier, so `japanese.segment_tiers()` cuts tier strips in reading order. Slots
come from the question tree (`answer_key_tree.py`), split per answer box as laid out on the scored sheets.
The keys were transcribed from each round's `…結果.pdf` (`files.result`: 解答と解説 on pp. 2–8, then the 教科別正答率一覧表,
whose rows match the slots one to one): `overrides/answers/kumiwake_*.json` holds answer / answer_type / variants and
`points` = 配点 (200/150/100 per exam), `pipeline/tags/kumiwake_*.json` grade 5 + topic = the table's 領域. Only the
国語 記述 are `manual` (model answer + note). The 結果.pdf also has the child's own scores — not used. Symbols printed
as circled hiragana (○い) are stored as ㋑ etc.; the grader folds single kana so a typed い matches (`norm_word`).

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

## 8. 今週の目標 (weekly goals toward the 2028 入試)

- Target schools live in `functions/schools.json` (`plan`: 第一志望 kyoritsu, 第二志望 shinagawa, exam_year 2028,
  margin +5%), with per-round 入試 day, 満点 / 合格者平均 / 受験者平均 per subject and the 合格ライン (sent by the
  parent). Final target per subject = the higher of the two schools: 合格者平均 rate, else 合格ライン rate + margin,
  else 受験者平均 rate + margin (共立 publishes only that); nothing known -> provisional 70% (shown as 仮).
- `functions/goals.py` (pure, tested in `tests/test_goals.py`) sets each subject's weekly goal from the results
  **before** the week (Monday 00:00 JST): accuracy climbs from the current level (last 4 weeks of items + latest
  whole-exam / 組分け scores, the parent's official 組分け score superseding the app's) to the final target so that
  it is reached 8 weeks before the exam; volume = 4-week median (+10% after a missed week); focus 分野 =
  (1 − mastery) × frequency in the target schools' past papers.
- The Cloud Function freezes the goals once per week in `students/{uid}/weeklyGoals/{weekStart}` (first grading of
  the week, or the Monday 00:05 JST `weekly_goals` schedule) and adds them with the week's live progress to
  `topicStats/summary.goals`. Official 組分け scores: `students/{uid}/kumiwakeScores/{round}`
  `{date, scores: {math: {score, max}, ...}}` (Admin SDK only for now).
- 今週の課題 (`goals.weekly_assignments`): `plan.weekly_minutes` (180) of work per week, frozen with the goals.
  やり直し (up to `review_share` of the time) = items still wrong / blank in an exam last touched 6+ days ago,
  lowest accuracy first, opened via `#/redo/{examId}` (a practice set with `redoOf`). New exams fill the rest in
  queue order: 組分け rounds -> 共立 / 品川 interleaved by year, oldest first -> `extra_schools` (栄東, 中央);
  each target school's latest year is held back until `reserve_from` (直前期). Until `grade6_from` exams are
  assigned with the 小5 filter; from 6年 a filtered-only attempt counts as not done. Time = 制限時間 scaled to the
  assigned items; a week may run 10% over. Unfinished work stays at the head of next week's queue.
  過去問集中 (`plan.focus`, Jul–Nov 2027): spare time after the new exams goes to whole school papers again
  (kind `retake`, 2回目, timed, no 小5 filter) — 第一/第二志望 first, then extra schools, last done 8+ weeks ago,
  longest ago / lowest score first; 組分け and the reserved latest year are never retaken. Projected in 全体計画 too.
  Once every 課題 of the week is done, next week's list is made (and frozen, `createdAt` = now) so the child
  can work ahead; work done early counts toward it, and on Monday the week keeps that list.
- 全体計画 (`goals.roadmap` / `goals.history` -> `topicStats/summary.plan`, `web/src/views/plan.js`, `#/plan` and
  the parent's child page): past weeks' 課題 assigned vs done (やり残し listed), then a week-by-week projection of
  the new-exam queue to the exam at `weekly_minutes x (1 - review_share)` per week assuming each week is done
  (frozen weeks as is; 小5-filtered exams with 6年 items come back at 6年), with the milestones (6年, 直前期,
  target deadline, 入試 days). Recomputed after every grading.
  Material added later is projected too (`schools.json` `upcoming`, shown as 予定, no link): a 組分け round every
  month (sized like the latest real round; dropped once the real round's month is in the bank) and each school's
  next 入試 papers from their `available` date — which then become the reserved latest year.
- 保護者 (admin) accounts don't take tests: the student pages (`web/src/roles.js`) redirect to `#/parent`; the
  overview shows each child's 今週の課題 progress, the child page the full goal card (no links).
- UI: `web/src/views/goals.js` card on the dashboard and on the parent's child page.
