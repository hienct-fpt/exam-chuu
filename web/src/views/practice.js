import { getTopicStats, loadAllItems, createAttempt } from '../api.js';
import { gradeFilterFromPref } from './home.js';

const SUBJ = { math: '算数', science: '理科', social: '社会', japanese: '国語' };
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const DECAY = 0.85;

/** JS mirror of analytics.practice_set: wrong before > never seen > correct long ago; shared-image siblings pulled in. */
export function pickPractice(items, topics, hist, { n = 10, gradeFilter = null, includePending = false } = {}) {
  const now = Date.now();
  const cands = [];
  for (const it of items) {
    if (topics && !topics.has(it.topic || '未分類')) continue;
    if (gradeFilter && !(it.grade && it.grade <= gradeFilter)) continue;
    if (!includePending && (it.answer_type === 'essay' || it.answer_type === 'manual')) continue;
    const h = hist[it.id];
    let prio = 1, age = 0;
    if (h) { prio = h.correct ? 2 : 0; age = now - new Date(h.t).getTime(); }
    cands.push({ prio, age: -age, it });
  }
  cands.sort((a, b) => a.prio - b.prio || a.age - b.age || a.it.id.localeCompare(b.it.id));
  const picked = [], ids = new Set();
  const groups = {};
  for (const it of items) if (it.shared_image) (groups[`${it.exam_id}|${it.image}`] ||= []).push(it);
  for (const { it } of cands) {
    if (ids.has(it.id)) continue;
    const g = it.shared_image ? groups[`${it.exam_id}|${it.image}`] : [it];
    for (const x of g) if (!ids.has(x.id) && (!topics || topics.has(x.topic || '未分類'))) { picked.push(x); ids.add(x.id); }
    if (picked.length >= n) break;
  }
  return picked;
}

export async function renderPractice({ app }, arg) {
  const [subject, qs] = String(arg || 'math').split('?');
  const params = new URLSearchParams(qs || '');
  const gradeFilter = params.get('g') ? (params.get('g') === 'all' ? null : Number(params.get('g'))) : gradeFilterFromPref();
  const wantWeak = params.get('weak') === '1';
  const topicParam = params.get('topic');
  app.innerHTML = '<div class="card">読み込み中…</div>';
  const [stats, all] = await Promise.all([getTopicStats(), loadAllItems(subject)]);
  const topics = Object.entries(stats.topics || {}).filter(([, t]) => t.subject === subject);
  const weak = topics.filter(([, t]) => t.weak).map(([t]) => t);
  const allTopics = [...new Set(all.items.map((it) => it.topic || '未分類'))].sort();
  const selected = new Set(topicParam ? [topicParam] : (wantWeak && weak.length ? weak : []));
  let n = 10;
  let includePending = false; // manual/essay items (e.g. min-san imports) need a parent to grade them

  function preview() {
    const picked = pickPractice(all.items, selected.size ? selected : null, stats.itemHistory || {}, { n, gradeFilter, includePending });
    const el = app.querySelector('#preview');
    el.innerHTML = picked.length
      ? `<div class="muted">${picked.length} 問 · ${[...new Set(picked.map((p) => p.examLabel))].join(' / ')}</div>
         <ul class="muted small">${picked.slice(0, 12).map((p) => `<li>${esc(p.examLabel)} 大問${p.big} ${esc(p.label)} <small>${esc(p.topic || '')}</small>${stats.itemHistory?.[p.id] ? (stats.itemHistory[p.id].correct ? ' ○' : ' <span class="ng">×前回不正解</span>') : ' <span class="badge">未</span>'}</li>`).join('')}${picked.length > 12 ? '<li>…</li>' : ''}</ul>`
      : '<div class="muted">該当する問題がありません（分野または学年フィルタを変えてください）</div>';
    app.querySelector('#start').disabled = !picked.length;
    return picked;
  }

  app.innerHTML = `
    <div class="card">
      <h1>練習セット · ${SUBJ[subject] || subject}</h1>
      <div class="muted">分野を選ぶと、その分野の問題から「前回まちがえた → まだ解いていない → 前に正解した」の順に出題します。
        ${gradeFilter ? `<span class="badge">小${gradeFilter}までの問題</span>` : '<span class="badge">全学年</span>'}
        <label><input type="checkbox" id="pending"> 手採点の問題も含む（記述・作図・みんなの算数の問題）</label></div>
      <h3>分野</h3>
      <div class="chips" id="topics">${allTopics.map((t) => {
        const st = stats.topics?.[t];
        return `<button class="chip ${selected.has(t) ? 'on' : ''} ${st?.weak ? 'weak' : ''}" data-t="${esc(t)}">${esc(t)}${st ? ` <small>${Math.round((st.mastery ?? 0) * 100)}%</small>` : ''}</button>`;
      }).join('')}</div>
      <div class="muted small">${weak.length ? `弱点: ${weak.map(esc).join('、')}` : '弱点分野はまだ判定されていません（3問以上解くと表示）'}
        ${weak.length ? ` · <a href="#" id="pickweak">弱点だけ選ぶ</a>` : ''} · <a href="#" id="pickall">全部</a> · <a href="#" id="picknone">解除</a></div>
      <h3>問題数</h3>
      <div class="seg" id="count">${[5, 10, 15, 20].map((k) => `<button data-n="${k}" class="${k === n ? 'on' : ''}">${k}</button>`).join('')}</div>
      <h3>出題予定</h3><div id="preview"></div>
      <p><button class="primary" id="start">練習を始める</button> <a href="#/dashboard" style="margin-left:12px">ダッシュボードへ</a></p>
    </div>`;
  app.querySelector('#topics').onclick = (e) => {
    const t = e.target.closest('[data-t]')?.dataset.t; if (!t) return;
    if (selected.has(t)) selected.delete(t); else selected.add(t);
    e.target.closest('[data-t]').classList.toggle('on');
    preview();
  };
  app.querySelector('#pending').onchange = (e) => { includePending = e.target.checked; preview(); };
  app.querySelector('#count').onclick = (e) => {
    const k = e.target.dataset.n; if (!k) return;
    n = Number(k);
    app.querySelectorAll('#count button').forEach((b) => b.classList.toggle('on', b.dataset.n === k));
    preview();
  };
  const setSel = (set) => { selected.clear(); for (const t of set) selected.add(t); app.querySelectorAll('#topics .chip').forEach((b) => b.classList.toggle('on', selected.has(b.dataset.t))); preview(); };
  app.querySelector('#pickweak')?.addEventListener('click', (e) => { e.preventDefault(); setSel(weak); });
  app.querySelector('#pickall').onclick = (e) => { e.preventDefault(); setSel([]); };
  app.querySelector('#picknone').onclick = (e) => { e.preventDefault(); setSel([]); };
  let picked = preview();
  app.querySelector('#start').onclick = async () => {
    picked = preview();
    if (!picked.length) return;
    const title = `${SUBJ[subject]} 練習: ${selected.size ? [...selected].join('・') : '全分野'}`;
    const id = await createAttempt(null, 'practice', {
      items: picked.map((p) => p.id), topics: [...selected], subject, gradeFilter,
      timeLimitMin: Math.max(5, Math.ceil(picked.length * 2 / 5) * 5), title,
    });
    location.hash = `#/attempt/${id}`;
  };
}
