import { getTopicStats, currentUser, listChildren } from '../api.js';
import { daysUntil } from './goals.js';
import { selectedChild, childPicker, bindChildPicker } from '../children.js';

// 全体計画 (#/plan for the child, a card on the parent's child page): topicStats/summary.plan from
// functions/goals.py — past weeks (assigned vs done), this / next week, the projected weeks to the exam, milestones.
// The parent's card adds two 予定 / 実績 charts (study time): cumulative to the exam, and the last weeks one by one.
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const md = (iso) => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;
const addDays = (iso, n) => new Date(Date.parse(iso) + n * 86400e3).toISOString().slice(0, 10);
const PHASE_CLS = { '5年': 'p5', '6年 前期': 'p6', '6年 後期': 'pk', 直前期: 'pc' };
// series colours (validated pair: lightness band, chroma, CVD ΔE 32, contrast ≥ 3:1 on white)
const PLAN = '#d97706';
const DONE = '#2563eb';
const hours = (min) => Math.round(min / 6) / 10;
/** Round axis steps (1, 2, 5 × 10^k hours) up to `maxH`: [0, step, 2·step, …] with the last ≥ maxH. */
export function niceTicks(maxH, count = 5) {
  const raw = Math.max(maxH, 0.1) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((v) => v >= raw);
  const out = [];
  for (let v = 0; v < maxH + step - 1e-9; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

function weekRow(w, { cur, links, milestones }) {
  const end = addDays(w.weekStart, 6);
  const ms = milestones.filter((m) => m.date >= w.weekStart && m.date <= end)
    .map((m) => `<span class="chip ${m.exam ? 'weak' : ''}">🚩 ${md(m.date)} ${esc(m.label)}</span>`).join('');
  const total = w.items.reduce((n, it) => n + it.minutes, 0);
  const list = w.items.length
    ? w.items.map((it) => (it.retake ? '<span class="badge retake">2回目</span>' : '')
      + (it.planned ? `<span class="planned" title="これから追加される予定">${esc(it.label)}</span>`
        : links ? `<a href="#/exam/${it.examId}${w.grade && !it.retake ? `?g=${w.grade}` : ''}">${esc(it.label)}</a>` : esc(it.label))).join('、')
    : '<span class="muted">やり直し</span>';
  return `<tr class="${w.weekStart === cur ? 'current' : ''}"><td class="nowrap">${md(w.weekStart)}${w.weekStart === cur ? ' <span class="badge new">今週</span>' : ''}</td>
    <td>${list} ${ms}</td><td class="nowrap muted">${total ? `${total}分` : ''}</td></tr>`;
}

/** Weekly points: past weeks (history), this week (goals, in progress), then the planned weeks. */
export function progressSeries(stats) {
  const p = stats?.plan;
  if (!p) return [];
  const g = stats.goals;
  const out = (p.history || []).map((h) => ({ week: h.weekStart, plan: h.minutes, done: h.doneMinutes,
    items: h.items, doneItems: h.done, missed: h.missed || [] }));
  const curItems = g?.assignments?.items || [];
  if (g?.weekStart && curItems.length && !out.some((o) => o.week === g.weekStart)) {
    const done = g.assignmentsDone || [];
    out.push({ week: g.weekStart, plan: curItems.reduce((n, it) => n + it.minutes, 0),
      done: curItems.reduce((n, it, i) => n + (done[i] ? it.minutes : 0), 0),
      items: curItems.length, doneItems: done.filter(Boolean).length, current: true,
      missed: curItems.filter((_, i) => !done[i]).map((it) => it.label) });
  }
  const last = out.length ? out[out.length - 1].week : '';
  for (const w of p.weeks) {
    if (w.weekStart <= last) continue;
    out.push({ week: w.weekStart, plan: w.items.reduce((n, it) => n + it.minutes, 0), done: null, future: true });
  }
  return out;
}

const tip = (s) => `${md(s.week)}〜 予定 ${hours(s.plan)}時間${s.done == null ? '' : ` / 実績 ${hours(s.done)}時間 (${s.doneItems}/${s.items}回分)`}`
  + (s.missed?.length && !s.future ? `\nやり残し: ${s.missed.join('、')}` : '');

/** Cumulative study time: 予定 (whole road to the exam) vs 実績 (so far). One axis: hours. */
export function cumulativeChart(series, { milestones = [] } = {}) {
  if (series.filter((s) => !s.future).length === 0) return '';
  const W = 640, H = 220, L = 44, R = 64, T = 14, B = 26;
  let planSum = 0, doneSum = 0;
  const pts = series.map((s) => {
    planSum += s.plan;
    if (s.done != null) doneSum += s.done;
    return { ...s, cp: planSum, cd: s.done == null ? null : doneSum };
  });
  const yTicks = niceTicks(hours(Math.max(60, planSum)));
  const max = yTicks[yTicks.length - 1] * 60;
  const step = (W - L - R) / Math.max(1, pts.length - 1);
  const x = (i) => L + i * step;
  const y = (min) => T + (H - T - B) * (1 - min / max);
  const line = (key) => pts.map((p, i) => (p[key] == null ? null : `${x(i)},${y(p[key])}`)).filter(Boolean).join(' ');
  const lastDone = pts.reduce((k, p, i) => (p.cd != null ? i : k), -1);
  const grid = yTicks.map((h) => `<line x1="${L}" x2="${W - R}" y1="${y(h * 60)}" y2="${y(h * 60)}" class="grid"></line>
    <text x="${L - 6}" y="${y(h * 60) + 4}" text-anchor="end" class="axis">${h}</text>`).join('');
  // x axis: the first week of Jan / Apr / Jul / Oct (a long road: monthly labels would collide); January carries the year
  let lastTick = -Infinity;
  const xTicks = pts.map((p, i) => {
    const m = Number(p.week.slice(5, 7));
    if (i && m === Number(pts[i - 1].week.slice(5, 7))) return '';
    if (i && ((m - 1) % 3 || x(i) - lastTick < 80)) return '';   // no label colliding with the previous one
    lastTick = x(i);
    const txt = m === 1 || i === 0 ? `${p.week.slice(0, 4)}年${m}月` : `${m}月`;
    return `<line x1="${x(i)}" x2="${x(i)}" y1="${H - B}" y2="${H - B + 4}" class="grid"></line>
      <text x="${x(i)}" y="${H - 8}" text-anchor="${i === 0 ? 'start' : 'middle'}" class="axis">${txt}</text>`;
  }).join('');
  const examMs = milestones.filter((m) => m.exam).map((m) => {
    const i = pts.findIndex((p) => p.week > m.date) - 1;
    return i >= 0 ? `<line x1="${x(i)}" x2="${x(i)}" y1="${T}" y2="${H - B}" class="ms"></line>` : '';
  }).join('');
  const hit = pts.map((p, i) => `<rect x="${x(i) - step / 2}" y="${T}" width="${step}" height="${H - T - B}" class="hit"><title>${esc(tip(p))}\n累計 予定 ${hours(p.cp)}時間${p.cd == null ? '' : ` / 実績 ${hours(p.cd)}時間`}</title></rect>`).join('');
  const now = lastDone >= 0 ? pts[lastDone] : null;
  const end = pts[pts.length - 1];
  return `<figure class="viz"><figcaption>累計の学習時間 <small class="muted">(時間)</small>
      <span class="legend"><i style="background:${PLAN}"></i>予定 <i style="background:${DONE}"></i>実績</span></figcaption>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="累計の学習時間 予定と実績">
      ${grid}${examMs}${xTicks}
      <polyline points="${line('cp')}" fill="none" stroke="${PLAN}" stroke-width="2" stroke-dasharray="5 4"></polyline>
      <polyline points="${line('cd')}" fill="none" stroke="${DONE}" stroke-width="2"></polyline>
      ${now ? `<circle cx="${x(lastDone)}" cy="${y(now.cd)}" r="4.5" fill="${DONE}" stroke="#fff" stroke-width="2"></circle>
        <text x="${x(lastDone) + 8}" y="${y(now.cd) - 8}" class="label">実績 ${hours(now.cd)}h / 予定 ${hours(now.cp)}h</text>` : ''}
      <text x="${W - R + 6}" y="${y(end.cp) + 4}" class="label">${hours(end.cp)}h</text>
      ${hit}
    </svg></figure>`;
}

/** Last weeks one by one: 予定 vs 実績 bars (minutes), ⚠ over a week with やり残し. */
export function weeklyBars(series, n = 12) {
  const past = series.filter((s) => !s.future).slice(-n);
  if (!past.length) return '';
  const W = 640, H = 170, L = 44, R = 10, T = 18, B = 26;
  const ticks = niceTicks(hours(Math.max(60, ...past.map((s) => Math.max(s.plan, s.done || 0)))), 4);
  const max = ticks[ticks.length - 1] * 60;
  const slot = (W - L - R) / past.length;
  const bw = Math.min(18, (slot - 10) / 2);
  const y = (min) => T + (H - T - B) * (1 - min / max);
  const base = H - B;
  // bar with the 4px rounded end at the top, square at the baseline
  const bar = (x0, v, color) => {
    if (!v) return '';
    const top = y(v), r = Math.min(4, (base - top) / 2, bw / 2);
    return `<path d="M${x0},${base} V${top + r} Q${x0},${top} ${x0 + r},${top} H${x0 + bw - r} Q${x0 + bw},${top} ${x0 + bw},${top + r} V${base} Z" fill="${color}"></path>`;
  };
  const marks = past.map((s, i) => {
    const cx = L + slot * i + slot / 2;
    const x1 = cx - bw - 1, x2 = cx + 1; // 2px gap between the pair
    const short = s.done < s.plan && !s.current;
    return `${bar(x1, s.plan, PLAN)}${bar(x2, s.done, DONE)}
      ${short ? `<text x="${cx}" y="${Math.min(y(s.plan), y(s.done || 0)) - 4}" text-anchor="middle" class="label">⚠</text>` : ''}
      <text x="${cx}" y="${H - 8}" text-anchor="middle" class="axis">${md(s.week)}${s.current ? '*' : ''}</text>
      <rect x="${L + slot * i}" y="${T}" width="${slot}" height="${H - T - B}" class="hit"><title>${esc(tip(s))}${s.current ? '\n（今週・途中）' : ''}</title></rect>`;
  }).join('');
  const grid = ticks.map((h) => `<line x1="${L}" x2="${W - R}" y1="${y(h * 60)}" y2="${y(h * 60)}" class="grid"></line>
    <text x="${L - 6}" y="${y(h * 60) + 4}" text-anchor="end" class="axis">${h}</text>`).join('');
  return `<figure class="viz"><figcaption>週ごとの予定と実績 <small class="muted">(時間 · ⚠ やり残し · * 今週)</small>
      <span class="legend"><i style="background:${PLAN}"></i>予定 <i style="background:${DONE}"></i>実績</span></figcaption>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="週ごとの予定と実績">${grid}${marks}</svg></figure>`;
}

/** The charts' numbers as a table (collapsed): past weeks, newest first. */
function historyTable(series) {
  const past = series.filter((s) => !s.future).reverse();
  if (!past.length) return '';
  return `<details class="viz-table"><summary class="muted small">表で見る</summary><table>
    <tr><th>週</th><th>回分</th><th>時間 実績 / 予定</th><th>やり残し</th></tr>
    ${past.map((s) => `<tr><td class="nowrap">${md(s.week)}〜${s.current ? ' <span class="badge new">今週</span>' : ''}</td>
      <td>${s.doneItems} / ${s.items}</td><td class="nowrap">${hours(s.done)} / ${hours(s.plan)}</td>
      <td class="small">${s.current ? '' : (s.missed.map(esc).join('、') || '—')}</td></tr>`).join('')}</table></details>`;
}

export function planCard(stats, { links = true, charts = false, now = new Date() } = {}) {
  const p = stats?.plan;
  if (!p?.weeks?.length) return '';
  const cur = stats.goals?.weekStart || p.weeks[0].weekStart;
  const months = new Map();
  for (const w of p.weeks) {
    const k = w.weekStart.slice(0, 7);
    if (!months.has(k)) months.set(k, []);
    months.get(k).push(w);
  }
  const body = [...months.keys()].map((k, i) => {
    const ws = months.get(k);
    const phase = ws[0].phase;
    return `<details class="month" ${i < 2 ? 'open' : ''}><summary>${Number(k.slice(0, 4))}年${Number(k.slice(5))}月
      <span class="phase ${PHASE_CLS[phase] || ''}">${esc(phase)}</span>
      <small class="muted">${ws.reduce((n, w) => n + w.items.length, 0)} 回分</small></summary>
    <table>${ws.map((w) => weekRow(w, { cur, links, milestones: p.milestones || [] })).join('')}</table></details>`;
  }).join('');
  const behind = (p.history || []).filter((h) => h.done < h.items).length;
  const series = charts ? progressSeries(stats) : [];
  return `<div class="card plan-card">
    <div class="big-head"><h2 style="margin:0">全体計画</h2>
      ${p.finishWeek ? `<span class="muted">一巡 ${md(p.finishWeek)}${p.retakes ? ` · 2回目 ${p.retakes}回` : ''}</span>` : ''}
      ${behind ? `<span class="warn">⚠ やり残し ${behind}週</span>` : ''}
      <span style="margin-left:auto">入試まで <b class="countdown">${daysUntil(p.examDate, now)}</b> 日</span></div>
    ${charts ? `${cumulativeChart(series, { milestones: p.milestones || [] })}${weeklyBars(series)}${historyTable(series)}` : ''}
    <h3>これからの予定 <small class="muted">毎週 約${hours(p.newBudget)}時間 ＋ やり直し</small></h3>
    ${body}
  </div>`;
}

export async function renderPlan({ app }) {
  app.innerHTML = '<div class="card">読み込み中…</div>';
  if (currentUser()?.admin) {   // the parent's 計画 tab: the selected child (picker with 2+ children)
    const kids = await listChildren();
    const k = selectedChild(kids);
    if (!k) {
      app.innerHTML = '<div class="card"><h1>全体計画</h1><p class="muted">連携している子どもがいません。<a href="#/parent">保護者ページ</a>で追加してください。</p></div>';
      return;
    }
    const card = planCard(await getTopicStats(k.uid), { links: false, charts: true });
    const title = `<h2 style="margin:0">全体計画 <small class="muted">${esc(k.name)}</small></h2>`;
    app.innerHTML = (kids.length > 1 ? `<div class="card">${childPicker(kids, k)}</div>` : '')
      + (card ? card.replace('<h2 style="margin:0">全体計画</h2>', title) : `<div class="card">${title}<p class="muted">まだ計画がありません。</p></div>`);
    bindChildPicker(app, () => renderPlan({ app }));
    return;
  }
  const stats = await getTopicStats();
  app.innerHTML = planCard(stats) || '<div class="card"><h1>全体計画</h1><p class="muted">まだ計画がありません。最初の問題を解くと作られます。</p></div>';
}
