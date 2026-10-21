// Mock backend: attempts in localStorage, grading + analytics via scripts/dev_server.py.
const KEY = 'exam-chuu.attempts';
// Role of the single mock user: 保護者 (admin: ○/× buttons, 保護者 page) or 生徒. Start value from VITE_MOCK_ADMIN
// (dev:mock = parent, dev:mock:student = student); the topbar switch (setMockRole) overrides it in localStorage.
const ROLE = 'exam-chuu.mockRole';
const storedRole = localStorage.getItem(ROLE);
const user = { uid: 'local', name: 'テスト生徒', email: 'local@example.com',
  admin: storedRole ? storedRole === 'parent' : import.meta.env.VITE_MOCK_ADMIN !== '0' };
const load = () => JSON.parse(localStorage.getItem(KEY) || '{}');
const save = (all) => localStorage.setItem(KEY, JSON.stringify(all));
const watchers = new Map();
const notify = (id) => (watchers.get(id) || []).forEach((cb) => cb(load()[id]));

export function currentUser() { return user; }
/** Mock only: switch between the parent and the student view (same local data). Caller reloads the page. */
export function setMockRole(role) { localStorage.setItem(ROLE, role); }
export function onAuth(cb) { setTimeout(() => cb(user), 0); return () => {}; }
export async function signIn() {}
export async function signOut() {}

/** extra: { itemIds, gradeFilter, timeLimitMin, items (practice: full ids), topics, title } */
export async function createAttempt(examId, mode = 'exam', extra = {}) {
  const all = load();
  const id = 'a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  all[id] = { id, examId: examId || null, mode, status: 'in_progress', answers: {}, startedAt: new Date().toISOString(),
    itemIds: extra.itemIds || null, gradeFilter: extra.gradeFilter || null, timeLimitMin: extra.timeLimitMin || null,
    items: extra.items || null, topics: extra.topics || null, title: extra.title || null, subject: extra.subject || null, redoOf: extra.redoOf || null, manualGrades: {} };
  save(all);
  return id;
}
export async function saveAnswers(id, answers, meta = {}) {
  const all = load(); all[id].answers = answers; all[id].updatedAt = new Date().toISOString();
  if (Number.isFinite(meta.activeSec)) all[id].activeSec = meta.activeSec;
  save(all);
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
  const { result } = await r.json();
  Object.assign(cur[id], { status: 'graded', result, score: result.score, max: result.max, percent: result.percent,
    pendingCount: result.pendingCount, gradedAt: cur[id].gradedAt || new Date().toISOString() });
  save(cur); notify(id);
}

export async function submitAttempt(id, answers, meta = {}) {
  const all = load();
  Object.assign(all[id], { answers, status: 'submitted', submittedAt: new Date().toISOString(),
    ...(Number.isFinite(meta.activeSec) ? { activeSec: meta.activeSec } : {}) });
  save(all); notify(id);
  await gradeNow(id);
}
export async function setManualGrade(id, sid, correct) {
  const all = load();
  all[id].manualGrades = { ...(all[id].manualGrades || {}), [sid]: correct };
  save(all);
  await gradeNow(id);
}
// Mock has a single local student; the `uid` args of the parent views are accepted and ignored.
// Invite codes + the link flag live in localStorage, so dev:mock (parent) and dev:mock:student share them.
const INV = 'exam-chuu.invites', LINK = 'exam-chuu.linked';
const invites = () => JSON.parse(localStorage.getItem(INV) || '{}');
const linked = () => localStorage.getItem(LINK) === '1';
// A second child (mock only, no attempts of its own) to try the screens of a parent with several children.
const KID2 = 'exam-chuu.mockKid2';
const kid2 = { uid: 'local2', name: 'テスト生徒2', email: 'local2@example.com' };
export const hasMockKid2 = () => localStorage.getItem(KID2) === '1';
export function setMockKid2(on) { if (on) localStorage.setItem(KID2, '1'); else localStorage.removeItem(KID2); }
const isKid2 = (uid) => uid === kid2.uid;
export async function listChildren() {
  return [...(linked() ? [{ uid: user.uid, name: user.name, email: user.email }] : []), ...(hasMockKid2() ? [kid2] : [])];
}
export async function listMyParents() { return linked() ? [{ uid: 'mock-parent', name: '保護者 (mock)' }] : []; }
export async function createInvite() {
  const code = Math.random().toString(36).slice(2, 8).toUpperCase();
  localStorage.setItem(INV, JSON.stringify({ ...invites(), [code]: new Date(Date.now() + 24 * 3600 * 1000).toISOString() }));
  return code;
}
export async function listInvites() {
  const now = new Date().toISOString();
  return Object.entries(invites()).filter(([, exp]) => exp > now).map(([code, expiresAt]) => ({ code, expiresAt }));
}
export async function deleteInvite(code) {
  const all = invites(); delete all[code]; localStorage.setItem(INV, JSON.stringify(all));
}
export async function redeemInvite(code) {
  const exp = invites()[String(code).trim().toUpperCase()];
  if (!exp) throw new Error('招待コードが見つかりません');
  if (exp < new Date().toISOString()) throw new Error('招待コードの有効期限が切れています');
  await deleteInvite(String(code).trim().toUpperCase());
  localStorage.setItem(LINK, '1');
  return { parentName: '保護者 (mock)' };
}
export async function unlinkChild(uid) { if (isKid2(uid)) setMockKid2(false); else localStorage.removeItem(LINK); }
// Mock is always signed in, so the signed-out sign-up screen never shows; these keep the API surface identical.
export async function signInWithLoginId() {}
export async function createChildAccount({ code }) { return redeemInvite(code); }
export async function resetChildPassword() {}
export async function getAnswerKey(examId) {
  const r = await fetch(`/api/answers/${encodeURIComponent(examId)}`);
  if (!r.ok) throw new Error(`dev_server ${r.status}`);
  return (await r.json()).items || {};
}
export async function listStudentAttempts(uid, max = 100) { return isKid2(uid) ? [] : (await listAttempts()).slice(0, max); }
export async function listPendingAttempts(uid) {
  if (isKid2(uid)) return [];
  return Object.values(load()).filter((a) => a.status === 'graded' && a.pendingCount > 0);
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
export async function getTopicStats(uid = null) {
  const attempts = isKid2(uid) ? [] : Object.values(load()).filter((a) => a.status === 'graded');
  const r = await fetch('/api/stats', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attempts, studentName: isKid2(uid) ? kid2.name : user.name }) });
  if (!r.ok) throw new Error(`dev_server ${r.status}`);
  return r.json();
}
