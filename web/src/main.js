import { onAuth, signIn, signOut, isMock } from './api.js';
import { renderHome } from './views/home.js';
import { renderExam, renderAttempt } from './views/exam.js';
import { renderResult } from './views/result.js';
import { renderHistory } from './views/history.js';
import { renderDashboard } from './views/dashboard.js';
import { renderPractice } from './views/practice.js';

const app = document.getElementById('app');
const userBox = document.getElementById('user');
let user = null;
let cleanup = null;

const ROUTES = { '': renderHome, exam: renderExam, attempt: renderAttempt, result: renderResult, history: renderHistory,
  dashboard: renderDashboard, practice: renderPractice };

function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  const hash = location.hash.replace(/^#/, '') || '/';
  const [, page, arg] = hash.match(/^\/([^/]*)\/?(.*)$/) || [];
  if (!user) {
    app.innerHTML = `<div class="card"><h1>過去問練習</h1><p>Google アカウントでログインしてください。</p>
      <button class="primary" id="login">ログイン</button></div>`;
    document.getElementById('login').onclick = () => signIn().catch((e) => alert(e.message));
    return;
  }
  document.querySelectorAll('#topbar nav a').forEach((a) => a.classList.toggle('on', a.getAttribute('href') === `#/${page || ''}`));
  const run = ROUTES[page || ''];
  if (!run) { app.innerHTML = '<div class="card">ページが見つかりません。<a href="#/">一覧へ</a></div>'; return; }
  Promise.resolve(run({ app, user }, arg)).then((c) => { cleanup = typeof c === 'function' ? c : null; })
    .catch((e) => { console.error(e); app.innerHTML = `<div class="card ng">エラー: ${e.message}</div>`; });
}

onAuth((u) => {
  user = u;
  userBox.innerHTML = u ? `<span>${u.name}${u.admin ? ' <span class="badge">保護者</span>' : ''}${isMock ? ' (mock)' : ''}</span><button id="logout">ログアウト</button>` : '';
  const lo = document.getElementById('logout');
  if (lo) lo.onclick = () => signOut();
  route();
});
window.addEventListener('hashchange', route);
