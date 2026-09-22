import { loadIndex, listAttempts } from '../api.js';

const SUBJ = { math: '算数', japanese: '国語', science: '理科', social: '社会' };

export async function renderHome({ app }) {
  const [index, attempts] = await Promise.all([loadIndex(), listAttempts(200)]);
  const best = {};
  for (const a of attempts) {
    if (a.status !== 'graded') continue;
    if (!best[a.examId] || a.percent > best[a.examId].percent) best[a.examId] = a;
  }
  const inProg = new Set(attempts.filter((a) => a.status === 'in_progress').map((a) => a.examId));
  app.innerHTML = `<h1>試験一覧</h1><div class="exam-grid">${index.map((e) => `
    <a class="card exam-tile" href="#/exam/${e.id}">
      <div class="muted">${e.school_name}</div>
      <h2>${e.year}年度 ${e.session_label} ${SUBJ[e.subject] || e.subject_label}</h2>
      <div class="muted">${e.item_count} 問 · ${e.time_limit_min} 分</div>
      <div style="margin-top:8px">
        ${inProg.has(e.id) ? '<span class="badge submitted">続きから</span> ' : ''}
        ${best[e.id] ? `<span class="badge graded">最高 ${best[e.id].score}/${best[e.id].max} (${best[e.id].percent}%)</span>` : '<span class="badge">未受験</span>'}
      </div>
    </a>`).join('')}</div>`;
}
