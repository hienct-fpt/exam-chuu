import { listMyParents, redeemInvite } from '../api.js';

// 保護者と連携 (#/join, #/join/<code> from the parent's copied link): the child enters the parent's invite code.
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export async function renderJoin({ app }, arg) {
  const parents = await listMyParents();
  if (parents.length) { // already linked: no second code
    app.innerHTML = `<div class="card"><h1>保護者と連携</h1>
      <p>連携中: ${parents.map((p) => `<span class="chip">${esc(p.name)}</span>`).join(' ')}</p>
      <p><a href="#/">試験一覧へ</a></p></div>`;
    return;
  }
  app.innerHTML = `<div class="card"><h1>保護者と連携</h1>
    <p class="muted">保護者から受け取った招待コードを入力してください。連携すると保護者があなたの結果を見て、記述・作図の採点ができます。</p>
    <form id="join-form">
      <input id="join-code" class="invite-code" maxlength="8" autocomplete="off" placeholder="例: K7Q2MX" value="${esc(decodeURIComponent(arg || '').toUpperCase())}">
      <button class="primary" type="submit">登録</button>
    </form>
    <p id="join-msg"></p></div>`;
  const msg = app.querySelector('#join-msg');
  app.querySelector('#join-form').onsubmit = async (e) => {
    e.preventDefault();
    const code = app.querySelector('#join-code').value.trim().toUpperCase();
    if (!code) return;
    const btn = e.target.querySelector('button');
    btn.disabled = true;
    msg.className = 'muted'; msg.textContent = '登録中…';
    try {
      const { parentName } = await redeemInvite(code);
      e.target.remove();
      msg.className = 'ok';
      msg.innerHTML = `${esc(parentName)} と連携しました。<a href="#/">試験一覧へ</a>`;
    } catch (err) {
      msg.className = 'ng'; msg.textContent = err.message;
      btn.disabled = false;
    }
  };
}
