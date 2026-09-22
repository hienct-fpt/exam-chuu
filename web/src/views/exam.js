import { loadExam, createAttempt, saveAnswers, submitAttempt, findInProgress } from '../api.js';

const slotId = (itemId) => itemId.split('#')[1];
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function inputFor(item, sid, value) {
  const unit = item.unit ? `<span class="unit">${esc(item.unit)}</span>` : '';
  if (item.parts && item.parts.length) {
    const vals = Array.isArray(value) ? value : [];
    return `<div class="answer-row"><span class="lbl">${esc(item.label)}</span>${item.parts.map((p, i) => `
      <span class="part"><small>${esc(p)}</small><input type="text" data-sid="${sid}" data-part="${i}" value="${esc(vals[i] || '')}" autocomplete="off"></span>`).join('')}${unit}</div>`;
  }
  const hint = { fraction: '分数は 3/4、帯分数は 1 3/4 のように', ratio: '比は 2:3 のように', text: '' }[item.answer_type] || '';
  return `<div class="answer-row"><span class="lbl">${esc(item.label)}</span>
    <input type="text" data-sid="${sid}" class="${item.answer_type === 'fraction' || item.answer_type === 'ratio' ? 'wide' : ''}" value="${esc(value || '')}" autocomplete="off">${unit}</div>
    ${hint ? `<div class="hint">${hint}</div>` : ''}`;
}

export async function renderExam({ app }, examId) {
  const exam = await loadExam(examId);
  let attempt = await findInProgress(examId);
  let attemptId = attempt ? attempt.id : null;
  const answers = attempt ? { ...(attempt.answers || {}) } : {};
  const startedAt = attempt ? new Date(attempt.startedAt) : new Date();

  const byBig = {};
  for (const it of exam.items) (byBig[it.big] ||= []).push(it);

  app.innerHTML = `
    <div class="card">
      <h1>${esc(exam.school_name)} ${exam.year}年度 ${esc(exam.session_label)} ${esc(exam.subject_label)}</h1>
      <div class="muted">${exam.item_count} 問 · 制限時間 ${exam.time_limit_min} 分 · 答えは解答欄に入力（単位は不要）</div>
    </div>
    <form id="sheet" autocomplete="off">
      ${exam.bigs.map((b) => {
        const items = byBig[b.no] || [];
        const shared = items.length && items.every((i) => i.shared_image);
        return `<div class="card big" id="big-${b.no}">
          <div class="big-head"><span class="big-no">${b.no}</span><span class="muted">${items.length} 問</span></div>
          ${b.stem_image && !shared ? `<img class="qimg" src="/${b.stem_image}" loading="lazy">` : ''}
          ${shared ? `<img class="qimg" src="/${b.image}" loading="lazy">
            <div class="item shared"><div>${items.map((it) => inputFor(it, slotId(it.id), answers[slotId(it.id)])).join('')}</div></div>`
            : items.map((it) => `<div class="item">
                <img class="qimg" src="/${it.image}" loading="lazy">
                <div>${inputFor(it, slotId(it.id), answers[slotId(it.id)])}</div></div>`).join('')}
        </div>`;
      }).join('')}
      <div class="card"><div class="sticky-bar">
        <span class="timer" id="timer">--:--</span>
        <span class="muted" id="progress"></span>
        <span class="muted" id="savestate"></span>
        <button type="button" class="primary" id="submit" style="margin-left:auto">提出して採点</button>
      </div></div>
    </form>`;

  const form = app.querySelector('#sheet');
  const total = exam.items.length;
  const progress = app.querySelector('#progress');
  const savestate = app.querySelector('#savestate');

  function collect() {
    for (const inp of form.querySelectorAll('input[data-sid]')) {
      const sid = inp.dataset.sid;
      if (inp.dataset.part !== undefined) {
        const arr = Array.isArray(answers[sid]) ? answers[sid] : [];
        arr[Number(inp.dataset.part)] = inp.value.trim();
        answers[sid] = arr;
      } else answers[sid] = inp.value.trim();
    }
    const done = exam.items.filter((it) => { const v = answers[slotId(it.id)]; return Array.isArray(v) ? v.some(Boolean) : Boolean(v); }).length;
    progress.textContent = `回答 ${done} / ${total}`;
    return done;
  }
  collect();

  let saveTimer = null;
  async function persist() {
    if (!attemptId) attemptId = await createAttempt(examId);
    await saveAnswers(attemptId, answers);
    savestate.textContent = '保存済み';
  }
  form.addEventListener('input', () => {
    collect();
    savestate.textContent = '保存中…';
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => persist().catch((e) => { savestate.textContent = '保存失敗'; console.error(e); }), 800);
  });
  // Enter moves to next input instead of submitting
  form.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
      e.preventDefault();
      const all = [...form.querySelectorAll('input[data-sid]')];
      const i = all.indexOf(e.target);
      if (all[i + 1]) all[i + 1].focus();
    }
  });

  const timerEl = app.querySelector('#timer');
  const limitMs = exam.time_limit_min * 60 * 1000;
  const tick = setInterval(() => {
    const left = Math.max(0, startedAt.getTime() + limitMs - Date.now());
    const m = Math.floor(left / 60000), s = Math.floor((left % 60000) / 1000);
    timerEl.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    timerEl.classList.toggle('low', left < 5 * 60000);
    if (left === 0) { clearInterval(tick); timerEl.textContent = '時間切れ'; }
  }, 500);

  app.querySelector('#submit').onclick = async () => {
    const done = collect();
    const msg = done < total ? `未回答が ${total - done} 問あります。提出しますか？` : '提出して採点しますか？';
    if (!confirm(msg)) return;
    const btn = app.querySelector('#submit');
    btn.disabled = true; btn.textContent = '提出中…';
    try {
      clearTimeout(saveTimer);
      if (!attemptId) attemptId = await createAttempt(examId);
      await submitAttempt(attemptId, answers);
      clearInterval(tick);
      location.hash = `#/result/${attemptId}`;
    } catch (e) {
      alert('提出に失敗しました: ' + e.message);
      btn.disabled = false; btn.textContent = '提出して採点';
    }
  };

  return () => { clearInterval(tick); clearTimeout(saveTimer); };
}
