import { getTopicStats, loadAllItems, listAttempts, currentUser } from '../api.js';
import { heroCard, taskCards, cheerCard } from '../kid.js';
import { activityLine } from '../activity.js';
import { gradeFilterFromPref } from './home.js';
import { goalCard } from './goals.js';

const SUBJ = { math: '算数', science: '理科', social: '社会', japanese: '国語' };
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);

/** Inline SVG bar chart of weekly accuracy (no external library). */
export function weeklyChart(weekly) {
  if (!weekly || !weekly.length) return '';
  const W = 480, H = 120, pad = 24, bw = (W - pad * 2) / weekly.length;
  const bars = weekly.map((w, i) => {
    const h = w.accuracy == null ? 0 : (H - pad * 2) * w.accuracy;
    const x = pad + i * bw + 4, y = H - pad - h;
    const label = w.weekStart.slice(5).replace('-', '/');
    return `<rect x="${x}" y="${y}" width="${bw - 8}" height="${h}" rx="3" fill="${w.accuracy == null ? '#e5e7eb' : w.accuracy < 0.6 ? '#f87171' : '#60a5fa'}"></rect>
      <text x="${x + (bw - 8) / 2}" y="${H - 8}" font-size="10" text-anchor="middle" fill="#6b7280">${label}</text>
      ${w.attempts ? `<text x="${x + (bw - 8) / 2}" y="${y - 4}" font-size="10" text-anchor="middle" fill="#374151">${Math.round((w.accuracy || 0) * 100)}% (${w.attempts})</text>` : ''}`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px" role="img" aria-label="週ごとの正答率">
    <line x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}" stroke="#d1d5db"></line>${bars}</svg>`;
}

export async function renderDashboard({ app }) {
  app.innerHTML = '<div class="card">読み込み中…</div>';
  const [stats, all, attempts] = await Promise.all([getTopicStats(), loadAllItems(), listAttempts(300)]);
  const gf = gradeFilterFromPref(); // number | null
  const gradeQ = gf ? `&g=${gf}` : '';
  // items per topic (pool size), respecting the grade preference
  const pool = {};
  for (const it of all.items) {
    if (gf && !(it.grade && it.grade <= gf)) continue;
    const k = `${it.subject}|${it.topic || '未分類'}`;
    pool[k] = (pool[k] || 0) + 1;
  }
  const subjects = ['math', 'science', 'social', 'japanese'];
  const subjectOf = (examId) => all.banks[examId]?.subject || 'math';
  const me = currentUser()?.name || '';
  // kid layout: greeting + this week, task cards | がんばりコーナー; the old detail stays below, folded
  const top = `${heroCard(me, stats.goals, attempts)}
    <div class="kid-grid">
      <section><h2 class="kid-h">📚 今週の課題</h2>${taskCards(stats.goals, subjectOf) || '<div class="card muted">今週の課題はまだありません。</div>'}
        ${nextWeek(stats.goals, subjectOf)}</section>
      <section><h2 class="kid-h">🏅 がんばりコーナー</h2>${cheerCard(attempts, stats.goals)}</section>
    </div>`;
  const topics = stats.topics || {};
  const done = Object.values(topics).reduce((n, t) => n + t.attempts, 0);
  if (!done) {
    app.innerHTML = `${top}<div class="card"><p class="muted">さいしょの課題を「▶ はじめる」から解いてみよう！</p></div>`;
    return;
  }
  const weakAll = Object.entries(topics).filter(([, t]) => t.weak).sort(([, a], [, b]) => a.mastery - b.mastery);
  app.innerHTML = `${top}
    ${weakTabs(topics, gradeQ)}
    <details class="card kid-more"><summary>くわしく見る（目標・正答率・分野ごと）</summary>
    ${goalCard(stats.goals, { gradeQ })}
    <div class="card"><div>${activityLine(attempts)}</div>
      <div class="muted">解答 ${done} 問 · 弱点分野 ${weakAll.length}
        ${gf ? `· <span class="badge">小${gf}までの問題で練習</span>` : ''}</div>
      <h3>週ごとの正答率</h3>${weeklyChart(stats.weekly)}
    </div>
    ${subjects.filter((s) => Object.values(topics).some((t) => t.subject === s)).map((s) => {
      const rows = Object.entries(topics).filter(([, t]) => t.subject === s)
        .sort(([, a], [, b]) => (a.mastery ?? 2) - (b.mastery ?? 2));
      const summ = stats.subjects?.[s] || {};
      const weak = rows.filter(([, t]) => t.weak).map(([t]) => t);
      return `<div class="card">
        <div class="big-head"><h2 style="margin:0">${SUBJ[s]}</h2><span class="muted">正答率 ${pct(summ.accuracy)} · ${summ.attempts || 0} 問</span>
          <span style="margin-left:auto"><a class="button primary" href="#/practice/${s}?weak=1${gradeQ}">${weak.length ? '弱点練習を始める' : '練習する'}</a></span></div>
        <table><tr><th>分野</th><th>正解 / 解答</th><th>習熟度</th><th>連続正解</th><th>問題数</th><th></th></tr>
        ${rows.map(([t, v]) => `<tr class="${v.weak ? 'weak' : ''}">
          <td>${esc(t)}${v.grade ? ` <small class="muted">小${v.grade}</small>` : ''}</td>
          <td>${v.correct} / ${v.attempts}${v.pending ? ` <small class="warn">(?${v.pending})</small>` : ''}</td>
          <td><div class="bar"><div style="width:${Math.round((v.mastery || 0) * 100)}%"></div></div> ${pct(v.mastery)}${v.confident ? '' : ' <small class="muted">少</small>'}</td>
          <td>${v.streak}</td>
          <td class="muted">${pool[`${s}|${t}`] || 0}</td>
          <td><a href="#/practice/${s}?topic=${encodeURIComponent(t)}${gradeQ}">練習</a></td></tr>`).join('')}
        </table></div>`;
    }).join('')}
    <div class="card"><h2>まだ解いていない分野</h2><div class="chips">${
      Object.entries(pool).filter(([k]) => !topics[k.split('|')[1]]).sort().map(([k, n]) => {
        const [s, t] = k.split('|');
        return `<a class="chip" href="#/practice/${s}?topic=${encodeURIComponent(t)}${gradeQ}">${SUBJ[s]} · ${esc(t)} <small>${n}問</small></a>`;
      }).join('') || '<span class="muted">なし</span>'}</div></div>
    </details>`;
  bindWeakTabs(app);
}

const SUBJECT_CLS = { math: 's-math', japanese: 's-japanese', science: 's-science', social: 's-social' };
const SUBJECT_ICON = { math: '🧮', japanese: '📖', science: '🔬', social: '🌏' };

/**
 * にがてを練習しよう, one tab per 教科: that 教科's weak 分野 as big practice buttons (weakest first);
 * a 教科 without weak 分野 shows its 3 lowest ones as 「もう少し」. The 教科 with most weak 分野 opens first.
 */
export function weakTabs(topics, gradeQ = '') {
  const subs = ['math', 'japanese', 'science', 'social'].filter((k) => Object.values(topics).some((t) => t.subject === k && t.mastery != null));
  if (!subs.length) return '';
  const of = (k) => Object.entries(topics).filter(([, t]) => t.subject === k && t.mastery != null).sort(([, a], [, b]) => a.mastery - b.mastery);
  const weakN = (k) => of(k).filter(([, t]) => t.weak).length;
  const first = [...subs].sort((a, b) => weakN(b) - weakN(a))[0];
  const btn = (k, [t, v]) => `<a class="kid-weak-btn ${SUBJECT_CLS[k]}" href="#/practice/${k}?topic=${encodeURIComponent(t)}${gradeQ}">${esc(t)} <small>${pct(v.mastery)}</small></a>`;
  const panel = (k) => {
    const weak = of(k).filter(([, t]) => t.weak);
    return `<div class="kid-tab-panel" data-panel="${k}" ${k === first ? '' : 'hidden'}>${weak.length
      ? `<div class="kid-weak-list">${weak.map((r) => btn(k, r)).join('')}</div>`
      : `<p class="ok">${SUBJ[k]}は にがてな分野がないよ 🎉</p><p class="muted small">もう少しでもっと強くなれる分野</p>
        <div class="kid-weak-list">${of(k).slice(0, 3).map((r) => btn(k, r)).join('')}</div>`}
      <p><a class="kid-go-all ${SUBJECT_CLS[k]}" href="#/practice/${k}?weak=1${gradeQ}">${SUBJECT_ICON[k]} ${SUBJ[k]}の弱点練習をはじめる</a></p></div>`;
  };
  return `<div class="card kid-weak"><h2 class="kid-h">💪 にがてを練習しよう</h2>
    <div class="kid-tabs" role="tablist">${subs.map((k) => `<button role="tab" class="kid-tab ${SUBJECT_CLS[k]} ${k === first ? 'on' : ''}" data-tab="${k}">
      ${SUBJECT_ICON[k]} ${SUBJ[k]}${weakN(k) ? ` <span class="kid-tab-n">${weakN(k)}</span>` : ''}</button>`).join('')}</div>
    ${subs.map(panel).join('')}</div>`;
}

/** Tab switching for weakTabs (no re-render). */
export function bindWeakTabs(root) {
  for (const b of root.querySelectorAll('.kid-tab[data-tab]')) {
    b.onclick = () => {
      for (const x of root.querySelectorAll('.kid-tab')) x.classList.toggle('on', x === b);
      for (const p of root.querySelectorAll('.kid-tab-panel')) p.hidden = p.dataset.panel !== b.dataset.tab;
    };
  }
}

/** 来週の課題 (先取りOK) once this week is all done. */
function nextWeek(goals, subjectOf) {
  const nx = goals?.next;
  if (!nx?.assignments?.items?.length) return '';
  return `<h2 class="kid-h">🚀 来週の分も先にできるよ</h2>${taskCards({ ...nx, weekStart: nx.weekStart }, subjectOf)}`;
}
