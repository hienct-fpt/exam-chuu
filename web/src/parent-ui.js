// 保護者 dashboard pieces: KPI cards, 弱点分析, 今週の課題 timeline. Real data only (goals / attempts / topic stats).
import { weekSeconds } from './kid.js';
import { kindOf, practiceImprovement } from './activity.js';
import { duration } from './views/parent.js';

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const SUBJ = { math: '算数', japanese: '国語', science: '理科', social: '社会' };

/** Average % of the last `n` graded 本番 / 範囲指定, and of the `n` before (for the trend). */
export function examAverage(attempts, n = 5) {
  const ex = attempts.filter((a) => a.status === 'graded' && ['exam', 'range'].includes(kindOf(a)))
    .sort((x, y) => String(y.submittedAt || y.startedAt || '').localeCompare(String(x.submittedAt || x.startedAt || '')));
  const avg = (l) => (l.length ? l.reduce((s, a) => s + (a.percent || 0), 0) / l.length : null);
  return { now: avg(ex.slice(0, n)), before: avg(ex.slice(n, 2 * n)), count: Math.min(n, ex.length) };
}

/** 実力 vs 最終目標 over the subjects that have a level (goals.subjects). */
export function targetGap(goals) {
  const rows = Object.entries(goals?.subjects || {}).filter(([, g]) => g.level != null && g.target != null);
  if (!rows.length) return null;
  const level = rows.reduce((s, [, g]) => s + g.level, 0) / rows.length;
  const target = rows.reduce((s, [, g]) => s + g.target, 0) / rows.length;
  const risk = rows.filter(([, g]) => g.atRisk).map(([k]) => SUBJ[k] || k);
  return { level, target, risk };
}

const trend = (now, before) => {
  if (now == null || before == null) return '';
  const d = Math.round(now - before);
  return d === 0 ? '<span class="kpi-trend">→ 前の5回と同じ</span>'
    : `<span class="kpi-trend ${d > 0 ? 'up' : 'down'}">${d > 0 ? '▲' : '▼'} ${Math.abs(d)}pt 前の5回より</span>`;
};
const bar = (v) => `<div class="kpi-bar"><div style="width:${Math.max(0, Math.min(100, Math.round(v * 100)))}%"></div></div>`;

/** Four KPI cards: this week's time, 課題 done, recent 本番 average, gap to the final target. */
export function kpiCards(stats, attempts, { compact = false } = {}) {
  const g = stats?.goals;
  const items = g?.assignments?.items || [];
  const doneN = (g?.assignmentsDone || []).filter(Boolean).length;
  const budget = g?.assignments?.budget || items.reduce((n, it) => n + it.minutes, 0);
  const sec = g?.weekStart ? weekSeconds(attempts, g.weekStart) : 0;
  const avg = examAverage(attempts);
  const gap = targetGap(g);
  return `<div class="kpi-grid ${compact ? 'compact' : ''}">
    <div class="kpi"><div class="kpi-label">今週の学習時間</div>
      <div class="kpi-value">${sec ? duration(sec) : '0分'}</div>
      ${budget ? `${bar(sec / 60 / budget)}<div class="kpi-sub">目安 ${duration(budget * 60)}</div>` : ''}</div>
    <div class="kpi"><div class="kpi-label">今週の課題</div>
      <div class="kpi-value">${doneN}<small> / ${items.length}</small></div>
      ${items.length ? `${bar(doneN / items.length)}<div class="kpi-sub">${doneN === items.length ? '✅ 完了' : `残り ${items.length - doneN}`}</div>` : ''}</div>
    <div class="kpi"><div class="kpi-label">本番の正答率 <small>直近${avg.count || 0}回</small></div>
      <div class="kpi-value">${avg.now == null ? '—' : `${Math.round(avg.now)}%`}</div>
      <div class="kpi-sub">${trend(avg.now, avg.before)}</div></div>
    ${hensachiKpi(stats?.hensachi, gap, g)}
  </div>`;
}

/** Headline session: the 第一志望's 回 with the best 合格可能性 (else the first one with an estimate). */
export function headlineSession(h) {
  const ok = (h?.sessions || []).filter((x) => x.estimate);
  if (!ok.length) return null;
  const first = ok.filter((x) => x.first);
  return (first.length ? first : ok).reduce((a, b) => (b.estimate.prob > a.estimate.prob ? b : a));
}
const probText = (p) => `${Math.round(p * 100)}%`;
const trendText = (t) => (t == null ? '—' : `${t > 0 ? '▲' : t < 0 ? '▼' : '→'} ${Math.abs(t).toFixed(1)}/月`);

function hensachiKpi(h, gap, g) {
  const x = headlineSession(h);
  if (!x) {
    return `<div class="kpi dark"><div class="kpi-label">推定偏差値</div><div class="kpi-value">—</div>
      <div class="kpi-sub">${esc(g?.firstName || '第一志望')}の過去問を全教科とくと推定できます</div></div>`;
  }
  const e = x.estimate;
  return `<div class="kpi dark"><div class="kpi-label">推定偏差値 <small>${esc(x.schoolName)} ${esc(x.label)}</small></div>
    <div class="kpi-value">${e.y.toFixed(1)} <small>/ 80%ライン ${x.y80}</small></div>
    <div class="kpi-sub">合格可能性 <b class="kpi-prob">${probText(e.prob)}</b> · ${trendText(x.trendPerMonth)}${gap && gap.risk.length ? ` · <span class="kpi-risk">ペース不足: ${gap.risk.join('・')}</span>` : ''}</div></div>`;
}

/** 偏差値の推移 for one 回: estimate per week against the 80% / 50% lines (reference lines, not series). */
export function hensachiChart(x) {
  const pts = x.series || [];
  if (pts.length < 2) return `<p class="muted small">${esc(x.schoolName)} ${esc(x.label)}: 推移は 2週以上の結果がたまると表示されます。</p>`;
  const W = 520, H = 180, L = 34, R = 92, T = 12, B = 24;
  const ys = pts.map((p) => p.y).concat([x.y80, x.y50]);
  const lo = Math.floor(Math.min(...ys) - 2), hi = Math.ceil(Math.max(...ys) + 2);
  const X = (i) => L + (W - L - R) * (i / (pts.length - 1));
  const Y = (v) => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  const ticks = [];
  for (let v = Math.ceil(lo / 5) * 5; v <= hi; v += 5) ticks.push(v);
  const ref = (v, label, cls) => `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" class="${cls}"></line>
    <text x="${W - R + 6}" y="${Y(v) + 4}" class="label ${cls}">${label} ${v}</text>`;
  const md = (iso) => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;
  const last = pts[pts.length - 1];
  return `<figure class="viz"><figcaption>${esc(x.schoolName)} ${esc(x.label)} <small class="muted">推定偏差値の推移</small></figcaption>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(x.schoolName)} 推定偏差値の推移">
      ${ticks.map((v) => `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" class="grid"></line><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" class="axis">${v}</text>`).join('')}
      ${ref(x.y80, '80%', 'ref80')}${ref(x.y50, '50%', 'ref50')}
      <polyline points="${pts.map((p, i) => `${X(i)},${Y(p.y)}`).join(' ')}" fill="none" stroke="#2563eb" stroke-width="2"></polyline>
      ${pts.map((p, i) => `<circle cx="${X(i)}" cy="${Y(p.y)}" r="${i === pts.length - 1 ? 4.5 : 3}" fill="#2563eb" stroke="#fff" stroke-width="1.5"><title>${md(p.week)}〜 推定偏差値 ${p.y} · 合格可能性 ${probText(p.prob)}</title></circle>`).join('')}
      <text x="${X(pts.length - 1)}" y="${Y(last.y) - 9}" text-anchor="end" class="label">${last.y.toFixed(1)}</text>
      <text x="${L}" y="${H - 6}" class="axis">${md(pts[0].week)}</text><text x="${W - R}" y="${H - 6}" text-anchor="end" class="axis">${md(last.week)}</text>
    </svg></figure>`;
}

/** 推定偏差値と合格可能性: one row per target 回 + the trend chart of each school's best 回. */
export function hensachiCard(h) {
  const list = h?.sessions || [];
  if (!list.length) return '';
  const COV = { school: '自校', other: '他' };
  const rows = list.map((x) => {
    const e = x.estimate;
    const cov = Object.entries(x.coverage || {});
    const own = cov.filter(([, c]) => c === 'school').length;
    const missing = cov.filter(([, c]) => !c).map(([k]) => SUBJ[k] || k);
    const status = !e ? '' : e.y >= x.y80 ? '<span class="tp-mark up">80%ライン以上</span>'
      : e.y >= x.y50 ? '<span class="tp-mark">50〜80%</span>' : '<span class="tp-mark weak">50%未満</span>';
    const reach = e && e.y >= x.y80 ? '到達' : x.reach80 ? `${x.reach80.slice(0, 4)}年${Number(x.reach80.slice(5))}月ごろ` : '—';
    return `<tr class="${x.first ? 'first' : ''}"><td>${esc(x.schoolName)} <small class="muted">${esc(x.label)}</small>${x.first ? ' <span class="badge">第一志望</span>' : ''}</td>
      <td class="num">${e ? `<b>${e.y.toFixed(1)}</b>` : '—'}</td><td class="num muted">${x.y80} / ${x.y50}</td>
      <td class="num">${e ? `<b>${probText(e.prob)}</b>` : '—'} ${status}</td>
      <td class="num">${trendText(x.trendPerMonth)}</td><td class="num">${reach}</td>
      <td class="small muted" title="${esc(cov.map(([k, c]) => `${SUBJ[k] || k}: ${c ? COV[c] : 'なし'}`).join(' / '))}">${e ? `自校の過去問 ${own}/${cov.length}教科` : `未受験: ${esc(missing.join('・'))}`}</td></tr>`;
  }).join('');
  const bySchool = {};
  for (const x of list) if (x.estimate && (!bySchool[x.school] || x.estimate.prob > bySchool[x.school].estimate.prob)) bySchool[x.school] = x;
  const a = h.assumptions || {};
  return `<div class="card p-card hensachi-card"><h2>推定偏差値と合格可能性 <small class="muted">四谷大塚の 80% / 50% ラインと比べた推定</small></h2>
    <div class="table-scroll"><table><tr><th>学校・回</th><th>推定偏差値</th><th>80% / 50%</th><th>合格可能性</th><th>傾向</th><th>80%到達見込み</th><th>もとにした結果</th></tr>${rows}</table></div>
    <div class="hensachi-charts">${Object.values(bySchool).map(hensachiChart).join('')}</div>
    <details class="small muted"><summary>この推定について</summary>
      <p>アプリで解いた各校の過去問（全問）の最近の得点率から本番の点数を見積もり、公表された受験者平均と合格最低点（未公表の回は合格率から推定）に当てはめ、
      合格ライン上の点数＝四谷大塚 50% 偏差値、80% ライン＝合格可能性 80% になるように換算しています。受験生の点数の散らばり（各教科 満点の${Math.round((a.spread ?? 0.18) * 100)}%）、
      教科間の相関（${a.rho ?? 0.6}）、当日のぶれは公表されていないため仮定です。模試の偏差値とは別の参考値です。自校の過去問がない教科は他の問題の得点率で代用しています（「他」）。</p>
      ${h.source ? `<p>出典: ${esc(h.source)}</p>` : ''}</details>
  </div>`;
}

/** 弱点分析: weakest 分野 with accuracy, answers, and whether practice is helping. */
export function weakAnalysis(stats, attempts, n = 4) {
  const weak = Object.entries(stats?.topics || {}).filter(([, t]) => t.weak).sort(([, a], [, b]) => a.mastery - b.mastery).slice(0, n);
  const imp = Object.fromEntries(practiceImprovement(attempts).map((x) => [`${x.subject}|${x.topic}`, x]));
  if (!weak.length) return '<div class="card p-card"><h2>弱点分析</h2><p class="ok">いま弱点の分野はありません。</p></div>';
  return `<div class="card p-card"><h2>弱点分析</h2>${weak.map(([t, v]) => {
    const x = imp[`${v.subject}|${t}`];
    const note = !x ? '弱点練習はまだ — 練習をすすめてください'
      : x.improved ? `練習で改善中 ${pct(x.before)} → ${pct(x.after)}` : `練習中（直近 ${pct(x.after)}）`;
    return `<div class="weak-row ${v.mastery < 0.4 ? 'sev' : ''}">
      <div class="weak-title">${esc(t)} <small>${SUBJ[v.subject] || ''}</small><span class="weak-pct">${pct(v.mastery)}</span></div>
      <div class="weak-sub">${v.correct} / ${v.attempts} 問正解</div>
      <div class="weak-note">${x?.improved ? '📈' : '💡'} ${note}</div></div>`;
  }).join('')}</div>`;
}

/**
 * 教科別の正答率 with every 分野 inside (click a 教科): weakest first, 習熟度 bar, correct / answered,
 * 弱点 / 練習で改善中 / 練習中 marks. 分野 with too few answers say so (少).
 */
export function subjectBreakdown(stats, attempts) {
  const subjects = Object.entries(SUBJ).filter(([k]) => stats?.subjects?.[k]);
  if (!subjects.length) return '<div class="card p-card"><h2>教科別の正答率</h2><p class="muted">まだありません</p></div>';
  const imp = Object.fromEntries(practiceImprovement(attempts).map((x) => [`${x.subject}|${x.topic}`, x]));
  const rows = subjects.map(([k, label]) => {
    const sub = stats.subjects[k];
    const topics = Object.entries(stats.topics || {}).filter(([, t]) => t.subject === k)
      .sort(([, a], [, b]) => (a.mastery ?? 2) - (b.mastery ?? 2));
    const weakN = topics.filter(([, t]) => t.weak).length;
    const list = topics.map(([name, t]) => {
      const x = imp[`${k}|${name}`];
      const mark = x?.improved ? '<span class="tp-mark up">📈 改善中</span>' : t.weak ? '<span class="tp-mark weak">弱点</span>'
        : x ? '<span class="tp-mark">練習中</span>' : '';
      return `<div class="tp-row ${t.weak ? 'weak' : ''}"><span class="tp-name">${esc(name)}${t.confident ? '' : ' <small class="muted">少</small>'}</span>
        <div class="kpi-bar"><div style="width:${Math.round((t.mastery || 0) * 100)}%"></div></div>
        <b>${pct(t.mastery)}</b><small class="muted">${t.correct}/${t.attempts}</small>${mark}</div>`;
    }).join('');
    return `<details class="subj"><summary class="subj-row"><span>${label}</span><div class="kpi-bar"><div style="width:${Math.round((sub.accuracy || 0) * 100)}%"></div></div>
        <b>${pct(sub.accuracy)}</b><small class="muted">${sub.attempts}問</small>${weakN ? `<span class="tp-mark weak">弱点 ${weakN}</span>` : ''}</summary>
      <div class="tp-list">${list || '<p class="muted small">分野の記録はまだありません</p>'}</div></details>`;
  }).join('');
  return `<div class="card p-card"><h2>教科別の正答率 <small class="muted">教科をクリックで分野ごと</small></h2>${rows}</div>`;
}

/** 今週の課題 as a timeline (no links: the parent watches, the child solves). */
export function weekTimeline(goals) {
  const asg = goals?.assignments;
  if (!asg?.items?.length) return '';
  const done = goals.assignmentsDone || [];
  const KIND = { new: '新しい問題', retake: '2回目', review: 'やり直し' };
  return `<div class="card p-card"><h2>今週の課題</h2><div class="timeline">${asg.items.map((it, i) => `
    <div class="tl-row ${done[i] ? 'done' : ''}"><span class="tl-dot"></span>
      <div><div class="tl-meta">${KIND[it.kind] || ''} · ${it.minutes}分</div>
        <div class="tl-title">${done[i] ? '✅ ' : ''}${esc(it.label)}</div></div></div>`).join('')}</div></div>`;
}

