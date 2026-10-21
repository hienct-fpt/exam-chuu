import { describe, expect, it } from 'vitest';
import { examAverage, targetGap, kpiCards, weakAnalysis, weekTimeline } from '../src/parent-ui.js';

const ex = (t, percent, extra = {}) => ({ status: 'graded', examId: 'e', mode: 'exam', submittedAt: t, percent, ...extra });

describe('保護者 KPI', () => {
  it('recent 本番 average and trend ignore practice sets', () => {
    const list = [ex('2026-10-10', 80), ex('2026-10-09', 60), { status: 'graded', mode: 'practice', items: ['x'], submittedAt: '2026-10-11', percent: 10 },
      ex('2026-09-01', 50), ex('2026-08-01', 50)];
    const a = examAverage(list, 2);
    expect(a).toEqual({ now: 70, before: 50, count: 2 });
  });
  it('gap to the final target and at-risk subjects', () => {
    const g = targetGap({ subjects: { math: { level: 0.5, target: 0.7, atRisk: true }, social: { level: 0.7, target: 0.7 }, science: { level: null, target: 0.7 } } });
    expect(g.level).toBeCloseTo(0.6); expect(g.target).toBeCloseTo(0.7); expect(g.risk).toEqual(['算数']);
    expect(targetGap({})).toBeNull();
  });
  it('cards render with and without data', () => {
    const stats = { goals: { firstName: '共立', weekStart: '2026-10-19', assignments: { budget: 180, items: [{ label: 'a', minutes: 60, kind: 'new' }, { label: 'b', minutes: 30, kind: 'review' }] }, assignmentsDone: [true, false],
      subjects: { math: { level: 0.55, target: 0.7, atRisk: true } } } };
    const html = kpiCards(stats, [ex('2026-10-20T01:00:00Z', 72, { activeSec: 3600 })]);
    expect(html).toContain('1時間');          // this week's time
    expect(html).toContain('1<small> / 2');
    expect(html).toContain('72%');
    expect(kpiCards({}, [])).toContain('推定偏差値');
    expect(weekTimeline(stats.goals)).toContain('✅ a');
    expect(weakAnalysis({ topics: {} }, [])).toContain('弱点の分野はありません');
  });
});
