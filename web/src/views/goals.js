// 今週の目標 card (dashboard + 保護者ページ). Goals come from topicStats/summary.goals (functions/goals.py):
// frozen per week (Monday JST) from the results before it; `actual` = this week's progress so far.
const SUBJ = { math: '算数', japanese: '国語', science: '理科', social: '社会' };
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const md = (iso) => iso.slice(5).replace('-', '/').replace(/^0/, '');

/** Whole days from today (JST) to the exam day. */
export function daysUntil(isoDate, now = new Date()) {
  const today = new Date(now.getTime() + 9 * 3600e3).toISOString().slice(0, 10);
  return Math.round((Date.parse(isoDate) - Date.parse(today)) / 86400e3);
}

/** ✅ met / ▶ in progress / ⚠️ accuracy below goal (only once a few questions are in). */
export function goalStatus(g, a) {
  const accOk = g.goalAccuracy == null || (a.accuracy != null && a.accuracy >= g.goalAccuracy);
  if (a.items >= g.goalItems && accOk) return 'done';
  if (a.items >= 5 && !accOk) return 'low';
  return 'progress';
}
const ICON = { done: '✅', progress: '▶', low: '⚠️' };

export function goalCard(goals, { gradeQ = '', practice = true } = {}) {
  if (!goals?.subjects) return '';
  const end = new Date(Date.parse(goals.weekStart) + 6 * 86400e3).toISOString().slice(0, 10);
  const days = daysUntil(goals.examDate);
  const provisional = Object.values(goals.subjects).some((s) => s.provisional);
  const bases = Object.entries(SUBJ).filter(([k]) => goals.subjects[k]?.basis)
    .map(([k, label]) => `${label}: ${goals.subjects[k].basis}`).join(' / ');
  const rows = Object.entries(SUBJ).map(([k, label]) => {
    const g = goals.subjects[k];
    if (!g) return '';
    const a = goals.actual?.[k] || { items: 0, correct: 0, accuracy: null };
    const st = goalStatus(g, a);
    const fill = Math.min(100, Math.round((a.items / g.goalItems) * 100));
    const focus = (g.focus || []).map((f) => (practice
      ? `<a class="chip" href="#/practice/${k}?topic=${encodeURIComponent(f.topic)}${gradeQ}">${esc(f.topic)}</a>`
      : `<span class="chip">${esc(f.topic)}</span>`)).join('');
    return `<tr class="goal-${st}">
      <td>${ICON[st]} ${label}</td>
      <td><div class="bar"><div style="width:${fill}%"></div></div> ${a.items} / ${g.goalItems}問${g.behind ? ' <small class="warn">先週未達→増量</small>' : ''}</td>
      <td>${pct(a.accuracy)} <span class="muted">/ ${g.goalAccuracy == null ? '—' : pct(g.goalAccuracy)}</span></td>
      <td title="${esc(g.basis || '')}">${pct(g.level)} <span class="muted">→</span> ${pct(g.target)}${g.provisional ? '<small class="muted">(仮)</small>' : ''}${g.atRisk ? ' <small class="ng">ペース不足</small>' : ''}</td>
      <td><div class="chips">${focus || '<span class="muted">—</span>'}</div></td></tr>`;
  }).join('');
  return `<div class="card goal-card">
    <div class="big-head"><h2 style="margin:0">今週の目標</h2><span class="muted">${md(goals.weekStart)}〜${md(end)}</span>
      <span style="margin-left:auto">第一志望 ${esc(goals.firstName)} 入試まで <b class="countdown">${days}</b> 日</span></div>
    <table><tr><th>科目</th><th>解いた問題</th><th>正答率 今週 / 目標</th><th>実力 → 最終目標</th><th>重点分野</th></tr>${rows}</table>
    <p class="muted small">目標は毎週月曜に先週までの結果から自動で決まります（${esc(md(goals.deadline))}までに最終目標に届くペース、残り${goals.weeksLeft}週）。
      最終目標＝${esc(goals.firstName)}・${esc(goals.secondName)}の合格者平均のうち高い方${bases ? `（${esc(bases)}）` : ''}。
      重点分野＝苦手 × 両校の過去問によく出る分野。${provisional ? '（仮）＝合格点が未登録のため目標70%で計算中。' : ''}</p>
  </div>`;
}
