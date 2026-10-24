import { getTopicStats, loadAllItems, createAttempt, currentUser } from '../api.js';
import { qimg } from '../qimg.js';
import { kumiwakeSim, toruPoints } from '../simulator.js';

// 取るべき問題: #/toru (child) / #/toru?uid=<child> (parent, read-only)
// 組分け questions that most test-takers got right (正答率 ≥ threshold, from the 正答率一覧 via build.py item.rate)
// but the child's latest answer is wrong or blank -> the points that cost the most 偏差値. One practice set per 教科.
const SUBJ = { math: '算数', japanese: '国語', science: '理科', social: '社会' };
const ORDER = ['math', 'japanese', 'science', 'social'];
const THRESHOLDS = [40, 50, 60, 70];
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** {subject: [{item, rate, tries}]} — wrong/blank (latest try) items with 正答率 ≥ threshold, highest 正答率 first. */
export function toruList(itemHistory, items, threshold = 50) {
  const out = {};
  for (const it of items) {
    const h = itemHistory?.[it.id];
    if (it.rate == null || it.rate < threshold || !h || h.correct) continue;
    (out[it.subject] ||= []).push({ item: it, rate: it.rate, tries: h.tries });
  }
  for (const k of Object.keys(out)) out[k].sort((a, b) => b.rate - a.rate || a.item.id.localeCompare(b.item.id));
  return out;
}

function section(k, rows, readOnly) {
  return `<div class="card toru-subject">
    <div class="toru-head"><h2>${SUBJ[k] || k} <small class="muted">${rows.length}問</small></h2>
      ${readOnly ? '' : `<button class="primary" data-start="${k}">この${rows.length}問を練習する</button>`}</div>
    <table class="toru-table"><tr><th>正答率</th><th>問題</th><th>分野</th><th></th></tr>
    ${rows.map(({ item: it, rate, tries }) => `<tr>
      <td><b>${Math.round(rate)}%</b></td>
      <td>${esc(it.examLabel)} 大問${it.big} ${esc(it.label)}${tries > 1 ? ` <small class="muted">${tries}回目も×</small>` : ''}</td>
      <td class="muted">${esc(it.topic || '')}</td>
      <td class="qcell">${qimg(it.image, 'thumb')}</td></tr>`).join('')}</table></div>`;
}

export async function renderToru({ app }, arg) {
  const qs = new URLSearchParams(String(arg || '').split('?')[1] || '');
  const uid = qs.get('uid');
  const readOnly = Boolean(uid) || Boolean(currentUser()?.admin);
  let threshold = Number(qs.get('min')) || 50;
  app.innerHTML = '<div class="card">読み込み中…</div>';
  const [stats, all] = await Promise.all([getTopicStats(uid), loadAllItems()]);
  const items = all.items.filter((it) => it.rate != null);

  const draw = () => {
    const list = toruList(stats.itemHistory, items, threshold);
    const subs = ORDER.filter((k) => list[k]?.length);
    const total = subs.reduce((n, k) => n + list[k].length, 0);
    const rounds = stats.hensachi?.kumiwake?.rounds || [];
    const last = rounds[rounds.length - 1];
    let gain = '';
    if (last) {
      const pts = toruPoints(last, list), now = kumiwakeSim(last), then = kumiwakeSim(last, pts);
      const got = Object.values(pts).reduce((a, b) => a + b, 0);
      if (now && then && got) {
        gain = then.total != null && last.total != null
          ? `第${last.round}回のこの問題をぜんぶ取れていたら：4科の偏差値 <b>${last.total.toFixed(1)} → ${then.total.toFixed(1)}</b>（+${got}点）`
          : `第${last.round}回のこの問題をぜんぶ取れていたら：${Object.entries(pts).filter(([, p]) => p).map(([s, p]) => `${SUBJ[s]} ${last.subjects[s].y.toFixed(1)} → <b>${then.subjects[s].toFixed(1)}</b>（+${p}点）`).join('、')}`;
      }
    }
    app.innerHTML = `
      <div class="card">
        ${uid ? `<p><a href="#/parent/${encodeURIComponent(uid)}">← 生徒の記録へ</a></p>` : ''}
        <h1>🎯 取るべき問題</h1>
        <p>組分けテストで、受験者の<b>${threshold}%以上が正解</b>しているのに、前回まちがえた（または空らんだった）問題です。
          ここを取れるようになると、偏差値がいちばん上がりやすくなります。</p>
        ${gain ? `<p class="toru-gain">📈 ${gain}</p>` : ''}
        <p class="toru-th">正答率 ${THRESHOLDS.map((t) => `<button class="chip ${t === threshold ? 'on' : ''}" data-th="${t}">${t}%以上</button>`).join(' ')}
          <span class="muted">· ${total}問</span></p>
        ${readOnly ? '<p class="hint">練習はお子さんの画面の「取るべき問題」から始められます。</p>' : ''}
      </div>
      ${subs.length ? subs.map((k) => section(k, list[k], readOnly)).join('')
        : `<div class="card"><p class="ok">正答率 ${threshold}%以上の問題は、ぜんぶ取れています 🎉</p>
           <p class="muted">組分けテストをアプリで解くと、ここに出てきます。</p></div>`}`;
    for (const b of app.querySelectorAll('button[data-th]')) b.onclick = () => { threshold = Number(b.dataset.th); draw(); };
    for (const t of app.querySelectorAll('.qcell .thumb')) t.onclick = () => t.classList.toggle('open');
    for (const b of app.querySelectorAll('button[data-start]')) {
      b.onclick = async () => {
        const k = b.dataset.start;
        const ids = list[k].map((r) => r.item.id);
        b.disabled = true; b.textContent = '準備中…';
        try {
          const id = await createAttempt(null, 'practice', {
            items: ids, subject: k, title: `取るべき問題 ${SUBJ[k]}（正答率${threshold}%以上）`,
            timeLimitMin: Math.max(5, Math.ceil(ids.length * 2 / 5) * 5),
          });
          location.hash = `#/attempt/${id}`;
        } catch (e) {
          console.error(e);
          alert('練習を開始できませんでした: ' + e.message);
          b.disabled = false; b.textContent = `この${ids.length}問を練習する`;
        }
      };
    }
  };
  draw();
}
