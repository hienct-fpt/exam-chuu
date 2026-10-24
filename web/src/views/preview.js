import { loadExam, examTitle, getAnswerKey, listChildren, listStudentAttempts } from '../api.js';
import { qimg } from '../qimg.js';
import { groupAttempts, duration } from './parent.js';
import { howto } from './result.js';

// 問題の確認 (保護者 only, from 試験一覧): #/preview/{examId} — every question with its answer (answerKeys, readable by the
// admin claim only) and the 解説 crops, plus how the child did on this exam. Read-only: no attempt is created.
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const slotId = (itemId) => itemId.split('#')[1];

/** One answer key as text: parts labelled, 別解 after it, unit at the end; parent-graded items say so. */
export function answerText(key, item = {}) {
  if (!key) return '—';
  const type = key.answer_type || item.answer_type;
  const unit = key.unit && !String(key.unit).includes('・') ? ` ${key.unit}` : '';
  const a = key.answer;
  let main;
  if (Array.isArray(a)) {
    const parts = key.parts || item.parts;
    main = parts?.length ? a.map((v, i) => `${parts[i] ?? ''} ${v}`.trim()).join(' / ') : a.join('・');
  } else main = a == null || a === '' ? '' : String(a);
  if (!main && (type === 'manual' || type === 'essay')) return `保護者が採点${key.note ? `（${key.note}）` : ''}`;
  const variants = (key.variants || []).filter(Boolean);
  return `${main || '—'}${unit}${variants.length ? `（別解 ${variants.join('、')}）` : ''}`;
}

function childSummary(kids, attemptsByKid, examId) {
  if (!kids.length) return '';
  return kids.map((k) => {
    const g = groupAttempts(attemptsByKid[k.uid].filter((a) => a.examId === examId || a.redoOf === examId), () => '')[0];
    if (!g) return `<div><b>${esc(k.name)}</b> <span class="badge">未受験</span></div>`;
    return `<div class="exam-log-line"><b>${esc(k.name)}</b> <span class="muted">${g.list.length}回 · 合計 ${g.totalSec ? `${g.approx ? '約' : ''}${duration(g.totalSec)}` : '—'}</span>
      ${g.graded.map((a) => `<span class="chip ${a.percent < 60 ? 'weak' : ''}">${a.percent}%</span>`).join('<span class="muted">→</span>')}
      <a class="small" href="#/parent/${encodeURIComponent(k.uid)}">記録を見る</a></div>`;
  }).join('');
}

export async function renderPreview({ app }, examId) {
  app.innerHTML = '<div class="card">読み込み中…</div>';
  const [exam, keys, kids] = await Promise.all([loadExam(examId), getAnswerKey(examId).catch(() => ({})), listChildren()]);
  const attemptsByKid = Object.fromEntries(await Promise.all(kids.map(async (k) => [k.uid, await listStudentAttempts(k.uid, 200)])));
  const bigs = exam.bigs.map((b) => {
    const items = exam.items.filter((it) => it.big === b.no);
    const shown = new Set();
    let html = '';
    if (b.stem_image) { html += qimg(b.stem_image); shown.add(b.stem_image); }
    for (const it of items) {
      for (const st of it.stem_images || []) if (!shown.has(st)) { html += qimg(st, 'qimg stem'); shown.add(st); }
      if (!shown.has(it.image)) { html += qimg(it.image); shown.add(it.image); }
      html += `<div class="answer-key"><span class="lbl">${esc(it.label)}</span> <b>${esc(answerText(keys[slotId(it.id)], it))}</b>
        ${it.grade ? `<small class="muted">小${it.grade}</small>` : ''} ${it.topic ? `<small class="muted">${esc(it.topic)}</small>` : ''}
        ${howto(keys[slotId(it.id)] || {})}</div>`;
    }
    const kx = b.explain_image ? `<details class="kaisetsu"><summary>大問${b.no} の解説</summary>${qimg(b.explain_image)}</details>` : '';
    return `<div class="card big" id="big-${b.no}"><div class="big-head"><span class="big-no">${b.no}</span><span class="muted">${items.length} 問</span></div>${html}${kx}</div>`;
  }).join('');
  app.innerHTML = `
    <div class="card"><p><a href="#/">← 試験一覧</a></p>
      <h1>${esc(exam.school_name)} ${esc(examTitle(exam))} ${esc(exam.subject_label)} <span class="badge">問題と答え</span></h1>
      <div class="muted">${exam.item_count} 問 · 制限時間 ${exam.time_limit_min} 分 · 確認用（解答はできません）</div>
      ${childSummary(kids, attemptsByKid, examId)}
    </div>
    ${bigs}`;
}
