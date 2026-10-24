// 偏差値シミュレーター: "if the child gets N more points in this 教科" -> 推定偏差値 / 合格可能性.
// Mirrors functions/hensachi.py (estimate() and kumiwake_report()) on the numbers the report exports:
//   school session x: {y80, y50, model: {max: {s: max}, line, sigmaC}, levels: {s: 0..1}}
//   組分け round r:   {subjects: {s: {y, pct, max, sd, examId}}, total, sdTotal}
const SUBJ = { math: '算数', japanese: '国語', science: '理科', social: '社会' };
export const Z80 = 0.8416212335729143;
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** Standard normal CDF (Abramowitz–Stegun 7.1.26 erf, |error| < 1.5e-7). */
export function normCdf(z) {
  const x = Math.abs(z) / Math.SQRT2, t = 1 / (1 + 0.3275911 * x);
  const erf = 1 - t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429)))) * Math.exp(-x * x);
  return z >= 0 ? (1 + erf) / 2 : (1 - erf) / 2;
}

/** Expected score per 教科 now (level × max), capped added points -> {score, y, prob}; null without model / levels. */
export function schoolSim(x, add = {}) {
  const m = x?.model, lv = x?.levels;
  if (!m || !lv || Object.keys(m.max).some((s) => lv[s] == null)) return null;
  let score = 0;
  for (const [s, mx] of Object.entries(m.max)) score += Math.min(mx, lv[s] * mx + (Number(add[s]) || 0));
  const z = (score - m.line) / m.sigmaC;
  return { score, y: x.y50 + (x.y80 - x.y50) / Z80 * z, prob: normCdf(z) };
}

/** 偏差値 per extra point (any 教科) and points still needed for the 80% line. */
export function schoolNeeds(x) {
  const now = schoolSim(x);
  if (!now) return null;
  const perPoint = (x.y80 - x.y50) / Z80 / x.model.sigmaC;
  return { perPoint, to80: Math.max(0, x.model.line + Z80 * x.model.sigmaC - now.score) };
}

/** 組分け round with added points per 教科 -> {subjects: {s: y}, total}. */
export function kumiwakeSim(r, add = {}) {
  const subjects = {};
  let dTotal = 0;
  for (const [s, v] of Object.entries(r?.subjects || {})) {
    if (v.sd == null) return null;
    const pts = Math.min(Number(add[s]) || 0, v.max * (1 - v.pct / 100));
    subjects[s] = v.y + 10 * pts / v.sd;
    dTotal += pts;
  }
  return { subjects, total: r.total == null || r.sdTotal == null ? null : r.total + 10 * dTotal / r.sdTotal };
}

/** Points per 教科 of a round that the 取るべき問題 list holds (items carry `points` and `examId`). */
export function toruPoints(r, toruBySubject) {
  const out = {};
  for (const [s, v] of Object.entries(r?.subjects || {})) {
    out[s] = (toruBySubject?.[s] || []).filter(({ item }) => item.exam_id === v.examId).reduce((n, { item }) => n + (item.points || 1), 0);
  }
  return out;
}

const f1 = (v) => (v == null ? '—' : v.toFixed(1));
const pctTxt = (p) => `${Math.round(p * 100)}%`;
const delta = (a, b) => { const d = b - a; return `<span class="${d > 0.05 ? 'up' : ''}">${d > 0.05 ? '+' : ''}${d.toFixed(1)}</span>`; };

/** Parent card: school sessions (+N点 per 教科 inputs) and the latest 組分け round (per-point effect per 教科). */
export function simulatorCard(h) {
  const sessions = (h?.sessions || []).filter((x) => schoolSim(x));
  const rounds = (h?.kumiwake?.rounds || []).filter((r) => kumiwakeSim(r));
  if (!sessions.length && !rounds.length) return '';
  const last = rounds[rounds.length - 1];
  const kumi = last ? `<h3>組分けテスト 第${last.round}回 <small class="muted">1点ふやすと</small></h3>
    <table><tr><th>教科</th><th>今の偏差値</th><th>+1点で</th><th>+10点で</th></tr>
      ${Object.entries(last.subjects).map(([s, v]) => `<tr><td>${SUBJ[s] || s}</td><td class="num">${f1(v.y)}</td>
        <td class="num">+${(10 / v.sd).toFixed(2)}</td><td class="num">+${(100 / v.sd).toFixed(1)}</td></tr>`).join('')}
      ${last.sdTotal ? `<tr><td>4科</td><td class="num">${f1(last.total)}</td><td class="num">+${(10 / last.sdTotal).toFixed(2)}</td><td class="num">+${(100 / last.sdTotal).toFixed(1)}</td></tr>` : ''}
    </table><p class="small muted">4科の偏差値は、どの教科で取った1点でも同じだけ上がります。取りやすい点（<a href="#/toru">取るべき問題</a>）から取るのが近道です。</p>` : '';
  const opts = sessions.map((x, i) => `<option value="${i}">${esc(x.schoolName)} ${esc(x.label)}</option>`).join('');
  return `<div class="card p-card sim-card"><h2>偏差値シミュレーター <small class="muted">あと何点で、どれだけ上がる？</small></h2>
    ${sessions.length ? `<p><select id="sim-session">${opts}</select></p><div id="sim-school"></div>` : ''}
    ${kumi}
    <p class="small muted">推定偏差値と同じ仮定（点数の散らばり・当日のぶれ）にもとづく参考値です。</p></div>`;
}

/** Fill / refresh the school part of simulatorCard (inputs per 教科, live). */
export function bindSimulator(root, h) {
  const sel = root.querySelector('#sim-session'), box = root.querySelector('#sim-school');
  if (!sel || !box) return;
  const sessions = (h?.sessions || []).filter((x) => schoolSim(x));
  const draw = () => {
    const x = sessions[Number(sel.value) || 0];
    const now = schoolSim(x), need = schoolNeeds(x);
    box.innerHTML = `<table><tr><th>教科</th><th>今の見込み</th><th>ふやす点</th></tr>
      ${Object.entries(x.model.max).map(([s, mx]) => `<tr><td>${SUBJ[s] || s}</td><td class="num">${Math.round(x.levels[s] * mx)} / ${mx}点</td>
        <td><input type="number" class="sim-add" data-s="${s}" min="0" max="${Math.round(mx * (1 - x.levels[s]))}" step="5" value="0" style="width:5em"> 点</td></tr>`).join('')}</table>
      <p id="sim-out"></p>
      <p class="small muted">1点で 偏差値 +${need.perPoint.toFixed(2)} · 80%ラインまで あと <b>${Math.ceil(need.to80)}点</b>${need.to80 === 0 ? '（到達）' : ''}</p>`;
    const out = box.querySelector('#sim-out');
    const update = () => {
      const add = Object.fromEntries([...box.querySelectorAll('.sim-add')].map((i) => [i.dataset.s, Number(i.value) || 0]));
      const r = schoolSim(x, add);
      out.innerHTML = `推定偏差値 <b>${f1(now.y)}</b> → <b>${f1(r.y)}</b> (${delta(now.y, r.y)}) · 合格可能性 ${pctTxt(now.prob)} → <b>${pctTxt(r.prob)}</b>
        <small class="muted">（80%ライン ${x.y80} / 50%ライン ${x.y50}）</small>`;
    };
    for (const i of box.querySelectorAll('.sim-add')) i.oninput = update;
    update();
  };
  sel.onchange = draw;
  draw();
}
