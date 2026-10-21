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
const KIND = { new: '新しい問題', retake: '2回目（全問・時間を計って）', review: 'やり直し' };

/** One line for the parent overview: 今週の課題 progress + countdown. */
export function weekSummary(goals) {
  if (!goals?.weekStart) return '';
  const items = goals.assignments?.items || [];
  const done = goals.assignmentsDone || [];
  const min = items.reduce((n, it, i) => n + (done[i] ? it.minutes : 0), 0);
  const total = items.reduce((n, it) => n + it.minutes, 0);
  const n = done.filter(Boolean).length;
  return `<div>今週の課題 <b>${n} / ${items.length}</b> <small class="muted">(${min} / ${total}分)</small>${items.length && n === items.length ? ' ✅' : ''}
    · ${esc(goals.firstName)} 入試まで <b>${daysUntil(goals.examDate)}</b> 日</div>`;
}

/** 今週の課題: new exams + やり直し within the weekly time budget (goals.assignments, frozen per week). */
/** Link of one 課題: やり直し -> the redo sheet, new / 2回目 -> the exam (new ones 小N まで when graded). */
export const taskHref = (asg, it) => (it.kind === 'review' ? `#/redo/${encodeURIComponent(it.examId)}`
  : `#/exam/${it.examId}${asg.grade && it.kind === 'new' ? `?g=${asg.grade}` : ''}`);

function taskList(asg, done, links) {
  const href = (it) => taskHref(asg, it);
  return `<ul class="assignments">${asg.items.map((it, i) => `<li class="${done[i] ? 'done' : ''}">${done[i] ? '✅' : '⬜'}
      <span class="badge ${it.kind}">${KIND[it.kind] || it.kind}</span>
      ${links && !done[i] ? `<a href="${href(it)}">${esc(it.label)}</a>` : esc(it.label)}
      <small class="muted">${it.kind === 'review' ? `間違い・未回答 ${it.items.length}問 · ` : ''}${it.minutes}分</small></li>`).join('')}</ul>`;
}

const minutesOf = (asg, done) => [asg.items.reduce((n, it, i) => n + (done[i] ? it.minutes : 0), 0),
  asg.items.reduce((n, it) => n + it.minutes, 0)];

export function assignmentList(goals, { links = true } = {}) {
  const asg = goals?.assignments;
  if (!asg?.items?.length) return '';
  const done = goals.assignmentsDone || [];
  const [doneMin, total] = minutesOf(asg, done);
  const nx = goals.next;
  const ahead = nx?.assignments?.items?.length ? (() => {
    const [nd, nt] = minutesOf(nx.assignments, nx.assignmentsDone || []);
    return `<h3>来週の課題 <span class="badge new">先取りOK</span> <small class="muted">${md(nx.weekStart)}〜 · ${nd} / ${nt}分</small></h3>
      <p class="ok small">今週の課題はぜんぶ終わりました 🎉 来週の分を先に進められます（ここで解いた分は来週の課題に数えます）。</p>
      ${taskList(nx.assignments, nx.assignmentsDone || [], links)}`;
  })() : '';
  return `<h3>今週の課題 <small class="muted">${doneMin} / ${total}分（目安 ${Math.round(asg.budget / 60 * 10) / 10}時間）</small></h3>
    ${taskList(asg, done, links)}${ahead}
    <p class="muted small">新しい問題：組分け → ${esc(goals.firstName)}・${esc(goals.secondName)}の過去問（古い年度から）→ 併願校の順。各校の最新年度は直前期用に残します。
      やり直し：前に解いた回の間違い・未回答だけをもう一度。残り ${asg.remaining} 回分${asg.grade ? `（小${asg.grade}までの問題）` : ''}。</p>`;
}

export function goalCard(goals, { gradeQ = '', practice = true, tasks = true } = {}) {
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
      <span style="margin-left:auto">第一志望 ${esc(goals.firstName)} 入試まで <b class="countdown">${days}</b> 日
</span></div>
    ${tasks ? assignmentList(goals, { links: practice }) : ''}
    <table><tr><th>科目</th><th>解いた問題</th><th>正答率 今週 / 目標</th><th>実力 → 最終目標</th><th>重点分野</th></tr>${rows}</table>
    <p class="muted small">目標は毎週月曜に先週までの結果から自動で決まります（${esc(md(goals.deadline))}までに最終目標に届くペース、残り${goals.weeksLeft}週）。
      最終目標＝${esc(goals.firstName)}・${esc(goals.secondName)}の公表データ（合格者平均、未公表なら受験者平均＋5%）のうち高い方${bases ? `（${esc(bases)}）` : ''}。
      重点分野＝苦手 × 両校の過去問によく出る分野。${provisional ? '（仮）＝合格点が未登録のため目標70%で計算中。' : ''}</p>
  </div>`;
}
