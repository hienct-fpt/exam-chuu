import { describe, expect, it } from 'vitest';
import { kumiwakeCard, kpiCards, examAverage, subjectOfAttempt } from '../src/parent-ui.js';

const ex = (id, t, percent) => ({ status: 'graded', examId: id, mode: 'exam', submittedAt: t, percent });

describe('本番の正答率 per 教科', () => {
  it('finds the subject and averages per subject with the change vs the 5 before', () => {
    expect(subjectOfAttempt({ examId: 'kyoritsu_2026_2-1_math' })).toBe('math');
    expect(subjectOfAttempt({ result: { perItem: { a: { subject: 'social' } } } })).toBe('social');
    const list = [ex('k_math', '2026-10-10', 80), ex('k_math', '2026-10-01', 60), ex('k_social', '2026-10-05', 50)];
    expect(examAverage(list, 1, 'math')).toEqual({ now: 80, before: 60, count: 1 });
    const html = kpiCards({ goals: {} }, list);
    expect(html).toContain('教科ごと 直近5回');
    expect(html).toContain('<span>算数</span><b>70%</b>');
    expect(html).toContain('<span>社会</span><b>50%</b>');
    expect(html).not.toContain('<span>理科</span>');
  });
});

describe('組分けテストの推定偏差値', () => {
  it('table per round, 4科 only when complete, trend row, chart from 2 rounds', () => {
    const k = { rounds: [
      { year: '2026', round: 1, total: 52.3, subjects: { math: { y: 56.1 }, japanese: { y: 44.0 }, science: { y: 50 }, social: { y: 51 } } },
      { year: '2026', round: 2, total: 54.0, subjects: { math: { y: 58.2 } } },
    ], trend: { total: 1.7, math: 2.1 } };
    const html = kumiwakeCard(k);
    expect(html).toContain('第1回');
    expect(html).toContain('<b>52.3</b>');
    expect(html).toContain('class="num lo"><b>44.0</b>');
    expect(html).toContain('▲ 2.1');
    expect(html).toContain('4科の推定偏差値');
    expect(html).toContain('直接比べられません');
    expect(kumiwakeCard({ rounds: [] })).toBe('');
  });
});
