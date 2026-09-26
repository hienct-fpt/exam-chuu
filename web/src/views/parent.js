import { currentUser, listChildren, listStudentAttempts, listPendingAttempts, getTopicStats, loadIndex,
  createInvite, listInvites, deleteInvite, unlinkChild, resetChildPassword } from '../api.js';
import { weeklyChart } from './dashboard.js';

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
      listPendingAttempts(s.uid), listStudentAttempts(s.uid, 20), getTopicStats(s.uid)]);
    return { s, pending, recent, stats };
  }));
  const queue = data.flatMap(({ s, pending }) => pending.map((a) => ({ s, a })))
    .sort((x, y) => String(x.a.submittedAt || '').localeCompare(String(y.a.submittedAt || '')));
  const pendingTotal = queue.reduce((n, { a }) => n + (a.pendingCount || 0), 0);

  app.innerHTML = `
    <div class="card"><h1>保護者ページ</h1>
      <div class="muted">連携中の子ども ${kids.length} 人 · 採点待ち ${queue.length} 回分 (${pendingTotal} 問)</div></div>
    ${inviteCard(invites)}
    ${kids.length ? '' : '<div class="card muted">まだ連携している子どもがいません。上の招待コードで追加してください。</div>'}
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
    ${data.map(({ s, recent, stats }) => {
      const graded = recent.filter((a) => a.status === 'graded');
      const avg = graded.length ? graded.reduce((n, a) => n + (a.percent || 0), 0) / graded.length / 100 : null;
      const last = recent[0];
      const weak = weakTopics(stats);
      return `<div class="card">
        <div class="big-head"><h2 style="margin:0">${esc(s.name)}</h2><span class="muted">${s.loginId ? `ID: ${esc(s.loginId)}` : esc(s.email || '')}</span>
          <span style="margin-left:auto"><a class="button" href="#/parent/${encodeURIComponent(s.uid)}">詳しく見る</a>
            <button data-unlink="${esc(s.uid)}" data-name="${esc(s.name)}">連携解除</button></span></div>
        <div class="muted">受験 ${stats.attemptCount || 0} 回 · 直近${graded.length}回の平均 ${pct(avg)}
          · 最終 ${last ? `${when(last.startedAt)} (${esc(name(last))})` : 'なし'}</div>
        <div class="chips">${Object.entries(SUBJ).filter(([k]) => stats.subjects?.[k]).map(([k, label]) =>
          `<span class="chip">${label} ${pct(stats.subjects[k].accuracy)} <small class="muted">${stats.subjects[k].attempts}問</small></span>`).join('')}</div>
        ${weak.length ? `<div>弱点: ${weak.map(([t, v]) => `<span class="chip weak">${esc(t)} <small>${pct(v.mastery)}</small></span>`).join(' ')}</div>` : ''}
      </div>`;
    }).join('')}`;
  bindInviteCard(app, () => renderOverview(app));
}

async function renderChild(app, uid) {
  const kids = await listChildren();
  const s = kids.find((k) => k.uid === uid);
  if (!s) {
    app.innerHTML = '<div class="card"><p>この生徒とは連携していません。</p><a href="#/parent">← 保護者ページ</a></div>';
    return;
  }
  const [name, attempts, stats] = await Promise.all([attemptNamer(), listStudentAttempts(uid, 100), getTopicStats(uid)]);
  const weak = weakTopics(stats, 10);
  const pendingN = attempts.filter((a) => a.status === 'graded' && a.pendingCount > 0).length;
  const onlyPending = (a) => a.status === 'graded' && a.pendingCount > 0;

  app.innerHTML = `
    <div class="card"><p><a href="#/parent">← 保護者ページ</a></p>
      <h1>${esc(s.name)} <small class="muted">${s.loginId ? `ログインID: ${esc(s.loginId)}` : esc(s.email || '')}</small></h1>
      ${s.loginId ? '<p><button id="reset-pw">パスワードを変更</button></p>' : ''}
      <div class="muted">受験 ${stats.attemptCount || 0} 回 · 採点待ち ${pendingN} 回分</div>
      <h3>週ごとの正答率</h3>${weeklyChart(stats.weekly) || '<p class="muted">データなし</p>'}
    </div>
    <div class="two-col">
      <div class="card"><h2>教科別</h2><table><tr><th>教科</th><th>正答率</th><th>解答数</th></tr>
        ${Object.entries(SUBJ).filter(([k]) => stats.subjects?.[k]).map(([k, label]) =>
          `<tr><td>${label}</td><td>${pct(stats.subjects[k].accuracy)}</td><td>${stats.subjects[k].attempts}</td></tr>`).join('')
          || '<tr><td colspan="3" class="muted">まだありません</td></tr>'}</table></div>
      <div class="card"><h2>弱点分野 <small class="muted">(習熟度の低い順)</small></h2><table><tr><th>分野</th><th>正解 / 解答</th><th>習熟度</th></tr>
        ${weak.map(([t, v]) => `<tr class="weak"><td>${esc(t)} <small class="muted">${SUBJ[v.subject] || ''}</small></td>
          <td>${v.correct} / ${v.attempts}</td><td>${pct(v.mastery)}</td></tr>`).join('')
          || '<tr><td colspan="3" class="ok">弱点分野はありません</td></tr>'}</table></div>
    </div>
    <div class="card"><h2>受験記録</h2>
      <label class="muted"><input type="checkbox" id="onlypending"> 採点待ちのみ表示</label>
      ${attempts.length ? `<table id="attempts"><tr><th>日時</th><th>試験 / 練習</th><th>範囲</th><th>状態</th><th>得点</th><th></th></tr>
      ${attempts.map((a) => `<tr data-pending="${onlyPending(a)}">
        <td>${when(a.startedAt)}</td>
        <td>${esc(name(a))}</td>
        <td>${a.gradeFilter ? `<span class="badge">小${a.gradeFilter}まで</span>` : '<span class="badge">全問</span>'}</td>
        <td><span class="badge ${a.status}">${STATUS[a.status] || a.status}</span>${a.pendingCount ? ` <small class="warn">採点待ち${a.pendingCount}</small>` : ''}</td>
        <td>${a.status === 'graded' ? `${a.score} / ${a.max} (${a.percent}%)` : ''}</td>
        <td>${a.status === 'in_progress' ? '' : `<a href="${resultLink(uid, a)}">${onlyPending(a) ? '採点する' : '結果'}</a>`}</td>
      </tr>`).join('')}</table>` : '<p class="muted">まだ受験していません。</p>'}
    </div>`;
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
    for (const tr of app.querySelectorAll('#attempts tr[data-pending]')) tr.style.display = cb.checked && tr.dataset.pending !== 'true' ? 'none' : '';
  };
}
