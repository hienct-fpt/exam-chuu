// Backend facade. Two implementations: Firebase (production) and mock (localStorage + scripts/dev_server.py).
const MOCK = import.meta.env.VITE_MOCK === '1';

export async function loadIndex() {
  const r = await fetch('/bank/index.json');
  return r.json();
}
export async function loadExam(examId) {
  const r = await fetch(`/bank/${examId}.json`);
  if (!r.ok) throw new Error(`exam not found: ${examId}`);
  return r.json();
}

const impl = MOCK ? await import('./api.mock.js') : await import('./api.firebase.js');
export const { onAuth, signIn, signOut, currentUser, createAttempt, saveAnswers, submitAttempt, setManualGrade,
  watchAttempt, getAttempt, listAttempts, findInProgress } = impl;
export const isMock = MOCK;
