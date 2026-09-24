"""min-san.com (みんなの算数オンライン) past-problem DB -> offline copy -> bank exams.

Only public listing pages and the public problem SVGs are fetched (no login, no 解説, no answers).
Throttled (one request at a time, --delay seconds between requests) and resumable: listing results are
merged into out/minsan/items.json, SVGs already on disk are skipped.

  python pipeline/minsan.py scrape [--cat db,dbz,dbk] [--delay 0.8]
  python pipeline/minsan.py render     # svgz -> out/q/minsan/{id}.png   (node pipeline/svg2png.mjs, @resvg/resvg-js from web/node_modules)
  python pipeline/minsan.py build      # -> out/bank/minsan_{year}_{NN}.json (50-min sets, grouped by year then school) + out/minsan/answers.json
  python pipeline/minsan.py all

Site layout: /mobile/{cat}/{page}/{bunya}/{grade}/   cat = db (文章題) | dbz (図形問題) | dbk (計算問題)
Entry: school+year, <p class="grade4|5|6">, ★ difficulty (of 6), comment, tag words, SVG, /mobile/kakomon/db/{id}/.
Items have no answer key -> answer_type "manual" (parent grades in the result view); the source block carries
school / year / ★ / tags / comment / link so the parent can check the 解説 on the site.
"""
from __future__ import annotations

import argparse
import html
import math
import re
import subprocess
import sys
import time
import urllib.request
from collections import Counter, defaultdict

from common import OUT, ROOT, load_json, dump_json

sys.path.insert(0, str(ROOT / "functions"))
from examcore.grading import grade as grading_grade  # noqa: E402

BASE = "https://min-san.com"
UA = "Mozilla/5.0 (exam-chuu offline practice copy; personal use)"
MS = OUT / "minsan"
SVG = MS / "svg"
PNG = OUT / "q" / "minsan"
CATS = {
    "db": {"slug": "bunsho", "label": "文章題",
           "bunya": {6: "和と差", 7: "割合と比", 8: "数の性質", 9: "速さ", 10: "規則性", 11: "場合の数", 12: "論理・推理"}},
    "dbz": {"slug": "zukei", "label": "図形問題", "bunya": {4: "平面図形", 5: "立体図形"}},
    "dbk": {"slug": "keisan", "label": "計算問題", "bunya": {1: "計算", 2: "逆算", 3: "単位換算"}},
}


def fetch(url: str, delay: float, tries: int = 4) -> bytes:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            time.sleep(delay)
            return data
        except Exception as e:  # noqa: BLE001
            wait = delay * (2 ** (i + 1)) + 2
            print(f"  retry {i + 1} {url}: {e} (sleep {wait:.0f}s)", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed: {url}")


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_list(page: str) -> list[dict]:
    m = re.search(r"<main.*?</main>", page, re.S)
    body = m.group(0) if m else page
    out = []
    for chunk in body.split('<div class="db_school_name">')[1:]:
        head, _, rest = chunk.partition("</div>")
        name = strip_tags(head)
        mm = re.match(r"(.*?)\s*(\d{4})\s*$", name)
        school, year = (mm.group(1).strip(), int(mm.group(2))) if mm else (name, None)
        kid = re.search(r"/mobile/kakomon/(db[kz]?)/([0-9a-f]+)/", rest)  # db / dbz / dbk
        if not kid:
            continue
        g = re.search(r'<p class="grade(\d)">(.*?)</p>', rest, re.S)
        stars = (g.group(2).count("★") or None) if g else None  # older entries have no ★ rating
        # newer entries: /kakomon_mobile/k_svg/..._crop1.svgz?ts ; older: /kakomon/k_svg/..._crop1.svgz
        svg = re.search(r'src="(//min-san\.com/[^"?]*?k_svg/[^"?]+)', rest)
        com = re.search(r'<section class="db_comment">(.*?)</section>', rest, re.S)
        tags = re.findall(r'class="db_tag" name="tag_word" value="([^"]+)"', rest)
        out.append({
            "id": kid.group(2), "school": school, "year": year,
            "grade": int(g.group(1)) if g else None, "stars": stars,
            "svg_url": svg.group(1) if svg else None,
            "url": f"{BASE}/mobile/kakomon/{kid.group(1)}/{kid.group(2)}/",
            "comment": strip_tags(com.group(1)) if com else "",
            "tags": [html.unescape(t) for t in tags],
        })
    return out


def max_page(page: str, cat: str, bunya: int) -> int:
    pages = [int(p) for p in re.findall(rf'/mobile/{cat}/(\d+)/{bunya}(?:/0)?/"', page)]
    return max(pages, default=1)


def scrape(cats: list[str], delay: float) -> None:
    MS.mkdir(parents=True, exist_ok=True)
    SVG.mkdir(parents=True, exist_ok=True)
    items: dict[str, dict] = load_json(MS / "items.json", {}) or {}
    for cat in cats:
        for bunya, blabel in CATS[cat]["bunya"].items():
            page, last = 1, None
            while last is None or page <= last:
                h = fetch(f"{BASE}/mobile/{cat}/{page}/{bunya}/0/", delay).decode("utf-8", "replace")
                if last is None:
                    last = max_page(h, cat, bunya)
                ents = parse_list(h)
                print(f"[{cat}/{blabel}] page {page}/{last}: {len(ents)} entries", flush=True)
                if not ents:
                    break
                for e in ents:
                    prev = items.get(e["id"])
                    if prev:
                        if blabel not in prev["topics"]:
                            prev["topics"].append(blabel)
                        for k in ("svg_url", "stars", "grade", "comment", "tags", "url"):  # fill gaps from a re-scrape
                            if not prev.get(k) and e.get(k):
                                prev[k] = e[k]
                    else:
                        e.update(cat=cat, bunya=bunya, topic=blabel, topics=[blabel])
                        items[e["id"]] = e
                page += 1
            dump_json(MS / "items.json", items)
    todo = [it for it in items.values() if it.get("svg_url") and not (SVG / f"{it['id']}.svgz").exists()]
    print(f"[svg] {len(todo)} to fetch ({len(items)} items total)", flush=True)
    for i, it in enumerate(todo, 1):
        data = fetch("https:" + it["svg_url"], delay)
        (SVG / f"{it['id']}.svgz").write_bytes(data)
        if i % 50 == 0 or i == len(todo):
            print(f"  svg {i}/{len(todo)}", flush=True)


def render(zoom: float) -> None:
    PNG.mkdir(parents=True, exist_ok=True)
    cmd = ["node", str(ROOT / "pipeline" / "svg2png.mjs"), str(SVG), str(PNG), str(zoom)]
    print("[render]", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


SET_SIZE = 20        # problems per 50-minute set (~2.5 min each; single-question items)
SET_MINUTES = 50
CAT_ORDER = {"dbk": 0, "db": 1, "dbz": 2}   # 計算 -> 文章題 -> 図形, like a real paper


def year_key(y: int | None) -> tuple[int, str]:
    """Bucket sparse years so every bucket fills at least one set. Returns (sort key, label)."""
    if not y:
        return 0, "年不明"
    if y < 2004:
        return 2003, "2003年以前"
    if 2015 <= y <= 2017:
        return 2017, "2015〜2017年"
    return y, f"{y}年"


def pack_sets(items: list[dict], size: int = SET_SIZE) -> list[list[dict]]:
    """Group one year's items into sets of <= size. A school's items stay together (first-fit-decreasing by
    school; a school with more than `size` items is split). Inside a set: by school, then 計算→文章題→図形."""
    by_school: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_school[it["school"]].append(it)
    bins: list[dict[str, list[dict]]] = []
    for name, lst in sorted(by_school.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        for chunk in [lst[i:i + size] for i in range(0, len(lst), size)]:
            for b in bins:
                if sum(len(v) for v in b.values()) + len(chunk) <= size:
                    b.setdefault(name, []).extend(chunk)
                    break
            else:
                bins.append({name: list(chunk)})
    sets = []
    for b in bins:
        its: list[dict] = []
        for name in sorted(b):
            its.extend(sorted(b[name], key=lambda x: (CAT_ORDER.get(x["cat"], 9), x["id"])))
        sets.append(its)
    sets.sort(key=lambda s: (-len(s), s[0]["school"]))
    return sets


AI_THRESHOLD = 0.8


def ai_key(it: dict, ai: dict | None) -> tuple[dict, dict]:
    """(public item fields, secret key) for one problem. AI result with confidence >= AI_THRESHOLD -> auto-graded;
    otherwise manual (parent grades) with the AI answer as a hint in `note` when one exists."""
    manual_pub = {"answer_type": "manual", "unit": "", "parts": None, "part_units": None, "note": None}
    manual_key = {"answer": None, "variants": [], "answer_type": "manual", "parts": None, "unit": "", "options": None,
                  "note": None}
    if not ai or not ai.get("ok"):
        return manual_pub, manual_key
    conf = float(ai.get("confidence") or 0)
    atype = ai.get("answer_type") or "text"
    unit = ai.get("unit") or ""
    parts = ai.get("parts") or []
    if atype == "multi" and not parts:
        atype = "text"
    if conf < AI_THRESHOLD:
        ans = ai.get("answer") or " / ".join(f"{p['label']}={p['answer']}" for p in parts)
        note = f"AI解答（確度{conf:.0%}・要確認）: {ans} {unit}".strip()
        return {**manual_pub, "note": note}, {**manual_key, "note": note}
    if atype == "multi":
        labels = [p["label"] for p in parts]
        answers = [p["answer"] for p in parts]
        pub = {"answer_type": "multi", "unit": unit, "parts": labels, "part_units": None, "note": None}
        key = {"answer": answers, "variants": [], "answer_type": "multi", "parts": labels, "unit": unit,
               "options": None, "note": None}
    else:
        pub = {"answer_type": atype, "unit": unit, "parts": None, "part_units": None, "note": None}
        key = {"answer": ai.get("answer"), "variants": list(ai.get("variants") or []), "answer_type": atype,
               "parts": None, "unit": unit, "options": None, "note": None}
    # Self-check: an AI answer the grader itself would mark wrong (bad decimal notation, embedded unit,
    # malformed ratio/set/sequence...) must not ship as an auto-grader -> fall back to manual with a hint.
    # A bad *variant* (e.g. a "0.0166..." alongside a fine "1/60") is just dropped, not the whole item.
    try:
        ok = grading_grade(key, key["answer"]).correct
    except Exception:  # noqa: BLE001 - any parse failure is itself a "doesn't self-grade"
        ok = False
    if ok and key.get("variants"):
        good_variants = []
        for v in key["variants"]:
            try:
                if grading_grade(key, v).correct:
                    good_variants.append(v)
            except Exception:  # noqa: BLE001
                pass
        key["variants"] = good_variants
    if not ok:
        ans = ai.get("answer") or " / ".join(f"{p['label']}={p['answer']}" for p in parts)
        note = f"AI解答（自己採点チェック失敗・要確認）: {ans} {unit}".strip()
        return {**manual_pub, "note": note}, {**manual_key, "note": note}
    return pub, key


def build() -> None:
    items: dict[str, dict] = load_json(MS / "items.json", {}) or {}
    ai_results: dict[str, dict] = load_json(MS / "ai" / "results.json", {}) or {}
    usable = [it for it in items.values() if it.get("grade") and (PNG / f"{it['id']}.png").exists()]
    skipped = len(items) - len(usable)
    for f in (OUT / "bank").glob("minsan_*.json"):   # regrouping changes exam ids -> drop stale sets
        f.unlink()
    groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for it in usable:
        groups[year_key(it["year"])].append(it)
    answers: dict[str, dict] = {}
    n_sets = 0
    for (ykey, ylabel), lst in sorted(groups.items(), reverse=True):
        for k, src in enumerate(pack_sets(lst), 1):
            eid = f"minsan_{ykey}_{k:02d}"
            bigs, its = [], []
            for i, it in enumerate(src, 1):
                iid = f"{eid}#{it['id']}"
                img = f"q/minsan/{it['id']}.png"
                pub_fields, key = ai_key(it, ai_results.get(it["id"]))
                its.append({
                    "id": iid, "exam_id": eid, "big": i, "sub": 0, "path": [], "label": "",
                    "image": img, "stem_images": [], "stem_image": None, "shared_image": False,
                    "unit": pub_fields["unit"], "parts": pub_fields["parts"], "part_units": pub_fields["part_units"],
                    "frame": None, "width": None,
                    "answer_type": pub_fields["answer_type"], "options": None, "work_required": False, "points": 1,
                    "grade": it["grade"], "topic": it["topic"], "difficulty": it["stars"], "note": pub_fields["note"],
                    "source": {"site": "みんなの算数オンライン", "school": it["school"], "year": it["year"],
                               "category": CATS[it["cat"]]["label"], "stars": it["stars"], "tags": it["tags"],
                               "topics": it.get("topics", [it["topic"]]), "comment": it["comment"], "url": it["url"]},
                })
                bigs.append({"no": i, "image": img, "stem_image": None, "sub_count": 0, "items": [iid],
                             "grade": it["grade"], "topic": it["topic"]})
                answers[iid] = key
            schools = list(dict.fromkeys(it["school"] for it in src))
            pub = {
                "id": eid, "school": "minsan", "school_name": "みんなの算数オンライン",
                "year": ykey, "year_label": ylabel, "session": f"{k:02d}", "session_label": f"第{k}回",
                "subject": "math", "subject_label": "算数",
                "title": f"{ylabel} 第{k}回", "schools": schools,
                "time_limit_min": SET_MINUTES if len(its) >= 16 else max(10, math.ceil(len(its) * 2.5 / 5) * 5),
                "bigs": bigs, "items": its, "item_count": len(its),
                "grade_counts": dict(Counter(str(i["grade"]) for i in its)),
                "manual_count": sum(1 for i in its if i["answer_type"] in ("manual", "essay")),
            }
            dump_json(OUT / "bank" / f"{eid}.json", pub)
            n_sets += 1
        print(f"[minsan] {ylabel}: {len(lst)} items -> {k} sets", flush=True)
    dump_json(MS / "answers.json", answers)
    print(f"[minsan] {len(answers)} items in {n_sets} sets ({SET_MINUTES} min, <= {SET_SIZE} problems), "
          f"skipped {skipped} (no grade / no png) -> run python pipeline/build.py to refresh index / answers_all", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scrape", "render", "build", "all"])
    ap.add_argument("--cat", default="db,dbz,dbk")
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--zoom", type=float, default=2.5)
    a = ap.parse_args()
    cats = [c for c in a.cat.split(",") if c in CATS]
    if a.cmd in ("scrape", "all"):
        scrape(cats, a.delay)
    if a.cmd in ("render", "all"):
        render(a.zoom)
    if a.cmd in ("build", "all"):
        build()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
