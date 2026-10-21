// 保護者 with several linked children: which child the 計画 / 子どものページ show. The choice is kept per browser.
const KEY = 'exam-chuu.child';
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export function selectedChild(kids) {
  if (!kids?.length) return null;
  let uid = null;
  try { uid = localStorage.getItem(KEY); } catch { /* private mode */ }
  return kids.find((k) => k.uid === uid) || kids[0];
}
export function setSelectedChild(uid) {
  try { localStorage.setItem(KEY, uid); } catch { /* private mode */ }
}

/** Child switch (only with 2+ children). `href(kid)` -> link per child; without it the buttons carry data-child. */
export function childPicker(kids, current, href = null) {
  if (!kids || kids.length < 2) return '';
  return `<div class="seg child-picker">${kids.map((k) => (href
    ? `<a class="button ${k.uid === current?.uid ? 'on' : ''}" href="${href(k)}" data-child="${esc(k.uid)}">${esc(k.name)}</a>`
    : `<button class="${k.uid === current?.uid ? 'on' : ''}" data-child="${esc(k.uid)}">${esc(k.name)}</button>`)).join('')}</div>`;
}

/** Clicks on a picker remember the child; `rerender` runs for the button variant. */
export function bindChildPicker(root, rerender = null) {
  for (const el of root.querySelectorAll('.child-picker [data-child]')) {
    el.addEventListener('click', () => { setSelectedChild(el.dataset.child); if (rerender && el.tagName === 'BUTTON') rerender(); });
  }
}
