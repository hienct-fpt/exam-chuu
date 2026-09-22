import { loadIndex, listAttempts } from '../api.js';

const SUBJ = { math: '算数', japanese: '国語', science: '理科', social: '社会' };
const GRADE_KEY = 'exam-chuu.grade';
const SCHOOL_KEY = 'exam-chuu.school';
const SCHOOLS = [['all', 'すべて'], ['kyoritsu', '共立女子'], ['shinagawa', '品川女子学院']];

export function getGradePref() {
  try { return localStorage.getItem(GRADE_KEY) || '5'; } catch { return '5'; }
}
function setGradePref(v) { try { localStorage.setItem(GRADE_KEY, v); } catch { /* ignore */ } }
export function getSchoolPref() {
  try { return localStorage.getItem(SCHOOL_KEY) || 'all'; } catch { return 'all'; }
}
function setSchoolPref(v) { try { localStorage.setItem(SCHOOL_KEY, v); } catch { /* ignore */ } }

export async function renderHome({ app }) {
  const [fullIndex, attempts] = await Promise.all([loadIndex(), listAttempts(200)]);
  const grade = getGradePref(); // '5' | 'all'
  const school = getSchoolPref(); // 'all' | school id
  const index = school === 'all' ? fullIndex : fullIndex.filter((e) => e.school === school);
  const best = {};
  for (const a of attempts) {
    if (a.status !== 'graded') continue;
    const k = `${a.examId}|${a.gradeFilter || 'all'}`;
    if (!best[k] || a.percent > best[k].percent) best[k] = a;
  }
  const inProg = new Set(attempts.filter((a) => a.status === 'in_progress').map((a) => `${a.examId}|${a.gradeFilter || 'all'}`));
  const q = grade === '5' ? '?g=5' : '';
  const scopeKey = (id) => `${id}|${grade === '5' ? '5' : 'all'}`;
  const count = (e) => (grade === '5' ? (e.grade_counts?.['5'] || 0) : e.item_count);

  app.innerHTML = `
    <div class="card" style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
      <h1 style="margin:0">試験一覧</h1>
      <div class="seg" id="gradeseg">
        <button data-g="5" class="${grade === '5' ? 'on' : ''}">小5までの問題</button>
        <button data-g="all" class="${grade === 'all' ? 'on' : ''}">全問（小6含む）</button>
      </div>
      <span class="muted">${grade === '5' ? '小5までに習う内容だけを出題します（小6の比・相似・点の移動などは除外）' : '本番と同じ全問を出題します'}</span>
      <div class="seg" id="schoolseg">
        ${SCHOOLS.map(([id, label]) => `<button data-s="${id}" class="${school === id ? 'on' : ''}">${label}</button>`).join('')}
      </div>
    </div>
    <div class="exam-grid">${index.map((e) => {
      const n = count(e);
      const b = best[scopeKey(e.id)];
      return `<a class="card exam-tile ${n ? '' : 'disabled'}" href="#/exam/${e.id}${q}">
      <div class="muted">${e.school_name}</div>
      <h2>${e.year}年度 ${e.session_label} ${SUBJ[e.subject] || e.subject_label}</h2>
      <div class="muted">${grade === '5' ? `小5 ${n} 問 <small>(全 ${e.item_count} 問)</small>` : `${e.item_count} 問 <small>(小5 ${e.grade_counts?.['5'] || 0} / 小6 ${e.grade_counts?.['6'] || 0})</small>`} · ${e.time_limit_min} 分</div>
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
}
