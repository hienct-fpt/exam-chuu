import { initializeApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut as fbSignOut, onAuthStateChanged } from 'firebase/auth';
import {
  getFirestore, doc, collection, addDoc, setDoc, updateDoc, getDoc, getDocs, onSnapshot,
  query, where, orderBy, limit, serverTimestamp,
} from 'firebase/firestore';

const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
});
const auth = getAuth(app);
const db = getFirestore(app);

let user = null;
export function currentUser() { return user; }

export function onAuth(cb) {
  return onAuthStateChanged(auth, async (u) => {
    user = u ? { uid: u.uid, name: u.displayName || u.email, email: u.email, photo: u.photoURL } : null;
    if (u) {
      // upsert profile (role/parentEmail are admin-managed; rules block the student from changing them)
      const ref = doc(db, 'students', u.uid);
      const snap = await getDoc(ref);
      if (!snap.exists()) await setDoc(ref, { name: u.displayName || u.email, email: u.email, createdAt: serverTimestamp() });
    }
    cb(user);
  });
}
export async function signIn() { await signInWithPopup(auth, new GoogleAuthProvider()); }
export async function signOut() { await fbSignOut(auth); }

const attempts = () => collection(db, 'students', user.uid, 'attempts');
const attemptRef = (id) => doc(db, 'students', user.uid, 'attempts', id);

function norm(snap) {
  const d = snap.data();
  const ts = (v) => (v && v.toDate ? v.toDate().toISOString() : v || null);
  return { id: snap.id, ...d, startedAt: ts(d.startedAt), submittedAt: ts(d.submittedAt), gradedAt: ts(d.gradedAt) };
}

export async function createAttempt(examId, mode = 'exam') {
  const ref = await addDoc(attempts(), { examId, mode, status: 'in_progress', answers: {}, startedAt: serverTimestamp(), updatedAt: serverTimestamp() });
  return ref.id;
}
export async function saveAnswers(attemptId, answers) {
  await updateDoc(attemptRef(attemptId), { answers, updatedAt: serverTimestamp() });
}
export async function submitAttempt(attemptId, answers) {
  await updateDoc(attemptRef(attemptId), { answers, status: 'submitted', submittedAt: serverTimestamp(), updatedAt: serverTimestamp() });
}
export function watchAttempt(attemptId, cb) {
  return onSnapshot(attemptRef(attemptId), (snap) => snap.exists() && cb(norm(snap)));
}
export async function getAttempt(attemptId) {
  const snap = await getDoc(attemptRef(attemptId));
  return snap.exists() ? norm(snap) : null;
}
export async function listAttempts(max = 50) {
  const q = query(attempts(), orderBy('startedAt', 'desc'), limit(max));
  return (await getDocs(q)).docs.map(norm);
}
export async function findInProgress(examId) {
  const q = query(attempts(), where('examId', '==', examId), where('status', '==', 'in_progress'), limit(1));
  const s = await getDocs(q);
  return s.empty ? null : norm(s.docs[0]);
}
