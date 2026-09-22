import { loadExam, watchAttempt } from '../api.js';

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (v) => (Array.isArray(v) ? v.map((x) => x || '—').join(' / ') : (v === '' || v == null ? '—' : String(v)));
const pct = (c, n) => (n ? Math.round(100 * c / n) : 0);

export async function renderResult({ app }, attemptId) {
  let exam = null;
  const unsub = watchAttempt(attemptId, async (a) => {
    if (!a) { app.innerHTML = '<div class="card">結果が見つかりません。</div>'; return; }
    if (!exam) exam = await loadExam(a.examId);
    const title = `${exam.school_name} ${exam.year}年度 ${exam.session_label} ${exam.subject_label}`;
    const scope = a.gradeFilter ? `<span class="badge">小${a.gradeFilter}までの問題</span>` : '';
    if (a.status !== 'graded') {
      app.innerHTML = `<div class="card"><h1>${esc(title)} ${scope}</h1>
        <p>${a.status === 'error' ? `<span class="ng">採点エラー: ${esc(a.error || '')}</span>` : '採点中… しばらくお待ちください。'}</p>
        <a href="#/">一覧へ</a></div>`;
      return;
    }
    const r = a.result;
    const items = Object.entries(r.perItem).sort(([, x], [, y]) => x.big - y.big || x.sub - y.sub);
    const topics = Object.entries(r.perTopic || {}).sort(([, x], [, y]) => pct(x.correct, x.items) - pct(y.correct, y.items));
    const retry = `#/exam/${a.examId}${a.gradeFilter ? `?g=${a.gradeFilter}` : ''}`;
    app.innerHTML = `
      <div class="card">
        <h1>${esc(title)} ${scope}</h1>
        <div class="score">${r.score} / ${r.max} <span class="muted" style="font-size:18px">(${r.percent}%)</span></div>
        <div class="muted">正解 ${r.correctCount} / ${r.itemCount} 問 · 未回答 ${r.itemCount - r.answeredCount} 問 · 提出 ${a.submittedAt ? new Date(a.submittedAt).toLocaleString('ja-JP') : ''}</div>
        <div class="muted">結果は保護者のメールにも送信されました。</div>
        <p><a href="${retry}">もう一度挑戦</a> · <a href="#/">一覧へ</a>${a.emailHtml ? ' · <a href="#" id="showmail">メールプレビュー (mock)</a>' : ''}</p>
      </div>
      <div class="two-col">
        <div class="card"><h2>大問別</h2><table><tr><th>大問</th><th>正解</th><th>正答率</th></tr>
          ${Object.values(r.perBig).sort((x, y) => x.big - y.big).map((b) => `<tr><td>${b.big}</td><td>${b.correct} / ${b.items}</td><td>${pct(b.correct, b.items)}%</td></tr>`).join('')}
        </table></div>
        <div class="card"><h2>分野別 <small class="muted">(正答率の低い順 = 弱点)</small></h2><table><tr><th>分野</th><th>正解</th><th>正答率</th></tr>
          ${topics.map(([t, v]) => `<tr class="${pct(v.correct, v.items) < 50 ? 'weak' : ''}"><td>${esc(t)}</td><td>${v.correct} / ${v.items}</td><td>${pct(v.correct, v.items)}%</td></tr>`).join('')}
        </table></div>
      </div>
      <div class="card"><h2>全問</h2>
        <label class="muted"><input type="checkbox" id="onlywrong"> 間違いのみ表示</label>
        <table id="items"><tr><th></th><th>問</th><th>分野</th><th>あなたの回答</th><th>正答</th><th>問題</th></tr>
        ${items.map(([sid, it]) => `<tr data-ok="${it.correct}">
          <td class="${it.correct ? 'ok' : (it.answered ? 'ng' : 'muted')}">${it.correct ? '○' : (it.answered ? '×' : '－')}</td>
          <td>大問${it.big} ${esc(it.label)}${it.parts ? ` <small class="muted">[${it.parts.map(esc).join(' / ')}]</small>` : ''}</td>
          <td class="muted">${esc(it.topic || '')}${it.grade ? ` <small>小${it.grade}</small>` : ''}</td>
          <td>${esc(fmt(it.student))} <span class="muted">${esc(it.unit || '')}</span></td>
          <td>${esc(fmt(it.expected))}${it.variants && it.variants.length ? ` <small class="muted">(${it.variants.map(esc).join(', ')})</small>` : ''}</td>
          <td>${it.image ? `<img class="thumb" src="/${it.image}" loading="lazy" onclick="this.classList.toggle('open')">` : ''}</td>
        </tr>`).join('')}</table></div>
      <div class="card" id="mailbox" style="display:none"><h2>メールプレビュー</h2><div id="mailhtml"></div></div>`;
    app.querySelector('#onlywrong').onchange = (e) => {
      for (const tr of app.querySelectorAll('#items tr[data-ok]')) tr.style.display = e.target.checked && tr.dataset.ok === 'true' ? 'none' : '';
    };
    const sm = app.querySelector('#showmail');
    if (sm) sm.onclick = (e) => {
      e.preventDefault();
      const box = app.querySelector('#mailbox'); box.style.display = '';
      const frame = document.createElement('iframe'); frame.style.cssText = 'width:100%;height:900px;border:1px solid #ddd';
      app.querySelector('#mailhtml').replaceChildren(frame);
      frame.srcdoc = a.emailHtml;
      box.querySelector('h2').textContent = `メールプレビュー: ${a.emailSubject || ''}`;
    };
  });
  return unsub;
}
