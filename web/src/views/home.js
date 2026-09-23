import { loadIndex, listAttempts, examTitle } from '../api.js';

const SUBJ = { math: '算数', japanese: '国語', science: '理科', social: '社会' };
const GRADE_KEY = 'exam-chuu.grade';
const SCHOOL_KEY = 'exam-chuu.school';
const SCHOOLS = [['all', 'すべて'], ['kyoritsu', '共立女子'], ['shinagawa', '品川女子学院'], ['minsan', 'みんなの算数']];
/** Grade scope options: pref value -> [label, description]. 'all' = 全問. */
export const GRADES = [
  ['4', '小4までの問題', '小4までに習う内容だけを出題します（計算・角度・植木算・周期など）'],
  ['5', '小5までの問題', '小5までに習う内容だけを出題します（小6の比・相似・点の移動などは除外）'],
  ['all', '全問（小6含む）', '本番と同じ全問を出題します'],
];

export function getGradePref() {
  try {
    const v = localStorage.getItem(GRADE_KEY) || '5';
    return GRADES.some(([g]) => g === v) ? v : '5';
  } catch { return '5'; }
}
/** Numeric grade filter for the current pref (null = 全問). */
export function gradeFilterFromPref(pref = getGradePref()) {
  return pref === 'all' ? null : Number(pref);
}
/** Number of items in an index entry with grade <= g (g = null -> all items). */
export function countUpTo(e, g) {
  if (!g) return e.item_count;
  return Object.entries(e.grade_counts || {}).reduce((n, [k, v]) => (Number(k) && Number(k) <= g ? n + v : n), 0);
}
/** "小4 3 / 小5 17 / 小6 7" breakdown over the exam's numeric grade buckets (untagged '?' skipped). */
export function gradeBreakdown(e) {
  return Object.entries(e.grade_counts || {}).filter(([k, v]) => Number(k) && v).sort(([a], [b]) => a - b)
    .map(([k, v]) => `小${k} ${v}`).join(' / ');
}
function setGradePref(v) { try { localStorage.setItem(GRADE_KEY, v); } catch { /* ignore */ } }
export function getSchoolPref() {
  try { return localStorage.getItem(SCHOOL_KEY) || 'all'; } catch { return 'all'; }
}
function setSchoolPref(v) { try { localStorage.setItem(SCHOOL_KEY, v); } catch { /* ignore */ } }
const YEAR_KEY = 'exam-chuu.year';
function getYearPref() { try { return localStorage.getItem(YEAR_KEY) || 'all'; } catch { return 'all'; } }
function setYearPref(v) { try { localStorage.setItem(YEAR_KEY, v); } catch { /* ignore */ } }
/** Distinct years of an index slice, newest first (min-san sets carry year_label for bucketed years). */
export function yearOptions(index) {
  const m = new Map();
  for (const e of index) if (e.year) m.set(String(e.year), e.year_label || `${e.year}年度`);
  return [...m.entries()].sort(([a], [b]) => Number(b) - Number(a));
}

export async function renderHome({ app }) {
  const [fullIndex, attempts] = await Promise.all([loadIndex(), listAttempts(200)]);
  const grade = getGradePref(); // '4' | '5' | 'all'
  const gf = gradeFilterFromPref(grade); // number | null
  const school = getSchoolPref(); // 'all' | school id
  const bySchool = school === 'all' ? fullIndex : fullIndex.filter((e) => e.school === school);
  const years = yearOptions(bySchool);
  const showYears = bySchool.length > 12 && years.length > 1;
  const year = showYears && years.some(([y]) => y === getYearPref()) ? getYearPref() : 'all';
  const index = year === 'all' ? bySchool : bySchool.filter((e) => String(e.year) === year);
  const best = {};
  for (const a of attempts) {
    if (a.status !== 'graded') continue;
    const k = `${a.examId}|${a.gradeFilter || 'all'}`;
    if (!best[k] || a.percent > best[k].percent) best[k] = a;
  }
  const inProg = new Set(attempts.filter((a) => a.status === 'in_progress').map((a) => `${a.examId}|${a.gradeFilter || 'all'}`));
  const q = gf ? `?g=${gf}` : '';
  const scopeKey = (id) => `${id}|${gf || 'all'}`;
  const count = (e) => countUpTo(e, gf);
  const desc = GRADES.find(([g]) => g === grade)[2];

  app.innerHTML = `
    <div class="card" style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
      <h1 style="margin:0">試験一覧</h1>
      <div class="seg" id="gradeseg">
        ${GRADES.map(([g, label]) => `<button data-g="${g}" class="${grade === g ? 'on' : ''}">${label}</button>`).join('')}
      </div>
      <span class="muted">${desc}</span>
      <div class="seg" id="schoolseg">
        ${SCHOOLS.map(([id, label]) => `<button data-s="${id}" class="${school === id ? 'on' : ''}">${label}</button>`).join('')}
      </div>
      ${showYears ? `<div class="chips" id="yearchips" style="flex-basis:100%">
        <button class="chip ${year === 'all' ? 'on' : ''}" data-y="all">全年度 <small>${bySchool.length}</small></button>
        ${years.map(([y, label]) => `<button class="chip ${year === y ? 'on' : ''}" data-y="${y}">${label} <small>${bySchool.filter((e) => String(e.year) === y).length}</small></button>`).join('')}
      </div>` : ''}
    </div>
    <div class="exam-grid">${index.map((e) => {
      const n = count(e);
      const b = best[scopeKey(e.id)];
      return `<a class="card exam-tile ${n ? '' : 'disabled'}" href="#/exam/${e.id}${q}">
      <div class="muted">${e.school_name}</div>
      <h2>${examTitle(e)} ${SUBJ[e.subject] || e.subject_label}</h2>
      ${e.schools ? `<div class="muted small">${e.schools.slice(0, 4).join('・')}${e.schools.length > 4 ? ` ほか${e.schools.length - 4}校` : ''}</div>` : ''}
      <div class="muted">${gf ? `小${gf}まで ${n} 問 <small>(全 ${e.item_count} 問)</small>` : `${e.item_count} 問 <small>(${gradeBreakdown(e)})</small>`} · ${e.time_limit_min} 分</div>
      <div style="margin-top:8px">
        ${inProg.has(scopeKey(e.id)) ? '<span class="badge submitted">続きから</span> ' : ''}
        ${b ? `<span class="badge graded">最高 ${b.score}/${b.max} (${b.percent}%)</span>` : '<span class="badge">未受験</span>'}
      </div></a>`;
    }).join('')}</div>`;

  app.querySelector('#gradeseg').onclick = (e) => {
    const g = e.target.dataset.g;
    if (!g) return;
    setGradePref(g);
    renderHome({ app });
  };
  app.querySelector('#schoolseg').onclick = (e) => {
    const s = e.target.dataset.s;
    if (!s) return;
    setSchoolPref(s);
    renderHome({ app });
  };
  app.querySelector('#yearchips')?.addEventListener('click', (e) => {
    const y = e.target.closest('[data-y]')?.dataset.y;
    if (!y) return;
    setYearPref(y);
    renderHome({ app });
  });
}
