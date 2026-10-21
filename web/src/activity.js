// What the child actually did, by kind — shown to the parent (and on the dashboard) instead of one 受験 count.
//   exam     本番: a whole exam (mode exam)          range    the same exam, 小N まで only (mode practice + examId)
//   redo     やり直し of an exam (redoOf)            practice 弱点分野の練習 (mode practice, no examId)
// For practice the result that matters is which 分野 got better, not how many sets were done.
export function kindOf(a) {
  if (a.redoOf) return 'redo';
  if (a.examId) return a.mode === 'exam' && !a.gradeFilter ? 'exam' : 'range';
  return 'practice';
}

const done = (a) => a.status === 'graded' || a.status === 'submitted';
const when = (a) => String(a.submittedAt || a.gradedAt || a.startedAt || '');

/** {exam, range, redo, practice}: submitted attempts per kind (in-progress sheets don't count). */
export function activityCounts(attempts) {
  const out = { exam: 0, range: 0, redo: 0, practice: 0 };
  for (const a of attempts) if (done(a)) out[kindOf(a)] += 1;
  return out;
}

export const IMPROVE = { minItems: 3, gain: 0.15, pass: 0.6, window: 10 };

/**
 * Per 分野 the child practiced: accuracy before the first practice set that contained it (all earlier answers) vs
 * after (the latest `window` answers from that practice on, any kind of attempt). improved = +15pt or more, or
 * from below 60% to 60%+. `before` is null when there were too few earlier answers to compare (then never improved).
 */
export function practiceImprovement(attempts, opt = IMPROVE) {
  const graded = attempts.filter((a) => a.status === 'graded' && a.result?.perItem).sort((x, y) => when(x).localeCompare(when(y)));
  const rows = [];   // chronological answers: {key, ok, practice}
  for (const a of graded) {
    const practice = kindOf(a) === 'practice';
    for (const it of Object.values(a.result.perItem)) {
      if (it.pending || !it.topic) continue;
      rows.push({ key: `${it.subject || ''}|${it.topic}`, ok: Boolean(it.correct), practice });
    }
  }
  const firstPractice = new Map();
  rows.forEach((r, i) => { if (r.practice && !firstPractice.has(r.key)) firstPractice.set(r.key, i); });
  const acc = (list) => (list.length ? list.filter((r) => r.ok).length / list.length : null);
  const out = [];
  for (const [key, start] of firstPractice) {
    const mine = rows.map((r, i) => ({ ...r, i })).filter((r) => r.key === key);
    const beforeList = mine.filter((r) => r.i < start);
    const afterList = mine.filter((r) => r.i >= start).slice(-opt.window);
    const before = beforeList.length >= opt.minItems ? acc(beforeList) : null;
    const after = afterList.length >= opt.minItems ? acc(afterList) : null;
    const improved = before != null && after != null && (after - before >= opt.gain || (before < opt.pass && after >= opt.pass));
    const [subject, topic] = key.split('|');
    out.push({ subject, topic, before, after, n: afterList.length, improved });
  }
  return out.sort((x, y) => (y.improved - x.improved) || ((y.after ?? 0) - (y.before ?? 0)) - ((x.after ?? 0) - (x.before ?? 0)));
}

const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const SUBJ = { math: '算数', science: '理科', social: '社会', japanese: '国語' };

/** One line: 本番 3回（範囲指定 2回）· やり直し 1回 · 練習で改善 2分野 / 練習した 5分野 */
export function activityLine(attempts) {
  const c = activityCounts(attempts);
  const imp = practiceImprovement(attempts);
  const better = imp.filter((x) => x.improved).length;
  return `本番 <b>${c.exam}</b>回${c.range ? `（範囲指定 ${c.range}回）` : ''}${c.redo ? ` · やり直し ${c.redo}回` : ''}
    · 練習で改善 <b>${better}</b>分野${imp.length ? ` <small class="muted">/ 練習した ${imp.length}分野</small>` : ''}`;
}

/** 弱点練習の成果: improved 分野 first (before → after), then the ones still being practiced. */
export function improvementCard(attempts) {
  const imp = practiceImprovement(attempts);
  if (!imp.length) return '';
  const chip = (x) => `<span class="chip ${x.improved ? 'ok-chip' : ''}" title="${x.n}問 (練習後の直近)">${esc(x.topic)}
    <small class="muted">${SUBJ[x.subject] || ''}</small> ${pct(x.before)} → <b>${pct(x.after)}</b></span>`;
  const better = imp.filter((x) => x.improved);
  const rest = imp.filter((x) => !x.improved);
  return `<div class="card"><h2>弱点練習の成果 <small class="muted">改善 ${better.length} / 練習した ${imp.length} 分野</small></h2>
    ${better.length ? `<div class="chips">${better.map(chip).join('')}</div>` : '<p class="muted">まだ改善した分野はありません。</p>'}
    ${rest.length ? `<h3>練習中</h3><div class="chips">${rest.map(chip).join('')}</div>` : ''}
    <p class="muted small">練習前の正答率 → 練習後（直近${IMPROVE.window}問）。+${IMPROVE.gain * 100}ポイント以上、または${IMPROVE.pass * 100}%未満から${IMPROVE.pass * 100}%以上になった分野を「改善」としています。</p>
  </div>`;
}
