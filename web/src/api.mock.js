// Mock backend: attempts in localStorage, grading + analytics via scripts/dev_server.py.
const KEY = 'exam-chuu.attempts';
const user = { uid: 'local', name: 'テスト生徒', email: 'local@example.com', admin: true };
const load = () => JSON.parse(localStorage.getItem(KEY) || '{}');
const save = (all) => localStorage.setItem(KEY, JSON.stringify(all));
const watchers = new Map();
const notify = (id) => (watchers.get(id) || []).forEach((cb) => cb(load()[id]));

export function currentUser() { return user; }
export function onAuth(cb) { setTimeout(() => cb(user), 0); return () => {}; }
export async function signIn() {}
export async function signOut() {}

/** extra: { itemIds, gradeFilter, timeLimitMin, items (practice: full ids), topics, title } */
export async function createAttempt(examId, mode = 'exam', extra = {}) {
  const all = load();
  const id = 'a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  all[id] = { id, examId: examId || null, mode, status: 'in_progress', answers: {}, startedAt: new Date().toISOString(),
    itemIds: extra.itemIds || null, gradeFilter: extra.gradeFilter || null, timeLimitMin: extra.timeLimitMin || null,
    items: extra.items || null, topics: extra.topics || null, title: extra.title || null, subject: extra.subject || null, manualGrades: {} };
  save(all);
  return id;
}
export async function saveAnswers(id, answers) {
  const all = load(); all[id].answers = answers; all[id].updatedAt = new Date().toISOString(); save(all);
}

async function gradeNow(id) {
  const a = load()[id];
  const r = await fetch('/api/grade', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ examId: a.examId, mode: a.mode, items: a.items, topics: a.topics, answers: a.answers, attemptId: id,
      studentName: user.name, itemIds: a.itemIds, gradeFilter: a.gradeFilter, manualGrades: a.manualGrades || {} }),
  });
  const cur = load();
  if (!r.ok) { cur[id].status = 'error'; cur[id].error = `dev_server ${r.status}`; save(cur); notify(id); return; }
  const { result, emailHtml, emailSubject } = await r.json();
  Object.assign(cur[id], { status: 'graded', result, score: result.score, max: result.max, percent: result.percent,
    pendingCount: result.pendingCount, gradedAt: cur[id].gradedAt || new Date().toISOString(), emailHtml, emailSubject });
  save(cur); notify(id);
}

export async function submitAttempt(id, answers) {
  const all = load();
  Object.assign(all[id], { answers, status: 'submitted', submittedAt: new Date().toISOString() });
  save(all); notify(id);
  await gradeNow(id);
}
export async function setManualGrade(id, sid, correct) {
  const all = load();
  all[id].manualGrades = { ...(all[id].manualGrades || {}), [sid]: correct };
  save(all);
  await gradeNow(id);
}
export function watchAttempt(id, cb) {
  const list = watchers.get(id) || []; list.push(cb); watchers.set(id, list);
  setTimeout(() => cb(load()[id]), 0);
  return () => watchers.set(id, (watchers.get(id) || []).filter((f) => f !== cb));
}
export async function getAttempt(id) { return load()[id] || null; }
export async function listAttempts() {
  return Object.values(load()).sort((a, b) => (b.startedAt || '').localeCompare(a.startedAt || ''));
}
export async function findInProgress(examId, gradeFilter = null) {
  return Object.values(load()).find((a) => a.examId === examId && a.mode !== 'practice' && a.status === 'in_progress'
    && (a.gradeFilter || null) === (gradeFilter || null)) || null;
}
/** Topic mastery summary computed by dev_server from the graded attempts (mirrors students/{uid}/topicStats/summary). */
export async function getTopicStats(opts = {}) {
  const attempts = Object.values(load()).filter((a) => a.status === 'graded');
  const r = await fetch('/api/stats', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attempts, studentName: user.name, digest: Boolean(opts.digest) }) });
  if (!r.ok) throw new Error(`dev_server ${r.status}`);
  return r.json();
}
