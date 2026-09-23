"""AI answer keys for the min-san.com problems (no key exists on the site) via the Claude Message Batches API.

  python pipeline/answer_key_ai.py submit [--model claude-sonnet-5] [--limit N] [--only-missing]
      -> one batch per <=400 problems; ids saved to out/minsan/ai/batches.json
  python pipeline/answer_key_ai.py fetch        # poll until every batch ended -> out/minsan/ai/results.json
  python pipeline/answer_key_ai.py report       # stats + out/minsan/ai/review.md (low-confidence / unsolvable list)
  python pipeline/answer_key_ai.py estimate     # token count of one request x N, rough $ before submitting

Then `python pipeline/minsan.py build && python pipeline/build.py` applies the keys: confidence >= THRESHOLD ->
auto-graded item (number / fraction / ratio / text / choice / set / sequence / multi), below -> stays `manual`
(parent grades) with the AI answer shown as a hint. Secret keys never enter the public bank.

Credentials: ANTHROPIC_API_KEY in the environment, else read from functions/.env or .env (git-ignored).
Cost (Sonnet 5, batch = 50% off): ~1.5k input + ~2-4k output tokens per problem -> ~$0.01-0.02 each.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from collections import Counter

from common import OUT, ROOT, load_json, dump_json

MS = OUT / "minsan"
AI = MS / "ai"
PNG = OUT / "q" / "minsan"
THRESHOLD = 0.8
BATCH_SIZE = 400
PRICE = {"claude-sonnet-5": (2.0, 10.0), "claude-opus-5": (5.0, 25.0), "claude-fable-5-1": (10.0, 50.0),
         "claude-haiku-4-5": (1.0, 5.0)}  # $/M input, output (standard; batch = half)

SYSTEM = """あなたは中学受験算数の模範解答作成者です。画像の問題を解き、最終的な答えだけを指定のJSONで返します。

手順: 問題文と図を正確に読み取る → 解く → 別の方法または逆算で検算する → 答えを確定する。
図の数値・条件は画像から読み取れるものだけを使い、推測で補わないこと。

出力ルール:
- answer_type
  number   : 整数・小数・分数の1つの数値。分数は a/b（帯分数は仮分数 7/4 に直す。約分済み）。小数はそのまま。
  ratio    : 比。最簡整数比 "2:3" / "2:3:5"。
  choice   : 選択肢を1つ選ぶ問題。記号のみ（"ア", "3"）。
  set      : 複数選ぶ・順不同。"ア・ウ" のように「・」区切り。
  sequence : 順番を答える。"A→C→B" のように「→」区切り。
  text     : 語句・時刻・曜日など（"午後3時20分" は "3:20" と "午後3時20分" を variants に）。
  multi    : 答えが複数ある問題（(1)(2)、①②、空欄が2つ以上、AとBの値など）。parts に順番どおり並べ、各 answer は上のルールで書く。answer は "" にする。
  essay    : 説明・理由・作図・求め方を書かせる問題、または画像が読めない・情報不足で解けない場合。solvable=false。
- answer / parts[].answer: 半角数字。単位は含めない（unit に分ける。multi は各 part に単位を含めず、共通単位を unit に）。
- unit: "cm", "cm2", "km", "個", "円", "分", "度" など。無ければ ""。
- variants: 同じ答えの別表記（"0.75" ⇄ "3/4"、"1.5" ⇄ "3/2" など）。無ければ []。
- confidence: 0〜1。図から長さや角度を読み取る必要がある、計算が長い、条件が曖昧、問題が途中で切れている → 低くする。
- check: 検算の要点を60字以内で。"""

SCHEMA = {
    "type": "object",
    "properties": {
        "solvable": {"type": "boolean"},
        "answer_type": {"type": "string",
                        "enum": ["number", "fraction", "ratio", "choice", "set", "sequence", "text", "multi", "essay"]},
        "answer": {"type": "string"},
        "parts": {"type": "array", "items": {
            "type": "object",
            "properties": {"label": {"type": "string"}, "answer": {"type": "string"}},
            "required": ["label", "answer"], "additionalProperties": False}},
        "unit": {"type": "string"},
        "variants": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "check": {"type": "string"},
    },
    "required": ["solvable", "answer_type", "answer", "parts", "unit", "variants", "confidence", "check"],
    "additionalProperties": False,
}


def api_key() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    for p in (ROOT / "functions" / ".env", ROOT / ".env"):
        if p.exists():
            m = re.search(r"^\s*ANTHROPIC_API_KEY\s*=\s*['\"]?([^'\"\s]+)", p.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1)
    return None


def client():
    import anthropic
    key = api_key()
    if not key:
        sys.exit("ANTHROPIC_API_KEY not set (env, functions/.env or .env)")
    return anthropic.Anthropic(api_key=key)


def problems(only_missing: bool) -> list[dict]:
    items = load_json(MS / "items.json", {}) or {}
    done = load_json(AI / "results.json", {}) or {}
    out = []
    for it in items.values():
        if not (PNG / f"{it['id']}.png").exists():
            continue
        if only_missing and done.get(it["id"], {}).get("ok"):
            continue
        out.append(it)
    return sorted(out, key=lambda x: x["id"])


def request_params(it: dict, model: str) -> dict:
    img = base64.standard_b64encode((PNG / f"{it['id']}.png").read_bytes()).decode("ascii")
    meta = f"出典: {it.get('school', '')} {it.get('year', '')}　分野: {it.get('topic', '')}　タグ: {'・'.join(it.get('tags') or [])}"
    return {
        "model": model,
        "max_tokens": 16000,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
            {"type": "text", "text": f"{meta}\nこの問題を解いて、指定のJSONだけを返してください。"},
        ]}],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }


def submit(model: str, limit: int | None, only_missing: bool) -> None:
    from anthropic.types.messages.batch_create_params import Request
    c = client()
    todo = problems(only_missing)[: limit or None]
    if not todo:
        print("[ai] nothing to submit")
        return
    AI.mkdir(parents=True, exist_ok=True)
    state = load_json(AI / "batches.json", {"batches": []}) or {"batches": []}
    for i in range(0, len(todo), BATCH_SIZE):
        chunk = todo[i:i + BATCH_SIZE]
        reqs = [Request(custom_id=it["id"], params=request_params(it, model)) for it in chunk]
        b = c.messages.batches.create(requests=reqs)
        state["batches"].append({"id": b.id, "model": model, "n": len(chunk), "status": b.processing_status,
                                 "created": time.strftime("%Y-%m-%dT%H:%M:%S")})
        dump_json(AI / "batches.json", state)
        print(f"[ai] batch {b.id}: {len(chunk)} requests ({b.processing_status})", flush=True)
    print(f"[ai] submitted {len(todo)} problems in {(len(todo) + BATCH_SIZE - 1) // BATCH_SIZE} batches -> fetch later")


def parse_result(msg) -> dict:
    text = next((b.text for b in msg.content if b.type == "text"), "")
    d = json.loads(text)
    d["ok"] = bool(d.get("solvable")) and d.get("answer_type") != "essay"
    d["usage"] = {"in": msg.usage.input_tokens, "out": msg.usage.output_tokens,
                  "cache_read": getattr(msg.usage, "cache_read_input_tokens", 0) or 0}
    d["stop_reason"] = msg.stop_reason
    return d


def fetch(wait: bool) -> None:
    c = client()
    state = load_json(AI / "batches.json", {"batches": []}) or {"batches": []}
    results = load_json(AI / "results.json", {}) or {}
    pending = [b for b in state["batches"] if b.get("status") != "fetched"]
    if not pending:
        print("[ai] all batches already fetched")
        return
    while pending:
        for b in list(pending):
            info = c.messages.batches.retrieve(b["id"])
            b["status"] = info.processing_status
            rc = info.request_counts
            print(f"[ai] {b['id']}: {info.processing_status} ok={rc.succeeded} err={rc.errored} "
                  f"processing={rc.processing}", flush=True)
            if info.processing_status != "ended":
                continue
            n_ok = n_err = 0
            for r in c.messages.batches.results(b["id"]):
                if r.result.type == "succeeded":
                    try:
                        results[r.custom_id] = {**parse_result(r.result.message), "model": b["model"]}
                        n_ok += 1
                    except Exception as e:  # noqa: BLE001 - malformed JSON / refusal
                        results[r.custom_id] = {"ok": False, "error": f"parse: {e}", "model": b["model"]}
                        n_err += 1
                else:
                    err = getattr(r.result, "error", None)
                    results[r.custom_id] = {"ok": False, "error": f"{r.result.type}: {getattr(err, 'type', '')}",
                                            "model": b["model"]}
                    n_err += 1
            b["status"] = "fetched"
            pending.remove(b)
            dump_json(AI / "results.json", results)
            dump_json(AI / "batches.json", state)
            print(f"[ai] {b['id']}: stored {n_ok} answers, {n_err} failures", flush=True)
        if pending and wait:
            time.sleep(60)
        elif pending:
            print(f"[ai] {len(pending)} batch(es) still processing; re-run fetch (or use --wait)")
            break
    report()


def report() -> None:
    results = load_json(AI / "results.json", {}) or {}
    items = load_json(MS / "items.json", {}) or {}
    if not results:
        print("[ai] no results yet")
        return
    ok = [r for r in results.values() if r.get("ok")]
    types = Counter(r.get("answer_type") for r in ok)
    conf = Counter("high" if r.get("confidence", 0) >= THRESHOLD else "low" for r in ok)
    tin = sum(r.get("usage", {}).get("in", 0) for r in results.values())
    tout = sum(r.get("usage", {}).get("out", 0) for r in results.values())
    model = next((r.get("model") for r in results.values() if r.get("model")), "claude-sonnet-5")
    pi, po = PRICE.get(model, (2.0, 10.0))
    cost = (tin * pi + tout * po) / 1e6 / 2  # batch discount
    print(f"[ai] {len(results)} results: {len(ok)} solvable, {len(results) - len(ok)} essay/unsolvable/failed")
    print(f"[ai] types {dict(types)} | confidence >= {THRESHOLD}: {conf['high']}, below: {conf['low']}")
    print(f"[ai] tokens in={tin} out={tout} -> ~${cost:.2f} ({model}, batch rate)")
    lines = ["# AI answer key review", "",
             f"{len(ok)} auto-gradable, {conf['low']} below confidence {THRESHOLD} (kept manual), "
             f"{len(results) - len(ok)} essay/unsolvable/failed.", "",
             "## Low confidence (manual grading, AI answer shown as hint)", ""]
    for rid, r in sorted(results.items(), key=lambda kv: kv[1].get("confidence", 0)):
        if not r.get("ok") or r.get("confidence", 0) >= THRESHOLD:
            continue
        it = items.get(rid, {})
        ans = r.get("answer") or " / ".join(f"{p['label']}={p['answer']}" for p in r.get("parts", []))
        lines.append(f"- `{rid}` {it.get('school', '')} {it.get('year', '')} [{it.get('topic', '')}] "
                     f"conf {r.get('confidence', 0):.2f} → **{ans} {r.get('unit', '')}** — {r.get('check', '')} "
                     f"[解説]({it.get('url', '')})")
    lines += ["", "## Essay / unsolvable / failed", ""]
    for rid, r in sorted(results.items()):
        if r.get("ok"):
            continue
        it = items.get(rid, {})
        lines.append(f"- `{rid}` {it.get('school', '')} {it.get('year', '')} [{it.get('topic', '')}] "
                     f"{r.get('error') or r.get('answer_type')} — {r.get('check', '')} [解説]({it.get('url', '')})")
    AI.mkdir(parents=True, exist_ok=True)
    (AI / "review.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[ai] review -> {AI / 'review.md'}")


def estimate(model: str) -> None:
    c = client()
    todo = problems(False)
    if not todo:
        sys.exit("no problems")
    sample = todo[len(todo) // 2]
    p = request_params(sample, model)
    n = c.messages.count_tokens(model=model, system=p["system"], messages=p["messages"]).input_tokens
    pi, po = PRICE.get(model, (2.0, 10.0))
    for out_tok in (2000, 4000):
        cost = (n * pi + out_tok * po) / 1e6 / 2 * len(todo)
        print(f"[ai] {len(todo)} problems x ({n} in + ~{out_tok} out) tokens -> ~${cost:.0f} ({model}, batch rate)")


def chunks(size: int, only_missing: bool) -> None:
    """Write out/minsan/ai/chunks/chunk_NNN.json work lists for solving inside Claude Code (agents) instead of
    the Batches API. Each agent writes out/minsan/ai/parts/chunk_NNN.json in the SCHEMA shape (+ ok, model)."""
    todo = problems(only_missing)
    d = AI / "chunks"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("chunk_*.json"):
        f.unlink()
    for n, i in enumerate(range(0, len(todo), size)):
        rows = [{"id": it["id"], "png": str(PNG / f"{it['id']}.png"), "school": it.get("school"), "year": it.get("year"),
                 "topic": it.get("topic"), "tags": it.get("tags") or []} for it in todo[i:i + size]]
        dump_json(d / f"chunk_{n:03d}.json", rows)
    print(f"[ai] {len(todo)} problems -> {(len(todo) + size - 1) // size} chunks of <= {size} in {d}")
    (AI / "SCHEMA.json").write_text(json.dumps(SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")
    (AI / "PROMPT.md").write_text(SYSTEM, encoding="utf-8")


def merge() -> None:
    """Merge out/minsan/ai/parts/*.json (agent output) into results.json; validates against SCHEMA keys."""
    results = load_json(AI / "results.json", {}) or {}
    n_new = n_bad = 0
    for f in sorted((AI / "parts").glob("*.json")):
        part = load_json(f, {}) or {}
        for rid, r in part.items():
            missing = [k for k in SCHEMA["required"] if k not in r]
            if missing:
                n_bad += 1
                print(f"  {f.name} {rid}: missing {missing}")
                continue
            r["ok"] = bool(r.get("solvable")) and r.get("answer_type") != "essay"
            r.setdefault("model", "claude-code")
            results[rid] = r
            n_new += 1
    dump_json(AI / "results.json", results)
    print(f"[ai] merged {n_new} results ({n_bad} rejected) -> {len(results)} total")
    report()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["submit", "fetch", "report", "estimate", "chunks", "merge"])
    ap.add_argument("--size", type=int, default=25, help="chunks: problems per agent work list")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only-missing", action="store_true", help="skip problems that already have an ok result")
    ap.add_argument("--wait", action="store_true", help="fetch: poll every 60 s until all batches ended")
    a = ap.parse_args()
    if a.cmd == "submit":
        submit(a.model, a.limit, a.only_missing)
    elif a.cmd == "fetch":
        fetch(a.wait)
    elif a.cmd == "report":
        report()
    elif a.cmd == "chunks":
        chunks(a.size, a.only_missing)
    elif a.cmd == "merge":
        merge()
    else:
        estimate(a.model)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
