// 保護者 (admin) accounts don't take tests: the student pages send them to the parent page instead
// (they still open a child's result there, #/result/{id}?uid=...).
const STUDENT_PAGES = new Set(['', 'exam', 'attempt', 'dashboard', 'practice', 'history', 'redo', 'plan']);

export const parentRedirect = (user, page) => Boolean(user?.admin && STUDENT_PAGES.has(page || ''));
