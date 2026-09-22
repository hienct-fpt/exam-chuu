// Mock backend: attempts in localStorage, grading via scripts/dev_server.py (POST /api/grade).
const KEY = 'exam-chuu.attempts';
const user = { uid: 'local', name: 'テスト生徒', email: 'local@example.com' };
const load = () => JSON.parse(localStorage.getItem(KEY) || '{}');
const save = (all) => localStorage.setItem(KEY, JSON.stringify(all));
const watchers = new Map();
const notify = (id) => (watchers.get(id) || []).forEach((cb) => cb(load()[id]));

export function currentUser() { return user; }
export function onAuth(cb) { setTimeout(() => cb(user), 0); return () => {}; }
export async function signIn() {}
export async function signOut() {}

export async function createAttempt(examId, mode = 'exam') {
  const all = load();
  const id = 'a' + Date.now().toString(36);
  all[id] = { id, examId, mode, status: 'in_progress', answers: {}, startedAt: new Date().toISOString() };
  save(all);
  return id;
}
export async function saveAnswers(id, answers) {
  const all = load(); all[id].answers = answers; all[id].updatedAt = new Date().toISOString(); save(all);
}
export async function submitAttempt(id, answers) {
  const all = load();
  Object.assign(all[id], { answers, status: 'submitted', submittedAt: new Date().toISOString() });
  save(all); notify(id);
  const r = await fetch('/api/grade', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ examId: all[id].examId, answers, attemptId: id, studentName: user.name }),
  });
  const cur = load();
  if (!r.ok) { cur[id].status = 'error'; cur[id].error = `dev_server ${r.status}`; save(cur); notify(id); return; }
  const { result, emailHtml, emailSubject } = await r.json();
  Object.assign(cur[id], { status: 'graded', result, score: result.score, max: result.max, percent: result.percent,
    gradedAt: new Date().toISOString(), emailHtml, emailSubject });
  save(cur); notify(id);
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
export async function findInProgress(examId) {
  return Object.values(load()).find((a) => a.examId === examId && a.status === 'in_progress') || null;
}
