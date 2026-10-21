import { isMock, hasMockKid2, setMockKid2, currentUser, listChildren, listStudentAttempts, listPendingAttempts, getTopicStats, loadIndex,
  createInvite, listInvites, deleteInvite, unlinkChild, resetChildPassword } from '../api.js';
import { weeklyChart } from './dashboard.js';
import { goalCard } from './goals.js';
import { activityLine, improvementCard } from '../activity.js';
import { kpiCards, weakAnalysis, subjectBreakdown, hensachiCard, kumiwakeCard } from '../parent-ui.js';
import { childPicker, bindChildPicker, setSelectedChild } from '../children.js';

// 保護者ページ (admin claim only): #/parent = grading queue + one card per child, #/parent/<uid> = one child's record.
const SUBJ = { math: '算数', science: '理科', social: '社会', japanese: '国語' };
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const when = (t) => (t ? new Date(t).toLocaleString('ja-JP', { dateStyle: 'short', timeStyle: 'short' }) : '');
const resultLink = (uid, a) => `#/result/${a.id}?uid=${encodeURIComponent(uid)}`;
const STATUS = { graded: '採点済', submitted: '採点中', in_progress: '途中', error: 'エラー' };

async function attemptNamer() {
  const index = await loadIndex();
  const meta = Object.fromEntries(index.map((e) => [e.id, e]));
  return (a) => {
    if (a.mode === 'practice' && a.items) return a.title || `練習 (${a.items.length}問)`;
    const e = meta[a.examId];
    return e ? `${e.school_name || ''} ${e.year}年度 ${e.session_label} ${e.subject_label}` : a.examId;
  };
}

/** Working time of an attempt in seconds: recorded activeSec, else ~ start→submit when that is plausible (older attempts). */
export function attemptSeconds(a) {
  if (Number.isFinite(a.activeSec) && a.activeSec > 0) return { sec: a.activeSec, approx: false };
  if (!a.startedAt || !a.submittedAt) return null;
  const sec = (Date.parse(a.submittedAt) - Date.parse(a.startedAt)) / 1000;
  return sec > 0 && sec <= 3 * 3600 ? { sec, approx: true } : null;   // longer = left open overnight, not working time
}
export const duration = (sec) => {
  const m = Math.max(1, Math.round(sec / 60));
  return m < 60 ? `${m}分` : `${Math.floor(m / 60)}時間${m % 60 ? `${m % 60}分` : ''}`;
};
const timeCell = (t) => (t ? `${t.approx ? '<span class="muted" title="開始〜提出の時間（作業時間の記録がない回）">約</span>' : ''}${duration(t.sec)}` : '—');

/** Attempts per 試験: a redo / practice set of one exam joins that exam; other practice sets are one group per title. */
export function groupAttempts(attempts, name) {
  const groups = new Map();
  for (const a of attempts) {
    const key = a.examId || a.redoOf || `practice:${a.title || name(a)}`;
    if (!groups.has(key)) groups.set(key, { key, label: a.examId || a.redoOf ? name({ ...a, examId: a.examId || a.redoOf, mode: 'exam', items: null }) : name(a), list: [] });
    groups.get(key).list.push(a);
  }
  for (const g of groups.values()) {
    g.list.sort((x, y) => String(x.startedAt || '').localeCompare(String(y.startedAt || '')));   // 1回目 first
    const times = g.list.map(attemptSeconds).filter(Boolean);
    g.totalSec = times.reduce((n, t) => n + t.sec, 0);
    g.approx = times.some((t) => t.approx);
    g.graded = g.list.filter((a) => a.status === 'graded');
    g.last = g.list[g.list.length - 1];
    g.pending = g.list.some((a) => a.status === 'graded' && a.pendingCount > 0);
  }
  return [...groups.values()].sort((x, y) => String(y.last.startedAt || '').localeCompare(String(x.last.startedAt || '')));
}

const KIND_OF = (a) => (a.redoOf ? 'やり直し' : a.mode === 'practice' ? '練習' : a.gradeFilter ? `小${a.gradeFilter}まで` : '全問');

function attemptLog(uid, groups) {
  if (!groups.length) return '<p class="muted">まだ受験していません。</p>';
  return groups.map((g) => `<details class="exam-log" data-pending="${g.pending}">
    <summary><b>${esc(g.label)}</b>
      <span class="muted">${g.list.length}回 · 合計 ${g.totalSec ? `${g.approx ? '約' : ''}${duration(g.totalSec)}` : '—'}</span>
      <span class="trend">${g.graded.map((a) => `<span class="chip ${a.percent < 60 ? 'weak' : ''}">${a.percent}%</span>`).join('<span class="muted">→</span>')}</span>
      ${g.pending ? '<span class="warn small">採点待ちあり</span>' : ''}</summary>
    <table><tr><th>回</th><th>日時</th><th>種類</th><th>作業時間</th><th>結果</th><th></th></tr>
    ${g.list.map((a, i) => `<tr>
      <td>${i + 1}回目</td><td class="nowrap">${when(a.startedAt)}</td>
      <td><span class="badge">${KIND_OF(a)}</span></td>
      <td class="nowrap">${timeCell(attemptSeconds(a))}${a.timeLimitMin ? ` <small class="muted">/ 制限${a.timeLimitMin}分</small>` : ''}</td>
      <td>${a.status === 'graded' ? `${a.score} / ${a.max} (${a.percent}%)${a.pendingCount ? ` <small class="warn">採点待ち${a.pendingCount}</small>` : ''}`
        : `<span class="badge ${a.status}">${STATUS[a.status] || a.status}</span>`}</td>
      <td>${a.status === 'in_progress' ? '' : `<a href="${resultLink(uid, a)}">${a.status === 'graded' && a.pendingCount > 0 ? '採点する' : '結果'}</a>`}</td>
    </tr>`).join('')}</table></details>`).join('');
}

function weakTopics(stats, n = 5) {
  return Object.entries(stats.topics || {}).filter(([, t]) => t.weak)
    .sort(([, a], [, b]) => a.mastery - b.mastery).slice(0, n);
}

export async function renderParent({ app }, arg) {
  if (!currentUser()?.admin) {
    app.innerHTML = '<div class="card"><h1>保護者ページ</h1><p class="muted">保護者アカウントでログインしてください。</p></div>';
    return;
  }
  app.innerHTML = '<div class="card">読み込み中…</div>';
  return arg ? renderChild(app, decodeURIComponent(arg)) : renderOverview(app);
}

/** 子どもを追加: the child signs in with their own account, opens #/join and enters the code. */
function inviteCard(invites) {
  const joinUrl = (code) => `${location.origin}${location.pathname}#/join/${code}`;
  return `<div class="card"><h2>子どもを追加</h2>
    <p class="muted">招待コードを作り、リンクをお子さんに送ります。お子さんはリンクを開いてログインIDとパスワードでアカウントを作ります
      （Google アカウントがあれば、ログイン後に「保護者と連携」でコードを入力しても可）。24時間有効・1回限り。</p>
    <button class="primary" id="new-invite">招待コードを作る</button>
    ${invites.length ? `<table><tr><th>コード</th><th>有効期限</th><th>リンク</th><th></th></tr>
      ${invites.map((i) => `<tr><td class="invite-code">${esc(i.code)}</td><td>${when(i.expiresAt)}</td>
        <td><button data-copy="${esc(joinUrl(i.code))}">リンクをコピー</button></td>
        <td><button data-del="${esc(i.code)}">取り消す</button></td></tr>`).join('')}</table>` : ''}
  </div>`;
}

function bindInviteCard(app, rerender) {
  app.querySelector('#new-invite').onclick = async (e) => {
    e.target.disabled = true;
    try { await createInvite(); rerender(); } catch (err) { alert('招待コードの作成に失敗: ' + err.message); e.target.disabled = false; }
  };
  for (const b of app.querySelectorAll('button[data-copy]')) {
    b.onclick = () => navigator.clipboard.writeText(b.dataset.copy).then(() => { b.textContent = 'コピーしました'; });
  }
  for (const b of app.querySelectorAll('button[data-del]')) {
    b.onclick = async () => { b.disabled = true; await deleteInvite(b.dataset.del); rerender(); };
  }
  for (const b of app.querySelectorAll('button[data-unlink]')) {
    b.onclick = async () => {
      if (!confirm(`${b.dataset.name} との連携を解除しますか？（お子さんの記録は消えません）`)) return;
      b.disabled = true;
      try { await unlinkChild(b.dataset.unlink); rerender(); } catch (err) { alert('解除に失敗: ' + err.message); b.disabled = false; }
    };
  }
}

async function renderOverview(app) {
  const [kids, name, invites] = await Promise.all([listChildren(), attemptNamer(), listInvites()]);
  const data = await Promise.all(kids.map(async (s) => {
    const [pending, recent, stats] = await Promise.all([
      listPendingAttempts(s.uid), listStudentAttempts(s.uid, 200), getTopicStats(s.uid)]);
    return { s, pending, recent, stats };
  }));
  const queue = data.flatMap(({ s, pending }) => pending.map((a) => ({ s, a })))
    .sort((x, y) => String(x.a.submittedAt || '').localeCompare(String(y.a.submittedAt || '')));
  const pendingTotal = queue.reduce((n, { a }) => n + (a.pendingCount || 0), 0);

  app.innerHTML = `
    <div class="card"><h1>保護者ページ</h1>
      <div class="muted">連携中の子ども ${kids.length} 人 · 採点待ち ${queue.length} 回分 (${pendingTotal} 問)</div></div>
    ${kids.length ? '' : '<div class="card muted">まだ連携している子どもがいません。下の「子どもを追加」で招待コードを作ってください。</div>'}
    ${data.map(({ s, recent, stats }) => {
      const last = recent[0];
      const weak = weakTopics(stats, 3);
      return `<div class="card p-child">
        <div class="p-head-row"><div><h2 style="margin:0">${esc(s.name)} <small class="muted">${s.loginId ? `ID: ${esc(s.loginId)}` : esc(s.email || '')}</small></h2>
          <div class="muted small">${activityLine(recent)} · 最終 ${last ? `${when(last.startedAt)} (${esc(name(last))})` : 'なし'}</div></div>
          <div class="p-head-side"><a class="button primary" href="#/parent/${encodeURIComponent(s.uid)}">詳しく見る</a>
            <button data-unlink="${esc(s.uid)}" data-name="${esc(s.name)}">連携解除</button></div></div>
        ${kpiCards(stats, recent, { compact: true })}
        ${weak.length ? `<div class="small">弱点: ${weak.map(([t, v]) => `<span class="chip weak">${esc(t)} <small>${pct(v.mastery)}</small></span>`).join(' ')}</div>` : ''}
      </div>`;
    }).join('')}
    <div class="card" ${kids.length ? '' : 'hidden'}><h2>採点待ち <small class="muted">(記述・作図 — 古い順)</small></h2>
      ${queue.length ? `<table><tr><th>提出</th>${kids.length > 1 ? '<th>生徒</th>' : ''}<th>試験 / 練習</th><th>仮の得点</th><th>採点待ち</th><th></th></tr>
      ${queue.map(({ s, a }) => `<tr>
        <td>${when(a.submittedAt)}</td>
        ${kids.length > 1 ? `<td>${esc(s.name)}</td>` : ''}
        <td>${esc(name(a))}</td>
        <td>${a.score} / ${a.max} (${a.percent}%)</td>
        <td class="warn">${a.pendingCount} 問</td>
        <td><a class="button primary" href="${resultLink(s.uid, a)}">採点する</a></td></tr>`).join('')}
      </table>` : '<p class="ok">採点待ちはありません。</p>'}
    </div>
    ${inviteCard(invites)}
    ${isMock ? `<div class="card muted small">mock: <button id="mock-kid2">${hasMockKid2() ? '2人目の子どもを外す' : '2人目の子ども（記録なし）を追加'}</button></div>` : ''}
`;
  bindInviteCard(app, () => renderOverview(app));
  const k2 = app.querySelector('#mock-kid2');
  if (k2) k2.onclick = () => { setMockKid2(!hasMockKid2()); renderOverview(app); };
}

async function renderChild(app, uid) {
  const kids = await listChildren();
  const s = kids.find((k) => k.uid === uid);
  if (!s) {
    app.innerHTML = '<div class="card"><p>この生徒とは連携していません。</p><a href="#/parent">← 保護者ページ</a></div>';
    return;
  }
  setSelectedChild(uid);   // 計画 opens the same child next
  const [name, attempts, stats] = await Promise.all([attemptNamer(), listStudentAttempts(uid, 300), getTopicStats(uid)]);
  const pendingN = attempts.filter((a) => a.status === 'graded' && a.pendingCount > 0).length;
  const groups = groupAttempts(attempts, name);
  const totalSec = groups.reduce((n, g) => n + g.totalSec, 0);

  app.innerHTML = `
    <div class="card p-head">
      <div class="p-head-row"><div>
        <p class="small"><a href="#/parent">← 保護者ページ</a></p>
        <h1>${esc(s.name)} <small class="muted">${s.loginId ? `ID: ${esc(s.loginId)}` : esc(s.email || '')}</small></h1>
        <div class="muted small">${activityLine(attempts)} · 採点待ち ${pendingN} 回分</div></div>
        <div class="p-head-side">${childPicker(kids, s, (k) => `#/parent/${encodeURIComponent(k.uid)}`)}
          ${s.loginId ? '<button id="reset-pw">パスワードを変更</button>' : ''}</div></div>
    </div>
    ${kpiCards(stats, attempts)}
    ${hensachiCard(stats.hensachi)}
    ${kumiwakeCard(stats.hensachi?.kumiwake)}
    <div class="p-grid">
      <div><div class="card p-card"><h2>週ごとの正答率</h2>${weeklyChart(stats.weekly) || '<p class="muted">データなし</p>'}</div>
        ${improvementCard(attempts)}
        <p class="muted small">今週の課題・全体計画・予定／実績のグラフは <a href="#/plan">計画</a> タブで見られます。</p></div>
      <div>${weakAnalysis(stats, attempts)}
        ${subjectBreakdown(stats, attempts)}
      </div>
    </div>
    <details class="card"><summary><b>今週の目標（教科別）</b></summary>${goalCard(stats.goals, { practice: false, tasks: false })}</details>
    <div class="card"><h2>受験記録 <small class="muted">${groups.length} 試験 · ${attempts.length} 回 · 合計 ${totalSec ? duration(totalSec) : '—'}</small></h2>
      <label class="muted"><input type="checkbox" id="onlypending"> 採点待ちのみ表示</label>
      ${attemptLog(uid, groups)}
    </div>`;
  bindChildPicker(app);
  const pw = app.querySelector('#reset-pw');
  if (pw) pw.onclick = async () => {
    const p = prompt(`${s.name} の新しいパスワード (6文字以上)`);
    if (p == null) return;
    if (p.length < 6) { alert('6文字以上にしてください'); return; }
    pw.disabled = true;
    try { await resetChildPassword(uid, p); alert('パスワードを変更しました。お子さんに伝えてください。'); }
    catch (err) { alert('変更に失敗: ' + err.message); }
    pw.disabled = false;
  };
  const cb = app.querySelector('#onlypending');
  if (cb) cb.onchange = () => {
    for (const d of app.querySelectorAll('details.exam-log')) d.style.display = cb.checked && d.dataset.pending !== 'true' ? 'none' : '';
  };
}
