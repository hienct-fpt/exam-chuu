import { listAttempts, loadIndex } from '../api.js';

export async function renderHistory({ app }) {
  const [attempts, index] = await Promise.all([listAttempts(100), loadIndex()]);
  const meta = Object.fromEntries(index.map((e) => [e.id, e]));
  const name = (id) => { const e = meta[id]; return e ? `${e.year}年度 ${e.session_label} ${e.subject_label}` : id; };
  const badge = (s) => ({ graded: '採点済', submitted: '採点中', in_progress: '途中', error: 'エラー' }[s] || s);
  app.innerHTML = `<div class="card"><h1>履歴</h1>
    ${attempts.length ? `<table><tr><th>日時</th><th>試験</th><th>状態</th><th>得点</th><th></th></tr>
    ${attempts.map((a) => `<tr>
      <td>${a.startedAt ? new Date(a.startedAt).toLocaleString('ja-JP') : ''}</td>
      <td>${name(a.examId)}</td>
      <td><span class="badge ${a.status}">${badge(a.status)}</span></td>
      <td>${a.status === 'graded' ? `${a.score} / ${a.max} (${a.percent}%)` : ''}</td>
      <td>${a.status === 'in_progress' ? `<a href="#/exam/${a.examId}">続ける</a>` : `<a href="#/result/${a.id}">結果</a>`}</td>
    </tr>`).join('')}</table>` : '<p class="muted">まだ受験していません。</p>'}
  </div>`;
}
