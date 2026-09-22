import { listAttempts, loadIndex } from '../api.js';

export async function renderHistory({ app }) {
  const [attempts, index] = await Promise.all([listAttempts(100), loadIndex()]);
  const meta = Object.fromEntries(index.map((e) => [e.id, e]));
  const name = (a) => {
    if (a.mode === 'practice' && a.items) return a.title || `練習 (${a.items.length}問)`;
    const e = meta[a.examId]; return e ? `${e.year}年度 ${e.session_label} ${e.subject_label}` : a.examId;
  };
  const badge = (s) => ({ graded: '採点済', submitted: '採点中', in_progress: '途中', error: 'エラー' }[s] || s);
  const scope = (a) => (a.gradeFilter ? `<span class="badge">小${a.gradeFilter}まで</span>` : '<span class="badge">全問</span>');
  const resume = (a) => (a.mode === 'practice' && a.items ? `#/attempt/${a.id}` : `#/exam/${a.examId}${a.gradeFilter ? `?g=${a.gradeFilter}` : ''}`);
  app.innerHTML = `<div class="card"><h1>履歴</h1>
    ${attempts.length ? `<table><tr><th>日時</th><th>試験 / 練習</th><th>範囲</th><th>状態</th><th>得点</th><th></th></tr>
    ${attempts.map((a) => `<tr>
      <td>${a.startedAt ? new Date(a.startedAt).toLocaleString('ja-JP') : ''}</td>
      <td>${name(a)}</td>
      <td>${scope(a)}</td>
      <td><span class="badge ${a.status}">${badge(a.status)}</span>${a.pendingCount ? ` <small class="warn">採点待ち${a.pendingCount}</small>` : ''}</td>
      <td>${a.status === 'graded' ? `${a.score} / ${a.max} (${a.percent}%)` : ''}</td>
      <td>${a.status === 'in_progress' ? `<a href="${resume(a)}">続ける</a>` : `<a href="#/result/${a.id}">結果</a>`}</td>
    </tr>`).join('')}</table>` : '<p class="muted">まだ受験していません。</p>'}
  </div>`;
}
