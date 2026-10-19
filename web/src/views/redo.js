import { getTopicStats, loadExam, createAttempt, getAttempt, examTitle } from '../api.js';

// やり直し: #/redo/{examId} -> a practice attempt with the exam's items that are still wrong or blank
// (the list frozen in this week's 課題, else the live item history), graded like any practice set.
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** Wrong / blank item ids of one exam: this week's assignment if present, else the latest outcome per item. */
export function redoItems(stats, examId) {
  const a = (stats.goals?.assignments?.items || []).find((x) => x.kind === 'review' && x.examId === examId);
  if (a?.items?.length) return a.items;
  return Object.entries(stats.itemHistory || {})
    .filter(([id, h]) => id.startsWith(`${examId}#`) && !h.correct).map(([id]) => id).sort();
}

export async function renderRedo({ app, user }, examId) {
  examId = decodeURIComponent(String(examId || '').split('?')[0]);
  app.innerHTML = '<div class="card">準備中…</div>';
  const key = `redo:${user?.uid || 'anon'}:${examId}`;
  const prev = localStorage.getItem(key);
  if (prev) {   // resume the unfinished redo set instead of creating another one
    const a = await getAttempt(prev).catch(() => null);
    if (a && a.status === 'in_progress') { location.hash = `#/attempt/${prev}`; return; }
  }
  const [stats, exam] = await Promise.all([getTopicStats(), loadExam(examId)]);
  const items = redoItems(stats, examId);
  if (!items.length) {
    app.innerHTML = `<div class="card"><h1>やり直し</h1><p class="ok">${esc(exam.school_name)} ${esc(examTitle(exam))} ${esc(exam.subject_label)}：やり直す問題はありません 🎉</p><a href="#/dashboard">ダッシュボードへ</a></div>`;
    return;
  }
  const id = await createAttempt(null, 'practice', {
    items, subject: exam.subject, redoOf: examId,
    title: `やり直し ${exam.school_name} ${examTitle(exam)} ${exam.subject_label}`,
  });
  localStorage.setItem(key, id);
  location.hash = `#/attempt/${id}`;
}
