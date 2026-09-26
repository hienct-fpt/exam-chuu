import { loadExam, loadIndex, watchAttempt, currentUser, setManualGrade } from '../api.js';

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (v) => (Array.isArray(v) ? v.map((x) => x || '—').join(' / ') : (v === '' || v == null ? '—' : String(v)));
const pct = (c, n) => (n ? Math.round(100 * c / n) : 0);
const TYPE_LABEL = { set: '順不同', sequence: '並べかえ', essay: '記述', manual: '作図' };

export async function renderResult({ app }, attemptId) {
  let title = null;
  let examLabel = () => '';
  const isAdmin = Boolean(currentUser()?.admin);
  const unsub = watchAttempt(attemptId, async (a) => {
    if (!a) { app.innerHTML = '<div class="card">結果が見つかりません。</div>'; return; }
    if (title === null) {
      if (a.mode === 'practice' && a.items) {
        const index = await loadIndex();
        const meta = Object.fromEntries(index.map((e) => [e.id, e]));
        examLabel = (eid) => (meta[eid] ? `${meta[eid].year}年度 ${meta[eid].session_label}` : eid);
        title = a.title || '練習';
      } else {
        const exam = await loadExam(a.examId);
        title = `${exam.school_name} ${exam.year}年度 ${exam.session_label} ${exam.subject_label}`;
      }
    }
    const isPractice = a.mode === 'practice' && a.items;
    const scope = a.gradeFilter ? `<span class="badge">小${a.gradeFilter}までの問題</span>` : '';
    if (a.status !== 'graded') {
      app.innerHTML = `<div class="card"><h1>${esc(title)} ${scope}</h1>
        <p>${a.status === 'error' ? `<span class="ng">採点エラー: ${esc(a.error || '')}</span>` : '採点中… しばらくお待ちください。'}</p>
        <a href="#/">一覧へ</a></div>`;
      return;
    }
    const r = a.result;
    const items = Object.entries(r.perItem).sort(([, x], [, y]) => String(x.examId).localeCompare(String(y.examId)) || x.big - y.big
      || String(x.path || x.sub).localeCompare(String(y.path || y.sub), 'ja', { numeric: true }));
    const topics = Object.entries(r.perTopic || {}).sort(([, x], [, y]) => pct(x.correct, x.items) - pct(y.correct, y.items));
    const retry = isPractice ? `#/practice/${a.subject || 'math'}?${a.topics?.length ? `topic=${encodeURIComponent(a.topics[0])}` : 'weak=1'}${a.gradeFilter ? '&g=' + a.gradeFilter : ''}`
      : `#/exam/${a.examId}${a.gradeFilter ? `?g=${a.gradeFilter}` : ''}`;
    const pending = r.pendingCount || 0;
    const mark = (it) => (it.correct ? '○' : it.pending ? '？' : it.answered ? '×' : '－');
    const cls = (it) => (it.correct ? 'ok' : it.pending ? 'warn' : it.answered ? 'ng' : 'muted');
    app.innerHTML = `
      <div class="card">
        <h1>${esc(title)} ${scope}</h1>
        <div class="score">${r.score} / ${r.max} <span class="muted" style="font-size:18px">(${r.percent}%)</span></div>
        <div class="muted">正解 ${r.correctCount} / ${r.itemCount} 問 · 未回答 ${r.itemCount - r.answeredCount} 問
          ${pending ? ` · <span class="warn">採点待ち ${pending} 問（記述・作図は保護者が採点）</span>` : ''}
          · 提出 ${a.submittedAt ? new Date(a.submittedAt).toLocaleString('ja-JP') : ''}</div>
        <p><a href="${retry}">${isPractice ? '同じ分野でもう一度' : 'もう一度挑戦'}</a> · <a href="#/dashboard">ダッシュボード</a> · <a href="#/">一覧へ</a></p>
      </div>
      <div class="two-col">
        <div class="card"><h2>${isPractice ? '過去問別' : '大問別'}</h2><table><tr><th>${isPractice ? '出典' : '大問'}</th><th>正解</th><th>正答率</th></tr>
          ${Object.values(r.perBig).sort((x, y) => String(x.examId).localeCompare(String(y.examId)) || x.big - y.big).map((b) => `<tr><td>${isPractice ? `${esc(examLabel(b.examId))} 大問${b.big}` : b.big}</td><td>${b.correct} / ${b.items}${b.pending ? ` <small class="warn">(?${b.pending})</small>` : ''}</td><td>${pct(b.correct, b.items)}%</td></tr>`).join('')}
        </table></div>
        <div class="card"><h2>分野別 <small class="muted">(正答率の低い順 = 弱点)</small></h2><table><tr><th>分野</th><th>正解</th><th>正答率</th></tr>
          ${topics.map(([t, v]) => `<tr class="${pct(v.correct, v.items) < 50 ? 'weak' : ''}"><td>${esc(t)}</td><td>${v.correct} / ${v.items}</td><td>${pct(v.correct, v.items)}%</td></tr>`).join('')}
        </table></div>
      </div>
      <div class="card"><h2>全問 ${isAdmin ? '<small class="badge">保護者モード: 記述の○×を付けられます</small>' : ''}</h2>
        <label class="muted"><input type="checkbox" id="onlywrong"> 間違い・採点待ちのみ表示</label>
        <table id="items"><tr><th></th><th>問</th><th>分野</th><th>あなたの回答</th><th>正答</th><th>問題</th></tr>
        ${items.map(([sid, it]) => `<tr data-ok="${it.correct}" data-sid="${sid}">
          <td class="${cls(it)}">${mark(it)}</td>
          <td>${isPractice ? `<small class="muted">${esc(examLabel(it.examId))}</small><br>` : ''}大問${it.big} ${esc(it.label)}${it.parts ? ` <small class="muted">[${it.parts.map(esc).join(' / ')}]</small>` : ''}${TYPE_LABEL[it.answerType] ? ` <small class="badge">${TYPE_LABEL[it.answerType]}</small>` : ''}</td>
          <td class="muted">${esc(it.topic || '')}${it.grade ? ` <small>小${it.grade}</small>` : ''}</td>
          <td>${esc(fmt(it.student))} <span class="muted">${esc(it.unit && !it.unit.includes('・') ? it.unit : '')}</span>
            ${(it.pending || it.manual) && isAdmin ? `<div class="grade-btns"><button data-mg="1" data-sid="${sid}" class="${it.manual && it.correct ? 'primary' : ''}">○ 正解</button><button data-mg="0" data-sid="${sid}" class="${it.manual && !it.correct ? 'danger' : ''}">× 不正解</button></div>` : ''}
            ${it.pending && !isAdmin ? '<div class="hint warn">採点待ち</div>' : ''}</td>
          <td>${esc(fmt(it.expected))}${it.variants && it.variants.length ? ` <small class="muted">(${it.variants.map(esc).join(', ')})</small>` : ''}${it.note ? `<div class="hint">${esc(it.note)}</div>` : ''}${it.source?.url ? `<div class="hint"><a href="${esc(it.source.url)}" target="_blank" rel="noopener">解説 (${esc(it.source.site || 'source')})</a> <small class="muted">${esc(it.source.school || '')} ${it.source.year || ''}</small></div>` : ''}</td>
          <td>${it.image ? `<img class="thumb" src="/${it.image}" loading="lazy" onclick="this.classList.toggle('open')">` : ''}</td>
        </tr>`).join('')}</table></div>`;
    app.querySelector('#onlywrong').onchange = (e) => {
      for (const tr of app.querySelectorAll('#items tr[data-ok]')) tr.style.display = e.target.checked && tr.dataset.ok === 'true' ? 'none' : '';
    };
    for (const btn of app.querySelectorAll('button[data-mg]')) {
      btn.onclick = async () => {
        btn.disabled = true;
        try { await setManualGrade(attemptId, btn.dataset.sid, btn.dataset.mg === '1'); }
        catch (e) { alert('採点の保存に失敗: ' + e.message); btn.disabled = false; }
      };
    }
  });
  return unsub;
}
