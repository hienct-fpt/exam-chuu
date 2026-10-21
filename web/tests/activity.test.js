import { describe, expect, it } from 'vitest';
import { kindOf, activityCounts, practiceImprovement, activityLine } from '../src/activity.js';

const items = (topic, ok, n, subject = 'math') => Object.fromEntries(Array.from({ length: n }, (_, i) =>
  [`${topic}-${i}`, { topic, subject, correct: i < ok, pending: false }]));
const att = (t, kind, perItem) => ({ status: 'graded', submittedAt: t, result: { perItem },
  ...(kind === 'exam' ? { examId: 'e', mode: 'exam' } : kind === 'range' ? { examId: 'e', mode: 'practice', gradeFilter: 5 }
    : kind === 'redo' ? { redoOf: 'e', mode: 'practice' } : { mode: 'practice', items: ['x'] }) });

describe('activity by kind', () => {
  it('classifies and counts submitted attempts only', () => {
    expect(kindOf({ examId: 'e', mode: 'exam' })).toBe('exam');
    expect(kindOf({ examId: 'e', mode: 'practice', gradeFilter: 5 })).toBe('range');
    expect(kindOf({ redoOf: 'e', mode: 'practice' })).toBe('redo');
    expect(kindOf({ mode: 'practice', items: ['x'] })).toBe('practice');
    expect(activityCounts([att('1', 'exam', {}), att('2', 'exam', {}), { examId: 'e', mode: 'exam', status: 'in_progress' },
      att('3', 'practice', {}), att('4', 'redo', {})])).toEqual({ exam: 2, range: 0, redo: 1, practice: 1 });
  });

  it('a practiced 分野 is improved when it rises by 15pt or crosses 60%', () => {
    const list = [
      att('2026-10-01', 'exam', { ...items('割合', 1, 4), ...items('速さ', 3, 4), ...items('図形', 2, 5) }),
      att('2026-10-05', 'practice', { ...items('割合', 3, 5), ...items('速さ', 3, 4) }),   // 割合 25% -> 60%: improved
      att('2026-10-09', 'exam', { ...items('割合', 2, 2) }),                              // 速さ 75% -> 75%: not improved
      att('2026-10-10', 'practice', { ...items('新分野', 3, 3) }),                         // nothing before: can't compare
    ];
    const imp = practiceImprovement(list);
    const by = Object.fromEntries(imp.map((x) => [x.topic, x]));
    expect(by['割合']).toMatchObject({ before: 0.25, improved: true });
    expect(by['割合'].after).toBeCloseTo(5 / 7);
    expect(by['速さ']).toMatchObject({ before: 0.75, after: 0.75, improved: false });
    expect(by['新分野']).toMatchObject({ before: null, improved: false });
    expect(by['図形']).toBeUndefined();                                                  // never practiced
    expect(imp[0].topic).toBe('割合');
    expect(activityLine(list)).toContain('本番 <b>2</b>回');
    expect(activityLine(list)).toContain('練習で改善 <b>1</b>分野');
    expect(activityLine(list)).toContain('練習した 3分野');
  });
});
