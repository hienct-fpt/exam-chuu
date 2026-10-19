import { getTopicStats } from '../api.js';
import { daysUntil } from './goals.js';

// 全体計画 (#/plan for the child, a card on the parent's child page): topicStats/summary.plan from
// functions/goals.py — past weeks (assigned vs done), this / next week, the projected weeks to the exam, milestones.
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const md = (iso) => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;
const addDays = (iso, n) => new Date(Date.parse(iso) + n * 86400e3).toISOString().slice(0, 10);
const PHASE_CLS = { '5年': 'p5', '6年 前期': 'p6', 過去問期: 'pk', 直前期: 'pc' };

function weekRow(w, { now, cur, links, milestones }) {
  const end = addDays(w.weekStart, 6);
  const ms = milestones.filter((m) => m.date >= w.weekStart && m.date <= end)
    .map((m) => `<div class="milestone ${m.exam ? 'exam' : ''}">🚩 ${md(m.date)} ${esc(m.label)}</div>`).join('');
  const total = w.items.reduce((n, it) => n + it.minutes, 0);
  const tag = w.weekStart === cur ? '<span class="badge new">今週</span>' : w.weekStart < now ? '' : '';
  const list = w.items.length
    ? w.items.map((it) => (links ? `<a href="#/exam/${it.examId}${w.grade ? `?g=${w.grade}` : ''}">${esc(it.label)}</a>` : esc(it.label))).join('、')
    : '<span class="muted">やり直し・新しく追加される組分け／過去問</span>';
  return `<tr class="${w.weekStart === cur ? 'current' : ''}"><td class="nowrap">${md(w.weekStart)}〜${md(end)} ${tag}</td>
    <td><span class="phase ${PHASE_CLS[w.phase] || ''}">${esc(w.phase)}</span></td>
    <td>${list}${ms}</td><td class="nowrap muted">${total ? `${total}分` : ''}</td></tr>`;
}

/** Past weeks: how much of each week's 課題 was done (for the parent's reminder). */
function historyTable(hist) {
  if (!hist?.length) return '';
  return `<h3>これまでの週</h3><table><tr><th>週</th><th>課題</th><th>時間</th><th>やり残し</th></tr>
    ${hist.slice(-8).reverse().map((h) => `<tr class="${h.done < h.items ? 'weak' : ''}"><td class="nowrap">${md(h.weekStart)}〜</td>
      <td>${h.done === h.items ? '✅' : '⚠️'} ${h.done} / ${h.items}</td><td class="nowrap">${h.doneMinutes} / ${h.minutes}分</td>
      <td class="small">${h.missed.map(esc).join('、') || '—'}</td></tr>`).join('')}</table>`;
}

export function planCard(stats, { links = true, now = new Date() } = {}) {
  const p = stats?.plan;
  if (!p?.weeks?.length) return '';
  const today = new Date(now.getTime() + 9 * 3600e3).toISOString().slice(0, 10);
  const cur = stats.goals?.weekStart || p.weeks[0].weekStart;
  // group by month; the current and next month open
  const months = new Map();
  for (const w of p.weeks) {
    const k = w.weekStart.slice(0, 7);
    if (!months.has(k)) months.set(k, []);
    months.get(k).push(w);
  }
  const keys = [...months.keys()];
  const body = keys.map((k, i) => `<details class="month" ${i < 2 ? 'open' : ''}><summary>${Number(k.slice(0, 4))}年${Number(k.slice(5))}月
      <small class="muted">${months.get(k).reduce((n, w) => n + w.items.length, 0)} 回分</small></summary>
    <table>${months.get(k).map((w) => weekRow(w, { now: today, cur, links, milestones: p.milestones || [] })).join('')}</table></details>`).join('');
  const behind = (p.history || []).filter((h) => h.done < h.items).length;
  return `<div class="card plan-card">
    <div class="big-head"><h2 style="margin:0">全体計画</h2>
      <span class="muted">予定どおり進めば ${p.finishWeek ? `${md(p.finishWeek)}の週までに今ある ${p.totalExams} 回分を一巡` : '—'}</span>
      <span style="margin-left:auto">入試まで <b class="countdown">${daysUntil(p.examDate, now)}</b> 日</span></div>
    ${behind ? `<p class="warn">やり残しのある週が ${behind} 週あります。やり残しは次の週の課題の先頭に入ります。</p>` : ''}
    <div class="chips">${(p.milestones || []).map((m) => `<span class="chip ${m.exam ? 'weak' : ''}">🚩 ${md(m.date)} ${esc(m.label)}</span>`).join('')}</div>
    ${historyTable(p.history)}
    <h3>これからの予定 <small class="muted">（毎週 新しい問題 約${p.newBudget}分 ＋ やり直し。予定は毎週の結果で更新されます）</small></h3>
    ${body}
  </div>`;
}

export async function renderPlan({ app }) {
  app.innerHTML = '<div class="card">読み込み中…</div>';
  const stats = await getTopicStats();
  app.innerHTML = planCard(stats) || '<div class="card"><h1>全体計画</h1><p class="muted">まだ計画がありません。最初の問題を解くと作られます。</p></div>';
}
