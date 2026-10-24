// まちがいの原因: the child (or parent) tags each wrong / blank answer on the result page; attempt.mistakes = {sid: cause}.
// The parent's child page counts them per cause and 教科 (from the attempts themselves, no Cloud Function involved).
export const CAUSES = [
  ['careless', 'ケアレスミス', '計算・読みまちがい、書きまちがい'],
  ['knowledge', '知らなかった', 'おぼえていない・習っていない'],
  ['time', '時間切れ', '時間が足りなかった'],
  ['hard', 'むずかしすぎ', 'わかっても解けなかった'],
];
const LABEL = Object.fromEntries(CAUSES.map(([k, l]) => [k, l]));
const SUBJ = { math: '算数', japanese: '国語', science: '理科', social: '社会' };
const ADVICE = {
  careless: 'ケアレスミスが一番多いです。解き終わったら見直す時間を残す、計算は途中式を書く、問題文の「正しくないもの」などに線を引く習慣が効きます。',
  knowledge: '知らなかった問題が一番多いです。やり直し・分野練習と「取るべき問題」で、覚えることを先に固めましょう。',
  time: '時間切れが一番多いです。時間を計って解く練習と、むずかしい問題を後回しにする順番の練習が効きます。',
  hard: 'むずかしすぎた問題が一番多いです。正答率の低い問題は後回しで大丈夫。まず取るべき問題を確実に。',
};
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** The cause picker of one wrong answer on the result page. */
export function mistakePicker(sid, current) {
  return `<select class="mistake" data-mistake="${esc(sid)}" title="まちがいの原因">
    <option value="">原因は？</option>${CAUSES.map(([k, l]) => `<option value="${k}" ${current === k ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
}

/** Counts over graded attempts: {total, tagged, untagged, byCause: {cause: n}, bySubject: {s: {cause: n}}}. */
export function mistakeStats(attempts) {
  const out = { total: 0, tagged: 0, byCause: {}, bySubject: {} };
  for (const a of attempts || []) {
    const per = a?.result?.perItem;
    if (a?.status !== 'graded' || !per) continue;
    for (const [sid, it] of Object.entries(per)) {
      if (it.correct || it.pending) continue;
      out.total += 1;
      const c = a.mistakes?.[sid];
      if (!LABEL[c]) continue;
      out.tagged += 1;
      out.byCause[c] = (out.byCause[c] || 0) + 1;
      const s = it.subject || (it.examId || a.examId || '').split('_').pop();
      ((out.bySubject[s] ||= {})[c] = (out.bySubject[s][c] || 0) + 1);
    }
  }
  out.untagged = out.total - out.tagged;
  return out;
}

/** Parent card: share per cause, per 教科 table, advice for the biggest cause. */
export function mistakeCard(attempts) {
  const st = mistakeStats(attempts);
  if (!st.total) return '';
  if (!st.tagged) {
    return `<div class="card p-card"><h2>まちがいの原因</h2><p class="muted small">結果ページで、まちがえた問題に「原因」（ケアレスミス・知らなかった・時間切れ・むずかしすぎ）を付けると、ここに集計されます。</p></div>`;
  }
  const top = CAUSES.map(([k]) => k).sort((a, b) => (st.byCause[b] || 0) - (st.byCause[a] || 0))[0];
  const pct = (n) => `${Math.round(100 * n / st.tagged)}%`;
  const subs = Object.keys(SUBJ).filter((s) => st.bySubject[s]);
  return `<div class="card p-card mistake-card"><h2>まちがいの原因 <small class="muted">原因つき ${st.tagged} / ${st.total}問</small></h2>
    <div class="mistake-bars">${CAUSES.map(([k, l]) => `<div class="mb-row"><span>${l}</span>
      <span class="mb-bar"><i style="width:${pct(st.byCause[k] || 0)}" class="mb-${k}"></i></span><b>${st.byCause[k] || 0}</b><small class="muted">${pct(st.byCause[k] || 0)}</small></div>`).join('')}</div>
    ${subs.length ? `<table class="small"><tr><th></th>${CAUSES.map(([, l]) => `<th>${l}</th>`).join('')}</tr>
      ${subs.map((s) => `<tr><td>${SUBJ[s]}</td>${CAUSES.map(([k]) => `<td class="num">${st.bySubject[s][k] || ''}</td>`).join('')}</tr>`).join('')}</table>` : ''}
    <p class="hint">💡 ${ADVICE[top]}</p>
    ${st.untagged ? `<p class="muted small">原因が未入力のまちがい: ${st.untagged}問（結果ページで付けられます）</p>` : ''}</div>`;
}
