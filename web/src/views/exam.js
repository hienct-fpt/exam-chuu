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

/** arg = "exam_id" or "exam_id?g=5" */
export function parseExamArg(arg) {
  const [examId, qs] = String(arg || '').split('?');
  const g = new URLSearchParams(qs || '').get('g');
  return { examId, gradeFilter: g && g !== 'all' ? Number(g) : null };
}

export function selectItems(exam, gradeFilter) {
  if (!gradeFilter) return exam.items;
  return exam.items.filter((it) => it.grade != null && it.grade <= gradeFilter);
}

export function scaledTimeLimit(exam, items) {
  if (items.length === exam.items.length) return exam.time_limit_min;
  return Math.max(5, Math.ceil((exam.time_limit_min * items.length / exam.items.length) / 5) * 5);
}

export async function renderExam({ app }, arg) {
  const { examId, gradeFilter } = parseExamArg(arg);
  const exam = await loadExam(examId);
  const items = selectItems(exam, gradeFilter);
  if (!items.length) {
    app.innerHTML = `<div class="card">この試験には該当する問題がありません。<a href="#/">一覧へ</a></div>`;
    return;
  }
  const itemIds = items.map((it) => slotId(it.id));
  const timeLimit = scaledTimeLimit(exam, items);
  let attempt = await findInProgress(examId, gradeFilter);
  let attemptId = attempt ? attempt.id : null;
  const answers = attempt ? { ...(attempt.answers || {}) } : {};
  const startedAt = attempt ? new Date(attempt.startedAt) : new Date();

  const byBig = {};
  for (const it of items) (byBig[it.big] ||= []).push(it);
  const bigs = exam.bigs.filter((b) => byBig[b.no]);

  app.innerHTML = `
    <div class="card">
      <h1>${esc(exam.school_name)} ${exam.year}年度 ${esc(exam.session_label)} ${esc(exam.subject_label)}
        ${gradeFilter ? `<span class="badge">小${gradeFilter}までの問題</span>` : ''}</h1>
      <div class="muted">${items.length} 問${gradeFilter ? ` <small>(全 ${exam.item_count} 問中)</small>` : ''} · 制限時間 ${timeLimit} 分 · 答えは解答欄に入力（単位は不要）</div>
    </div>
    <form id="sheet" autocomplete="off">
      ${bigs.map((b) => {
        const bitems = byBig[b.no];
        const shared = bitems.length && bitems.every((i) => i.shared_image);
        const topic = bitems[0].topic ? `<span class="badge">${esc(bitems[0].topic)}</span>` : '';
        return `<div class="card big" id="big-${b.no}">
          <div class="big-head"><span class="big-no">${b.no}</span><span class="muted">${bitems.length} 問</span>${topic}</div>
          ${b.stem_image && !shared ? `<img class="qimg" src="/${b.stem_image}" loading="lazy">` : ''}
          ${shared ? `<img class="qimg" src="/${b.image}" loading="lazy">
            <div class="item shared"><div>${bitems.map((it) => inputFor(it, slotId(it.id), answers[slotId(it.id)])).join('')}</div></div>`
            : bitems.map((it) => `<div class="item">
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
  const total = items.length;
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
    const done = items.filter((it) => { const v = answers[slotId(it.id)]; return Array.isArray(v) ? v.some(Boolean) : Boolean(v); }).length;
    progress.textContent = `回答 ${done} / ${total}`;
    return done;
  }
  collect();

  const extra = { itemIds, gradeFilter, timeLimitMin: timeLimit };
  let saveTimer = null;
  async function persist() {
    if (!attemptId) attemptId = await createAttempt(examId, gradeFilter ? 'practice' : 'exam', extra);
    await saveAnswers(attemptId, answers);
    savestate.textContent = '保存済み';
  }
  form.addEventListener('input', () => {
    collect();
    savestate.textContent = '保存中…';
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => persist().catch((e) => { savestate.textContent = '保存失敗'; console.error(e); }), 800);
  });
  form.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
      e.preventDefault();
      const all = [...form.querySelectorAll('input[data-sid]')];
      const i = all.indexOf(e.target);
      if (all[i + 1]) all[i + 1].focus();
    }
  });

  const timerEl = app.querySelector('#timer');
  const limitMs = timeLimit * 60 * 1000;
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
      if (!attemptId) attemptId = await createAttempt(examId, gradeFilter ? 'practice' : 'exam', extra);
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
