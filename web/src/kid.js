// Student (kid) dashboard pieces: greeting + this week's progress, big task cards, がんばりコーナー.
// Everything shown is computed from real data (goals / attempts) — no points or coins that mean nothing.
import { taskHref } from './views/goals.js';
import { practiceImprovement, kindOf } from './activity.js';
import { attemptSeconds, duration } from './views/parent.js';

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
export const SUBJECT_LOOK = {
  math: { label: '算数', icon: '🧮', cls: 's-math' },
  japanese: { label: '国語', icon: '📖', cls: 's-japanese' },
  science: { label: '理科', icon: '🔬', cls: 's-science' },
  social: { label: '社会', icon: '🌏', cls: 's-social' },
};
const KIND_KID = { new: 'あたらしい問題', retake: '2回目にちょうせん', review: 'やり直し' };
const jstDay = (t) => new Date(Date.parse(t) + 9 * 3600e3).toISOString().slice(0, 10);
const dayBefore = (d) => new Date(Date.parse(d) - 86400e3).toISOString().slice(0, 10);

/** Days in a row (JST) with at least one submitted sheet, ending today — or yesterday, so the morning isn't 0. */
export function streakDays(attempts, now = new Date()) {
  const days = new Set(attempts.filter((a) => a.submittedAt).map((a) => jstDay(a.submittedAt)));
  let d = jstDay(now.toISOString());
  if (!days.has(d)) d = dayBefore(d);
  let n = 0;
  while (days.has(d)) { n += 1; d = dayBefore(d); }
  return n;
}

/** Working time (s) of the sheets submitted since `weekStart` (YYYY-MM-DD, JST Monday). */
export function weekSeconds(attempts, weekStart) {
  return attempts.filter((a) => a.submittedAt && jstDay(a.submittedAt) >= weekStart)
    .reduce((n, a) => n + (attemptSeconds(a)?.sec || 0), 0);
}

/** Badges earned from real results; locked ones say what is still needed. */
export function badges(attempts, goals, now = new Date()) {
  const streak = streakDays(attempts, now);
  const items = goals?.assignments?.items || [];
  const doneTasks = (goals?.assignmentsDone || []).filter(Boolean).length;
  const improved = practiceImprovement(attempts).filter((x) => x.improved).length;
  const exams = attempts.filter((a) => a.status === 'graded' && kindOf(a) === 'exam').length;
  const perfect = attempts.some((a) => a.status === 'graded' && a.percent === 100);
  return [
    { icon: '🏃', name: 'はじめの一歩', got: exams >= 1, need: '本番を1回' },
    { icon: '🔥', name: '3日つづけた', got: streak >= 3, need: `あと${Math.max(0, 3 - streak)}日` },
    { icon: '🌟', name: '7日つづけた', got: streak >= 7, need: `あと${Math.max(0, 7 - streak)}日` },
    { icon: '✅', name: '今週コンプリート', got: items.length > 0 && doneTasks === items.length, need: `あと${Math.max(0, items.length - doneTasks)}こ` },
    { icon: '📈', name: 'にがて克服', got: improved >= 1, need: '練習で分野をのばそう' },
    { icon: '💯', name: '満点', got: perfect, need: '100点をとろう' },
  ];
}

/** Hero: greeting, countdown, this week's 課題 progress. */
export function heroCard(name, goals, attempts, now = new Date()) {
  const items = goals?.assignments?.items || [];
  const doneArr = goals?.assignmentsDone || [];
  const n = doneArr.filter(Boolean).length;
  const pctDone = items.length ? Math.round((n / items.length) * 100) : 0;
  const left = items.length - n;
  const days = goals?.examDate ? Math.round((Date.parse(goals.examDate) - Date.parse(jstDay(now.toISOString()))) / 86400e3) : null;
  const msg = !items.length ? '今週の課題はまだありません'
    : left === 0 ? 'ぜんぶできたね！ すごい！ 🎉' : `あと <b>${left}</b> こ！ がんばろう`;
  return `<div class="card kid-hero">
    <div class="kid-hero-star" aria-hidden="true">★</div>
    <div class="kid-hero-text">
      <h1>こんにちは、${esc(name)}さん！ ✨</h1>
      <p>${days != null ? `${esc(goals.firstName || '入試')}まで <b class="kid-count">${days}</b> 日` : 'きょうも いっしょに がんばろう！'}</p>
    </div>
    <div class="kid-progress">
      <div class="kid-progress-head"><span>今週の課題</span><span class="kid-pill">${n} / ${items.length}</span></div>
      <div class="kid-bar"><div style="width:${pctDone}%"></div></div>
      <p>${msg}</p>
    </div>
  </div>`;
}

/** Big task cards, one per 課題 of this week (done ones stay, ticked). */
export function taskCards(goals, subjectOf) {
  const asg = goals?.assignments;
  if (!asg?.items?.length) return '';
  const done = goals.assignmentsDone || [];
  return asg.items.map((it, i) => {
    const look = SUBJECT_LOOK[subjectOf(it.examId)] || SUBJECT_LOOK.math;
    const fin = Boolean(done[i]);
    return `<div class="kid-task ${look.cls} ${fin ? 'done' : ''}">
      <div class="kid-task-icon" aria-hidden="true">${fin ? '✅' : look.icon}</div>
      <div class="kid-task-body">
        <div class="kid-task-subject">${look.label} <span class="kid-tag">${KIND_KID[it.kind] || ''}</span></div>
        <div class="kid-task-title">${esc(it.label)}</div>
        <div class="kid-task-meta"><span>⏱ ${it.minutes}分</span>${it.kind === 'review' ? `<span>✏️ ${it.items.length}問</span>` : ''}</div>
      </div>
      ${fin ? '<span class="kid-done">できた！</span>'
        : `<a class="kid-go" href="${taskHref(asg, it)}">▶ はじめる</a>`}
    </div>`;
  }).join('');
}

/** がんばりコーナー: streak, this week's time, badges, 分野 that got better. */
export function cheerCard(attempts, goals, now = new Date()) {
  const streak = streakDays(attempts, now);
  const sec = goals?.weekStart ? weekSeconds(attempts, goals.weekStart) : 0;
  const better = practiceImprovement(attempts).filter((x) => x.improved);
  const bs = badges(attempts, goals, now);
  return `<div class="card kid-cheer">
    <div class="kid-stats">
      <div><div class="kid-stat-num">🔥 ${streak}<small>日</small></div><div class="kid-stat-label">つづけている日</div></div>
      <div><div class="kid-stat-num">⏱ ${sec ? duration(sec) : '0分'}</div><div class="kid-stat-label">今週べんきょうした時間</div></div>
    </div>
    <h3>バッジ <small>${bs.filter((b) => b.got).length} / ${bs.length}</small></h3>
    <div class="kid-badges">${bs.map((b) => `<div class="kid-badge ${b.got ? 'got' : ''}" title="${esc(b.got ? b.name : b.need)}">
      <div class="kid-badge-icon">${b.icon}</div><div class="kid-badge-name">${esc(b.name)}</div>
      ${b.got ? '' : `<div class="kid-badge-need">${esc(b.need)}</div>`}</div>`).join('')}</div>
    ${better.length ? `<h3>のびた分野 📈</h3><div class="chips">${better.slice(0, 6).map((x) =>
      `<span class="chip ok-chip">${esc(x.topic)} ${Math.round(x.before * 100)}→<b>${Math.round(x.after * 100)}%</b></span>`).join('')}</div>` : ''}
  </div>`;
}
