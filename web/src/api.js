// Backend facade. Two implementations: Firebase (production) and mock (localStorage + scripts/dev_server.py).
const MOCK = import.meta.env.VITE_MOCK === '1';

let indexCache = null;
const bankCache = new Map();
export async function loadIndex() {
  if (!indexCache) indexCache = await (await fetch('/bank/index.json')).json();
  return indexCache;
}
export async function loadExam(examId) {
  if (!bankCache.has(examId)) {
    const r = await fetch(`/bank/${examId}.json`);
    if (!r.ok) throw new Error(`exam not found: ${examId}`);
    bankCache.set(examId, await r.json());
  }
  return bankCache.get(examId);
}
/** Display name of an exam / index entry: real past papers "2024年度 2/1入試", min-san sets carry their own title. */
export const examTitle = (b) => b.title || `${b.year}年度 ${b.session_label}`;
/** All items of all exams of a subject (or all subjects), each tagged with exam meta. */
export async function loadAllItems(subject = null) {
  const index = await loadIndex();
  const exams = index.filter((e) => !subject || e.subject === subject);
  const banks = await Promise.all(exams.map((e) => loadExam(e.id)));
  const items = [];
  for (const b of banks) for (const it of b.items) items.push({ ...it, subject: b.subject, examLabel: examTitle(b) });
  return { items, banks: Object.fromEntries(banks.map((b) => [b.id, b])) };
}

const impl = MOCK ? await import('./api.mock.js') : await import('./api.firebase.js');
export const { onAuth, signIn, signOut, currentUser, createAttempt, saveAnswers, submitAttempt, setManualGrade,
  watchAttempt, getAttempt, listAttempts, findInProgress, getTopicStats,
  listChildren, listMyParents, listStudentAttempts, listPendingAttempts,
  createInvite, listInvites, deleteInvite, redeemInvite, unlinkChild,
  signInWithLoginId, createChildAccount, resetChildPassword } = impl;
export const isMock = MOCK;
