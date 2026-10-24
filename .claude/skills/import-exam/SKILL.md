---
name: import-exam
description: 新しい過去問・テスト(共立 kyoritsu_past/<年度>、品川、栄東、中大附属、四谷大塚 組分け など)の PDF をアプリに取り込むときの手順。「この年度の過去問をアプリに載せて」「新しい組分けを追加」「〇〇_past/2023年度 を取り込んで」と言われたとき、inventory → segments → 解答キー → 解き方(explanation) → tags → build → 確認 → デプロイまでを通しで行う。解き方だけ後から足す・公式解答がない試験のキーを作るときもここ。スキャン PDF(テキスト層なし)の手動切り出しもここ。
---

# 過去問セットの取り込み

ゴール: 元 PDF のフォルダ 1 つ(例 `kyoritsu_past/2023年度`)を、問題ごとの画像+解答欄+採点キー+分野タグ付きの試験としてアプリに出す。
元 PDF・切り出し画像は git 管理外(著作権)。**コミットするのは pipeline のコード・`pipeline/overrides/`・`pipeline/tags/`・`pipeline/out/{exams.json,segments,answers}` だけ**。

パイプライン: `inventory → segment → render → kaisetsu → seitouritsu → qtext → answer_key(_generic/_tree) → build`
(`python pipeline/run_all.py`、全試験を作り直すので 10 分以上かかる → バックグラウンド実行)。

## 1. 素材を調べる(先にユーザーへ報告)

```bash
python -c "import fitz,glob; [print(f, len(d:=fitz.open(f)), d[0].rect, d[0].rotation, len(d[0].get_text())) for f in sorted(glob.glob('<folder>/*.pdf'))]"
```
ページを PNG にしてスクラッチパッドで目視する(表紙・問題・解答)。確認すること:

| 項目 | 見るところ | 影響 |
|---|---|---|
| 学校・年度・回(2/1 か 2/2、第1回…) | 問題の表紙 | exam id `{school}_{year}_{session}_{subject}` |
| 教科のそろい | ファイル一覧 | 欠けた教科(例: 2023 共立は国語なし)はユーザーに伝える |
| テキスト層 | `get_text()` が空 = スキャン | 空なら自動切り出し不可 → § 3B |
| 判型 | `rect` / `rotation` | 横長 1032×728 = 見開き 2 ページ(左右に分けて切る) |
| 模範解答 | テキスト層ありか / 手書きスキャンか | 自動抽出 or 手入力 |
| 解答用紙 | 別 PDF / 問題 PDF の最終ページ / なし | 解答欄(slot)の並び・単位・「計算式」欄 |
| 子どもの答案・成績 | 組分けの `回答.pdf`・`結果.pdf` | **読み取り・出荷禁止**(slot 配置の確認だけ。`結果.pdf` の解説・正答率一覧の扱いは README / memory 参照) |

公式の解答がありそうなのに見つからないときは、自分で解かずに**どこにあるかユーザーに聞く**(見つからないと言われたら § 5「公式の解答がない試験」)。

## 2. inventory(`pipeline/inventory.py`)

- 既存スキャナ(`scan_kyoritsu` / `scan_shinagawa` / `scan_kumiwake`)のファイル名規則に合うか確認。合わなければ規則を足す
  (例: 2023 共立の `sansu-mondai.pdf` / `sansu-kaito.pdf` → `RE_KYO_ROMAJI` + 回は表紙から読んで `KYO_ROMAJI_SESSION`)。
  中央 2024–25 も同じ命名 → `scan_chuo` が `RE_KYO_ROMAJI` + `CHUO_ROMAJI_SESSION` で拾う。新しい年度は回を表紙で確認して辞書に足す。
- 1 試験 1 エージェントで取り込める(中央 2024–25 の 7 試験を並列: segments・answers・explanations・tags を各自が新規作成、
  コード・exams.json・pipeline/out は触らせない)。その後こちらで inventory → 対象試験だけ segment/render → answer_key_generic → build。
- 元 PDF は必ず学校ごとのフォルダ `{school}_past/{year}年度/` に置く(git 管理外。新しい学校なら `.gitignore` に `{school}_past/` を足す)。
  `pipeline/in/` のような共通の置き場は使わない。新しい学校は `scan_{school}()` を書いて `SCANNERS` に登録する(`exams.json` を手で編集しない)。
- 実行前に `pipeline/out/exams.json` をスクラッチパッドにバックアップ。実行後 `git diff pipeline/out/exams.json` で**追加だけ**であることを確認。

## 3. 切り出し(segments)

### 3A. テキスト層あり(ベクター PDF)
`segment.py` が 大問/小問 マーカーから自動で切る。結果は `pipeline/out/preview/{exam}.html` で目視。
ずれは `pipeline/overrides/segments/{exam}.json` の **部分パッチ** `{"bigs": {"3": {...}}}` で直す(学校ごとの癖は `SUBJECT_RULES`)。

### 3B. スキャン(テキスト層なし)
`pipeline/overrides/segments/{exam}.json` に **全体置き換えのリスト** `{"bigs": [...]}` を書く(segment.py がそのまま採用)。

1. `python pipeline/scan_bands.py <問題.pdf> [page ...]` で行ごとのインク帯(pt)を出す。見開きは L/R 半分ずつ。
2. 帯と画像を突き合わせて、大問の `stem`(リード文・共通の図)と小問の `regions` を決める。
   - 座標は**表示上の pt**(`rotation=90` のページでも `page.rect` 基準 = `get_pixmap(clip=)` と同じ)。
   - 見開きの片側は `x0`/`x1` で指定(2023 共立: L = 50–472, R = 570–986)。
   - ルビ(ふりがな)があると前の行と帯がつながる → 行の位置(画像 px ÷ 描画倍率)から行間の中央で切る。
   - 薄い灰色の図(時計の円など)は帯に出ないことがある → 図のある stem は余裕を持たせる。
   - 解答用紙のページ(問題 PDF の最終ページなど)は切らない。
3. ノード形: `{"no","key","label","rank","regions":[{page,x0,x1,y0,y1}],"stem":<region|list|null>,"subs":[...]}`。
   入れ子(問1 の (1)(2))は sub に `stem` + `subs`。穴埋め(あ〜き)のように小問マーカーのない大問は `subs: []`(slot が大問画像を共有)。
4. 座標は手で JSON を打たず、スクラッチパッドの生成スクリプト(region ヘルパー)で書き出すと直しやすい。
5. render 後、`pipeline/out/q/{exam}/*.png` を**全部目視**(行の切れ・前後の問題の混入・図の欠け)。直して `segment`+`render` を再実行。

## 4. 解答キー(slots)

- **解答用紙 PDF + テキスト層の模範解答** → 自動(`answer_key.py` 算数 / `answer_key_generic.py` 理社国)。`needs review` の slot を `overrides/answers/{exam}.json` の部分パッチ `{"slots": {"4-3": {...}}}` で直す。
- **解答用紙 PDF がない / 模範解答がスキャン** → `overrides/answers/{exam}.json` に**全 slot のリスト** `{"slots": [...]}` を書く(`answer_key_generic.manual_slots`。共立算数でも `sheet` がなければこちらに回る)。

slot の id は `大問-小問[-枝]`、セグメントの key の並びと一致させる(build.py が画像を対応付ける)。並びと単位は解答用紙に合わせる。

| 解答の形 | 書き方 |
|---|---|
| 数・分数(約分済み・帯分数・小数どれでも可) | `number` / `fraction`、`variants: ["62 4/5", "314/5"]`、`unit: "cm2"` |
| 比 | `ratio` `"3:2"` |
| 記号 1 つ / 複数(順不同)/ 順番 | `choice` / `set` `["ア","イ","エ"]` / `sequence` `"イ→ア→ウ"` |
| 語句 | `text` + `variants`(表記ゆれ・「〜県」付き等)|
| 欄が複数(ことば+記号、A/B/C、時間+分) | `multi`、`parts` = 欄の見出し、`answer` = 同順のリスト、`"赤血球\|ヘモグロビン"` = 別解 |
| 前後に固定文字のある欄(`7時□分`、`憲法の□`、`西暦□年□月□日`) | `multi`、`parts: ["7時__分"]`、`part_units: ["分"]` |
| 記述 / 作図・グラフ | `essay`(模範解答を `answer` に)/ `manual`(`note` に模範の説明)→ 保護者が ○/× |
| 「計算式も書く」欄 | `"work_required": true` |

配点が公表されていなければ `points` は省略(1 点扱い)。

## 5. 解き方(explanation)

採点後の結果画面で問題ごとに「解き方を見る」(全幅の折りたたみ行)として出る。保護者の「問題と答え」プレビューにも出る。
**新しい試験を入れたら解き方まで作るのが標準**(共立・品川・中央は全問あり)。組分けは公式の解説画像(`kaisetsu.py`)、
みんなの算数はサイトの解説リンクがあるので対象外。

### 置き場所とデータの流れ

| 試験の種類 | 置き場所 |
|---|---|
| 公式キーあり(共立・品川・栄東 2025 など) | `pipeline/explanations/{exam_id}.json` = `{"exam_id": "...", "explanations": {"1-1": "…", ...}}`。**キー本体(overrides/answers)は触らない** |
| キーを自作(中央 2026 など) | `overrides/answers/{exam_id}.json` の各 slot に `"explanation"` と `"unofficial": true` |

`build.py` が secret 側(`answers_all.json` → Firestore `answerKeys`)にだけ入れる → `functions/grader.py` が採点結果の
`perItem[sid].explanation` / `.unofficial` にコピー → `web/src/views/result.js` の `howto()` が表示(`unofficial` なら
「AI作成・非公式」バッジ)。公開 bank(`web/public/bank`)には入らないので、**提出前には見えない**。

### 文面のルール(小5–6 向け、日本語)

- 3〜10 行、`\n` 区切り、プレーンテキスト(LaTeX・Markdown なし。分数は 3/4、× ÷ は可)。
- 1 行目に考え方(「速さの比で考えます。」)→ 途中の計算 → 最終行「答え …」(単位つき、**公式の答えと一致**)。
- 選択肢: 正解の理由 + 紛らわしい選択肢がなぜ違うか。知識問題: 事実 + 覚え方。国語: 決め手になる本文の語句を示す。
- 記述(essay): 満点に必要な要素を並べてから模範解答。作図(manual)・公式の答えがない slot: 自分の解答で「答え(例) …」。

### 作り方(エージェントに分担)

1. 1 エージェントあたり 1〜3 試験(同じ年度・教科の 2/1・2/2 をまとめる)。並列は 1 波 15 前後まで。
2. 指示書(下のテンプレート)をスクラッチパッドに置き、各エージェントには exam_id と出力先だけ渡す。
3. 出力は `{"exam_id", "explanations": {...}, "disagree": [{"id","official","mine","why"}]}`。
   **公式の答えに到達できない slot は解き方を書かずに `disagree` に入れさせる**(作り話の解き方を防ぐ)。
4. 戻ってきたら:
   - 全 slot id が `explanations` にあるか(欠け・余分なし)をスクリプトで確認して `pipeline/explanations/` に書く。
   - `disagree` は**自分で確かめる**(算数は Python で全数チェック、図・答案スキャン `pages/{exam}/answer.png` や
     `answer_scan` を見る)。キーの抽出ミスか学校の誤りかを切り分ける。
   - 報告に出てくる「キーの note がおかしい」「別解・模範解答が欠けている」も同様に確認して直す。

キーの直し方(実例):
- 学校の模範解答の誤り(共立 2025 2-2 算数 か・け は 1 通り数え漏れ): `overrides/answers` の部分パッチで
  `answer` = 正しい値、`variants` = 学校の値、`note` に理由 →どちらでも ○。
- 抽出ミス(共立 2024 2-2 社会「34字」が variants に混入、共立 2026 2-1 国語 5-4 の読点位置): 部分パッチで修正。
- 手書きスキャンの転記ミス(品川 2018 r1 理科 2-9/2-10 の月の形が左右逆): スキャンを見て `note` を修正。

### 公式の解答がない試験

**ユーザーが「探したが見つからない、作って」と言ったときだけ**自分たちで解く(勝手に解かない。まず場所を聞く)。
- 1 試験 1 エージェントで答え+解き方を作る。算数・理科は**別エージェントに答えだけ独立に解かせて突き合わせる**。
- 食い違いは図・本文を自分で見て決める(中央 2026 2回 理科 2-5 は 図5 を読んで ウ・カ に決定)。
- slot に `"unofficial": true`、`ai_confidence`(high/medium/low)を残し、medium/low はユーザーに一覧で報告。
- overrides に入れる前に、全 slot がキー通りの入力で正解になるか `examcore.grading.grade` で自己採点する
  (multi の `"a|b"` は最初の候補で試す。①〜④ の選択肢は 1 / ① / １ どれでも通る)。

### エージェント用テンプレート(公式キーあり)

```
Repo: C:/Users/HienCT/workspace/exam-chuu. Read-only: write only <OUT_DIR>/<exam_id>.json.
Official key (ground truth): pipeline/out/answers/<exam_id>.json (slots: id, label, unit, parts, answer_type, answer, variants, note).
Question PDF: pipeline/out/exams.json -> files.question (+ page_range). Text: python -I -c "import fitz,sys;
sys.stdout.reconfigure(encoding='utf-8'); d=fitz.open(sys.argv[1]); [print('=== page',i,'\n',p.get_text()) for i,p in enumerate(d)]"
"<pdf>" > <scratch>.txt, then Read the txt (-I ignores PYTHONIOENCODING). Scans have no text.
Images: pipeline/out/q/<exam_id>/q{大問}-{小問}.png, q{n}_stem.png, pipeline/out/pages/<exam_id>/p*.png (国語 = 縦書き pages).
Output: {"exam_id", "explanations": {slot_id: text}, "disagree": [{"id","official","mine","why"}]} covering every slot id.
Text: Japanese for a 小5–6 child, 3–10 lines joined with "\n", key idea -> steps -> last line 「答え …」 = official answer.
Verify 算数・理科 calculations with Python (Fraction / enumeration). If you cannot reach the official answer, do not
invent an explanation: put the slot in disagree. Slots with no official answer: own solution, last line 「答え(例) …」.
Final message: per exam count + every disagree entry.
```

確認: `python pipeline/build.py` 後に `answers_all.json` で学校ごとの `explanation` 件数、公開 bank に `explanation` が
含まれないこと、`/start` で 1 試験提出して「解き方を見る」が出ることを見る。

## 6. 分野タグ(`pipeline/tags/{exam}.json`)

`{"bigs": {"1": {"grade": 5, "topic": "..."}}, "items": {"2-1": {"topic": "...", "grade": 6}}}`
- `topic` は**既存ラベルを優先**(`pipeline/bunya_map.py` にあるもの)。新ラベルを使うなら同じファイルの対応表に足す
  (`tests/test_bunya_map.py` が未対応ラベルで落ちる)。
- `grade`: 5 = 小5までの内容で解ける、6 = 小6 内容が必要(算数: 比・相似・速さと比 → 6。理科: 天体・回路・気体計算 → 6。社会: 地理 → 5、歴史・公民・時事 → 6)。
  国語: ことわざ・慣用句を問う問題(漢字の書き取りでも、ことわざの一部なら)→ **6**、topic `ことわざ` / `慣用句`(子どもがまだ習っていない — 2026-10 の生徒フィードバック)。四字熟語の読みは漢字のまま。

## 7. ビルドと確認

```bash
python pipeline/run_all.py            # バックグラウンドで。スキャン分だけなら segment/render/answer_key_generic/build を個別に呼んでもよい
git status --short && git diff --stat # 既存試験の segments/answers/exams.json が変わっていないこと
python -m pytest tests -q             # 全解答キーの自己採点(キー通りに答えて満点になるか)を含む
python scripts/sync_assets.py
```
- `pipeline/out/bank/{exam}.json` で items 数・`manual_count`・画像パス、`pipeline/out/preview/{exam}.html` で切り出しを確認。
- 画面で確認するなら `/start`(mock サーバー + Vite)→ 新しい試験を開いて問題画像と解答欄を見る → `/stop`。
- README の試験数・学校ごとの説明(§ 6)を更新。新しい学校ならホームの学校フィルタ(`web/`)も。

## 8. 出す

- `/deploy`(`scripts/deploy.sh`: pytest → sync → build → firebase deploy → `import_bank.py` で Firestore に exams / answerKeys)。本番反映なので**ユーザーの承認を得てから**。
- コミットはユーザーに頼まれたら。メッセージ例: `feat: 共立女子 2023年度 2/1入試 (算数・理科・社会, scanned)` + 本文に slot 数・手入力した理由・推測した箇所。

## 報告に入れること

試験 id と教科ごとの slot 数 / 記述・作図(保護者採点)の数 / 解き方の件数と disagree の扱い / 欠けている教科・資料 / 推測で決めた箇所(回の判定、解答欄の区切り、分野・学年タグ)/ テストとデプロイの結果。
