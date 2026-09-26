import { signIn, signInWithLoginId, createChildAccount } from '../api.js';

// Signed-out screens. #/join/<code> (the parent's invite link) = create a login-ID account; anything else = log in.
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const loginIdForm = `<form id="id-login" class="stack">
    <label>ログインID <input name="loginId" autocomplete="username" autocapitalize="none" required></label>
    <label>パスワード <input name="password" type="password" autocomplete="current-password" required></label>
    <button class="primary" type="submit">ログイン</button>
  </form>`;

function bind(app, form, fn) {
  const msg = app.querySelector('#auth-msg');
  form.onsubmit = async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    btn.disabled = true; msg.className = 'muted'; msg.textContent = '処理中…';
    try { await fn(Object.fromEntries(new FormData(form))); } // success -> onAuth re-routes
    catch (err) { msg.className = 'ng'; msg.textContent = err.message; btn.disabled = false; }
  };
}

export function renderLogin(app, page, arg) {
  const code = page === 'join' ? decodeURIComponent(arg || '').trim().toUpperCase() : '';
  if (code) return renderSignup(app, code);
  app.innerHTML = `<div class="card"><h1>過去問練習</h1>
    <h3>保護者・Google アカウント</h3><button class="primary" id="login">Google でログイン</button>
    <h3>ログインID</h3>${loginIdForm}
    <p id="auth-msg"></p>
    <p class="muted">アカウントがない場合は、保護者から招待リンクをもらってください。</p></div>`;
  app.querySelector('#login').onclick = () => signIn().catch((e) => alert(e.message));
  bind(app, app.querySelector('#id-login'), (f) => signInWithLoginId(f.loginId, f.password));
}

function renderSignup(app, code) {
  app.innerHTML = `<div class="card"><h1>アカウントを作る</h1>
    <p class="muted">保護者からの招待コード <b class="invite-code">${esc(code)}</b> でアカウントを作り、保護者と連携します。</p>
    <form id="signup" class="stack">
      <label>名前 <input name="name" maxlength="20" required placeholder="例: たろう"></label>
      <label>ログインID <input name="loginId" autocomplete="username" autocapitalize="none" pattern="[a-z0-9_]{3,20}" required
        placeholder="半角英小文字・数字・_ で3〜20文字"></label>
      <label>パスワード <input name="password" type="password" autocomplete="new-password" minlength="6" required placeholder="6文字以上"></label>
      <label>パスワード (確認) <input name="password2" type="password" autocomplete="new-password" minlength="6" required></label>
      <button class="primary" type="submit">アカウントを作る</button>
    </form>
    <p id="auth-msg"></p>
    <p class="muted">ログインIDとパスワードは忘れないようにメモしておきましょう。忘れたら保護者がパスワードを変更できます。</p>
    <details><summary>すでにアカウントがある</summary>
      <p class="muted">ログインすると、このコードで保護者と連携できます。</p>
      <button id="login">Google でログイン</button>${loginIdForm}</details></div>`;
  // Existing account: after sign-in the router lands on #/join/<code> (signed in), where the code is prefilled.
  app.querySelector('#login').onclick = () => signIn().catch((e) => alert(e.message));
  bind(app, app.querySelector('#id-login'), (f) => signInWithLoginId(f.loginId, f.password));
  bind(app, app.querySelector('#signup'), async (f) => {
    if (f.password !== f.password2) throw new Error('パスワードが一致しません');
    // replaceState fires no hashchange: after the automatic sign-in the router shows #/join (linked parent), not the used-up code
    history.replaceState(null, '', '#/join');
    try { await createChildAccount({ code, loginId: f.loginId.trim().toLowerCase(), password: f.password, name: f.name.trim() }); }
    catch (e) { history.replaceState(null, '', `#/join/${code}`); throw e; }
  });
}
