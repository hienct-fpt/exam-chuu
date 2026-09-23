import { loadExam, loadAllItems, createAttempt, saveAnswers, submitAttempt, findInProgress, getAttempt, examTitle } from '../api.js';

const slotId = (itemId) => itemId.split('#')[1];
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const HINTS = {
  fraction: '分数は 3/4、帯分数は 1 3/4 のように',
  ratio: '比は 2:3 のように',
  set: '順不同。A・D のように「・」で区切る',
  sequence: '順番に A→C→D のように「→」で区切る',
  essay: '文章で答える（保護者が採点します）',
  manual: '作図・グラフの問題。紙にかいてから、答えの説明を書いてください（保護者が採点します）',
};

function inputFor(item, key, value) {
  const unit = item.unit && !item.unit.includes('・') ? `<span class="unit">${esc(item.unit)}</span>` : '';
  const lbl = `<span class="lbl">${esc(item.label)}</span>`;
  if (item.parts && item.parts.length) {
    const vals = Array.isArray(value) ? value : [];
    const pu = item.part_units || [];
    return `<div class="answer-row">${lbl}${item.parts.map((p, i) => `
      <span class="part"><small>${esc(p)}</small><input type="text" data-sid="${key}" data-part="${i}" value="${esc(vals[i] || '')}" autocomplete="off">${pu[i] ? `<small>${esc(pu[i])}</small>` : ''}</span>`).join('')}${unit}</div>`;
  }
  if (item.answer_type === 'choice' && item.options && item.options.length) {
    return `<div class="answer-row">${lbl}${item.options.map((o) => `
      <label class="opt"><input type="radio" name="r-${key}" data-sid="${key}" data-radio="1" value="${esc(o)}" ${value === o ? 'checked' : ''}> ${esc(o)}</label>`).join('')}</div>`;
  }
  if (item.answer_type === 'essay' || item.answer_type === 'manual') {
    const hint = item.source ? '答えを入力してください（保護者が採点します）' : HINTS[item.answer_type];
    return `<div class="answer-row">${lbl}<textarea data-sid="${key}" rows="${item.source ? 1 : 3}" class="essay">${esc(value || '')}</textarea></div>
      <div class="hint">${hint}</div>`;
  }
  const hint = HINTS[item.answer_type] || '';
  const wide = ['fraction', 'ratio', 'set', 'sequence', 'text'].includes(item.answer_type);
  return `<div class="answer-row">${lbl}
    <input type="text" data-sid="${key}" class="${wide ? 'wide' : ''}" value="${esc(value || '')}" autocomplete="off">${unit}</div>
    ${hint ? `<div class="hint">${hint}</div>` : ''}`;
}

/** arg = "exam_id" or "exam_id?g=4|5" (items with grade <= g) */
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

/** Group items into blocks: one block per (exam, 大問). */
function blocks(items, banks) {
  const map = new Map();
  for (const it of items) {
    const k = `${it.exam_id}#${it.big}`;
    if (!map.has(k)) {
      const bank = banks[it.exam_id];
      const big = bank?.bigs.find((b) => b.no === it.big) || {};
      map.set(k, { key: k, examId: it.exam_id, big: it.big, stem_image: big.stem_image, image: big.image,
        examLabel: bank ? `${examTitle(bank)} ${bank.subject_label}` : it.exam_id, items: [] });
    }
    map.get(k).items.push(it);
  }
  return [...map.values()];
}

/** Imported items (min-san): tag badges next to the 問 count, "school year" above the question. No ★ / 解説 link here
 * (the result view carries the link for the parent who grades). */
function sourceHead(items) {
  const srcs = items.map((i) => i.source).filter(Boolean);
  if (!srcs.length) return { tags: '', origin: '' };
  const tags = [...new Set(srcs.flatMap((s) => s.tags || []))].map((t) => `<span class="badge">${esc(t)}</span>`).join('');
  const origin = [...new Set(srcs.map((s) => `${s.school || ''} ${s.year || ''}`.trim()).filter(Boolean))].join(' / ');
  return { tags, origin: origin ? `<span class="muted small origin">${esc(origin)}</span>` : '' };
}

function renderBlock(b, answers, keyOf, showExam) {
  const shown = new Set();
  const topic = b.items[0].topic ? `<span class="badge">${esc(b.items[0].topic)}</span>` : '';
  const { tags, origin } = sourceHead(b.items);
  const allShared = b.items.every((i) => i.shared_image);
  let html = `<div class="card big" id="big-${b.big}" data-block="${esc(b.key)}">
    <div class="big-head"><span class="big-no">${b.big}</span><span class="muted">${b.items.length} 問</span>${topic}${tags}
      ${origin || showExam ? `<span style="margin-left:auto">${origin}${showExam ? ` <span class="muted small">${esc(b.examLabel)}</span>` : ''}</span>` : ''}</div>`;
  if (allShared && b.items.every((i) => i.image === b.items[0].image)) {
    html += `<img class="qimg" src="/${b.items[0].image}" loading="lazy">
      <div class="item shared"><div>${b.items.map((it) => inputFor(it, keyOf(it), answers[keyOf(it)])).join('')}</div></div>`;
    return html + '</div>';
  }
  if (b.stem_image) { html += `<img class="qimg" src="/${b.stem_image}" loading="lazy">`; shown.add(b.stem_image); }
  let lastImage = null;
  for (const it of b.items) {
    for (const st of it.stem_images || []) if (!shown.has(st)) { html += `<img class="qimg stem" src="/${st}" loading="lazy">`; shown.add(st); }
    const k = keyOf(it);
    if (it.shared_image && it.image === lastImage) html += `<div class="item shared"><div>${inputFor(it, k, answers[k])}</div></div>`;
    else if (it.shared_image) html += `<img class="qimg" src="/${it.image}" loading="lazy"><div class="item shared"><div>${inputFor(it, k, answers[k])}</div></div>`;
    else html += `<div class="item"><img class="qimg" src="/${it.image}" loading="lazy"><div>${inputFor(it, k, answers[k])}</div></div>`;
    lastImage = it.image;
  }
  return html + '</div>';
}

/**
 * Shared answer-sheet renderer.
 * sheet = { title, subtitle, items, banks, keyOf(item)->answer key, timeLimit, attemptId|null, answers, startedAt,
 *           createExtra: () => [examId, mode, extra], showExam }
 */
async function renderSheet(app, sheet) {
  const { items, banks, keyOf } = sheet;
  const answers = { ...(sheet.answers || {}) };
  let attemptId = sheet.attemptId;
  const startedAt = sheet.startedAt || new Date();
  app.innerHTML = `
    <div class="card"><h1>${sheet.title}</h1><div class="muted">${sheet.subtitle}</div></div>
    <form id="sheet" autocomplete="off">
      ${blocks(items, banks).map((b) => renderBlock(b, answers, keyOf, sheet.showExam)).join('')}
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
    for (const inp of form.querySelectorAll('input[data-sid], textarea[data-sid]')) {
      const k = inp.dataset.sid;
      if (inp.dataset.radio) { if (inp.checked) answers[k] = inp.value; continue; }
      if (inp.dataset.part !== undefined) {
        const arr = Array.isArray(answers[k]) ? answers[k] : [];
        arr[Number(inp.dataset.part)] = inp.value.trim();
        answers[k] = arr;
      } else answers[k] = inp.value.trim();
    }
    const done = items.filter((it) => { const v = answers[keyOf(it)]; return Array.isArray(v) ? v.some(Boolean) : Boolean(v); }).length;
    progress.textContent = `回答 ${done} / ${total}`;
    return done;
  }
  collect();
  let saveTimer = null;
  async function ensureAttempt() {
    if (!attemptId) attemptId = await createAttempt(...sheet.createExtra());
    return attemptId;
  }
  async function persist() { await saveAnswers(await ensureAttempt(), answers); savestate.textContent = '保存済み'; }
  const onChange = () => {
    collect(); savestate.textContent = '保存中…'; clearTimeout(saveTimer);
    saveTimer = setTimeout(() => persist().catch((e) => { savestate.textContent = '保存失敗'; console.error(e); }), 800);
  };
  form.addEventListener('input', onChange);
  form.addEventListener('change', onChange);
  form.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
      e.preventDefault();
      const all = [...form.querySelectorAll('input[data-sid]:not([data-radio]), textarea[data-sid]')];
      const i = all.indexOf(e.target);
      if (all[i + 1]) all[i + 1].focus();
    }
  });
  const timerEl = app.querySelector('#timer');
  const limitMs = sheet.timeLimit * 60 * 1000;
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
      await submitAttempt(await ensureAttempt(), answers);
      clearInterval(tick);
      location.hash = `#/result/${attemptId}`;
    } catch (e) {
      alert('提出に失敗しました: ' + e.message);
      btn.disabled = false; btn.textContent = '提出して採点';
    }
  };
  return () => { clearInterval(tick); clearTimeout(saveTimer); };
}

/** Full exam (optionally filtered to 小N以下 items): #/exam/{examId}[?g=4|5] */
export async function renderExam({ app }, arg) {
  const { examId, gradeFilter } = parseExamArg(arg);
  const exam = await loadExam(examId);
  const items = selectItems(exam, gradeFilter);
  if (!items.length) { app.innerHTML = `<div class="card">この試験には該当する問題がありません。<a href="#/">一覧へ</a></div>`; return; }
  const itemIds = items.map((it) => slotId(it.id));
  const timeLimit = scaledTimeLimit(exam, items);
  const attempt = await findInProgress(examId, gradeFilter);
  return renderSheet(app, {
    title: `${esc(exam.school_name)} ${esc(examTitle(exam))} ${esc(exam.subject_label)} ${gradeFilter ? `<span class="badge">小${gradeFilter}までの問題</span>` : ''}`,
    subtitle: `${items.length} 問${gradeFilter ? ` <small>(全 ${exam.item_count} 問中)</small>` : ''} · 制限時間 ${timeLimit} 分 · 答えは解答欄に入力（単位は不要）`,
    items, banks: { [examId]: exam }, keyOf: (it) => slotId(it.id), timeLimit, showExam: false,
    attemptId: attempt ? attempt.id : null, answers: attempt?.answers, startedAt: attempt ? new Date(attempt.startedAt) : null,
    createExtra: () => [examId, gradeFilter ? 'practice' : 'exam', { itemIds, gradeFilter, timeLimitMin: timeLimit }],
  });
}

/** Cross-exam practice attempt created by the practice view: #/attempt/{attemptId} */
export async function renderAttempt({ app }, attemptId) {
  const a = await getAttempt(attemptId);
  if (!a) { app.innerHTML = '<div class="card">見つかりません。<a href="#/">一覧へ</a></div>'; return; }
  if (a.status !== 'in_progress') { location.hash = `#/result/${attemptId}`; return; }
  if (a.mode !== 'practice' || !a.items) { location.hash = `#/exam/${a.examId}${a.gradeFilter ? `?g=${a.gradeFilter}` : ''}`; return; }
  const all = await loadAllItems(a.subject || null);
  const byId = Object.fromEntries(all.items.map((it) => [it.id, it]));
  const items = a.items.map((id) => byId[id]).filter(Boolean);
  const timeLimit = a.timeLimitMin || Math.max(5, Math.ceil(items.length * 2 / 5) * 5);
  return renderSheet(app, {
    title: `${esc(a.title || '練習')} ${a.gradeFilter ? `<span class="badge">小${a.gradeFilter}まで</span>` : ''}`,
    subtitle: `${items.length} 問 · ${[...new Set(items.map((i) => i.examLabel))].length} 回分の過去問から · 目安 ${timeLimit} 分`,
    items, banks: all.banks, keyOf: (it) => it.id, timeLimit, showExam: true,
    attemptId, answers: a.answers, startedAt: new Date(a.startedAt),
    createExtra: () => [null, 'practice', {}],
  });
}
