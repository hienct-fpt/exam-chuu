// Who sees which page.
// 保護者 (admin) accounts don't take tests: the student pages send them to the parent page instead
// (they still open a child's result there, #/result/{id}?uid=...).
// 試験一覧 / 計画 / 問題の確認 are the parent's: the child works from 今週の課題 (ダッシュボード), 練習 and 履歴.
const STUDENT_PAGES = new Set(['exam', 'attempt', 'dashboard', 'practice', 'history', 'redo']);
const PARENT_PAGES = new Set(['', 'plan', 'preview']);

/** Where to send `user` instead of `page`, or null when the page is theirs. */
export function roleRedirect(user, page) {
  const p = page || '';
  if (user?.admin) return STUDENT_PAGES.has(p) ? '#/parent' : null;
  return PARENT_PAGES.has(p) ? '#/dashboard' : null;
}
export const parentRedirect = (user, page) => roleRedirect(user, page) === '#/parent';
