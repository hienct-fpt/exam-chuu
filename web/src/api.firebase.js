import { initializeApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider, signInWithPopup, signInWithEmailAndPassword, signOut as fbSignOut, onAuthStateChanged } from 'firebase/auth';
import {
  getFirestore, doc, collection, addDoc, setDoc, updateDoc, deleteDoc, getDoc, getDocs, onSnapshot,
  query, where, orderBy, limit, serverTimestamp, Timestamp,
} from 'firebase/firestore';
import { getFunctions, httpsCallable } from 'firebase/functions';

const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
});
const auth = getAuth(app);
const db = getFirestore(app);
const functions = getFunctions(app, 'asia-northeast1'); // same region as functions/main.py set_global_options

let user = null;
export function currentUser() { return user; }

export function onAuth(cb) {
  return onAuthStateChanged(auth, async (u) => {
    if (u) {
      const token = await u.getIdTokenResult();
      user = { uid: u.uid, name: u.displayName || u.email, email: u.email, photo: u.photoURL, admin: token.claims.admin === true };
      const ref = doc(db, 'students', u.uid);
      const snap = await getDoc(ref);
      if (!snap.exists()) await setDoc(ref, { name: u.displayName || u.email, email: u.email, createdAt: serverTimestamp() });
    } else {
      user = null;
    }
    cb(user);
  });
}
export async function signIn() { await signInWithPopup(auth, new GoogleAuthProvider()); }

// Login-ID accounts (children without Google): must match CHILD_EMAIL_DOMAIN in functions/main.py.
const CHILD_EMAIL_DOMAIN = 'kids.exam-chuu.invalid';
const AUTH_MSG = { 'auth/invalid-credential': 'ログインIDまたはパスワードが違います', 'auth/too-many-requests': 'しばらく待ってからもう一度お試しください' };
export async function signInWithLoginId(loginId, password) {
  try {
    await signInWithEmailAndPassword(auth, `${loginId.trim().toLowerCase()}@${CHILD_EMAIL_DOMAIN}`, password);
  } catch (e) { throw new Error(AUTH_MSG[e.code] || e.message); }
}
/** Signed-out child on the parent's invite link: create the account (linked by the function), then sign in. */
export async function createChildAccount({ code, loginId, password, name }) {
  const { data } = await httpsCallable(functions, 'create_child_account')({ code, loginId, password, name });
  await signInWithLoginId(loginId, password);
  return data;
}
export async function resetChildPassword(childUid, password) {
  await httpsCallable(functions, 'reset_child_password')({ childUid, password });
}
export async function signOut() { await fbSignOut(auth); }

// `uid` defaults to the signed-in user; the parent (admin claim) passes a child's uid.
const attempts = (uid = user.uid) => collection(db, 'students', uid, 'attempts');
const attemptRef = (id, uid = user.uid) => doc(db, 'students', uid || user.uid, 'attempts', id);

function norm(snap) {
  const d = snap.data();
  const ts = (v) => (v && v.toDate ? v.toDate().toISOString() : v || null);
  return { id: snap.id, ...d, startedAt: ts(d.startedAt), submittedAt: ts(d.submittedAt), gradedAt: ts(d.gradedAt) };
}

/** extra: { itemIds, gradeFilter, timeLimitMin, items (practice: full item ids), topics, title, subject } */
export async function createAttempt(examId, mode = 'exam', extra = {}) {
  const ref = await addDoc(attempts(), {
    examId: examId || null, mode, status: 'in_progress', answers: {}, manualGrades: {},
    itemIds: extra.itemIds || null, gradeFilter: extra.gradeFilter || null, timeLimitMin: extra.timeLimitMin || null,
    items: extra.items || null, topics: extra.topics || null, title: extra.title || null, subject: extra.subject || null,
    startedAt: serverTimestamp(), updatedAt: serverTimestamp(),
  });
  return ref.id;
}
export async function saveAnswers(attemptId, answers) {
  await updateDoc(attemptRef(attemptId), { answers, updatedAt: serverTimestamp() });
}
export async function submitAttempt(attemptId, answers) {
  await updateDoc(attemptRef(attemptId), { answers, status: 'submitted', submittedAt: serverTimestamp(), updatedAt: serverTimestamp() });
}
export async function setManualGrade(attemptId, sid, correct, uid = null) {
  await updateDoc(attemptRef(attemptId, uid), { [`manualGrades.${sid}`]: correct, updatedAt: serverTimestamp() });
}
export function watchAttempt(attemptId, cb, uid = null) {
  return onSnapshot(attemptRef(attemptId, uid), (snap) => cb(snap.exists() ? norm(snap) : null));
}
export async function getAttempt(attemptId) {
  const snap = await getDoc(attemptRef(attemptId));
  return snap.exists() ? norm(snap) : null;
}
export async function listAttempts(max = 50) {
  const q = query(attempts(), orderBy('startedAt', 'desc'), limit(max));
  return (await getDocs(q)).docs.map(norm);
}
/** Children linked to the signed-in parent (students/{me}.children, written by redeem_invite). */
export async function listChildren() {
  const me = await getDoc(doc(db, 'students', user.uid));
  const ids = (me.exists() && me.data().children) || [];
  const snaps = await Promise.all(ids.map((id) => getDoc(doc(db, 'students', id))));
  return snaps.filter((s) => s.exists()).map((s) => ({ uid: s.id, ...s.data() }));
}
/** Parents the signed-in child is linked to: [{uid, name}]. */
export async function listMyParents() {
  const me = await getDoc(doc(db, 'students', user.uid));
  const d = me.exists() ? me.data() : {};
  return (d.parents || []).map((uid) => ({ uid, name: d.parentNames?.[uid] || '保護者' }));
}

const INVITE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no 0/O/1/I
const INVITE_TTL_MS = 24 * 3600 * 1000;
/** Parent: new single-use invite code, valid 24h. Retries on the (unlikely) code collision, which the rules reject. */
export async function createInvite() {
  for (let tries = 0; tries < 5; tries++) {
    const code = Array.from(crypto.getRandomValues(new Uint32Array(6)), (n) => INVITE_CHARS[n % INVITE_CHARS.length]).join('');
    try {
      await setDoc(doc(db, 'invites', code), { parentUid: user.uid, parentName: user.name, createdAt: serverTimestamp(),
        expiresAt: Timestamp.fromMillis(Date.now() + INVITE_TTL_MS) });
      return code;
    } catch (e) { if (e.code !== 'permission-denied' || tries === 4) throw e; }
  }
}
export async function listInvites() {
  const s = await getDocs(query(collection(db, 'invites'), where('parentUid', '==', user.uid)));
  return s.docs.map((d) => ({ code: d.id, expiresAt: d.data().expiresAt?.toDate().toISOString() }))
    .filter((i) => i.expiresAt && i.expiresAt > new Date().toISOString());
}
export async function deleteInvite(code) { await deleteDoc(doc(db, 'invites', code)); }
/** Child: redeem a parent's code. Returns { parentName }. */
export async function redeemInvite(code) {
  return (await httpsCallable(functions, 'redeem_invite')({ code })).data;
}
export async function unlinkChild(childUid) {
  await httpsCallable(functions, 'unlink_child')({ childUid });
}
export async function listStudentAttempts(uid, max = 100) {
  const q = query(attempts(uid), orderBy('startedAt', 'desc'), limit(max));
  return (await getDocs(q)).docs.map(norm);
}
/** Graded attempts still waiting for the parent's ○/× on 記述・作図 items (single-field index, no composite needed). */
export async function listPendingAttempts(uid) {
  const q = query(attempts(uid), where('pendingCount', '>', 0), limit(50));
  return (await getDocs(q)).docs.map(norm).filter((a) => a.status === 'graded');
}
export async function findInProgress(examId, gradeFilter = null) {
  const q = query(attempts(), where('examId', '==', examId), where('status', '==', 'in_progress'), limit(10));
  const s = await getDocs(q);
  return s.docs.map(norm).find((a) => (a.gradeFilter || null) === (gradeFilter || null) && a.mode !== 'practice') || null;
}
/** students/{uid}/topicStats/summary, maintained by the Cloud Function after every grading. */
export async function getTopicStats(uid = null) {
  const snap = await getDoc(doc(db, 'students', uid || user.uid, 'topicStats', 'summary'));
  if (!snap.exists()) return { topics: {}, subjects: {}, weekly: [], itemHistory: {}, attemptCount: 0, suggestions: {} };
  const d = snap.data();
  return { suggestions: {}, ...d };
}
