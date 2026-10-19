import { describe, expect, it } from 'vitest';
import { planCard } from '../src/views/plan.js';
import { parentRedirect } from '../src/roles.js';

const stats = {
  goals: { weekStart: '2026-10-19' },
  plan: {
    examDate: '2028-02-01', newBudget: 119, finishWeek: '2026-10-26', totalExams: 3,
    milestones: [{ date: '2026-10-28', label: '6年スタート' }, { date: '2028-02-01', label: '入試：共立女子', exam: true }],
    history: [{ weekStart: '2026-10-12', items: 2, done: 1, minutes: 80, doneMinutes: 50, missed: ['組分け 第2回 理科'] }],
    weeks: [
      { weekStart: '2026-10-19', grade: 5, phase: '5年', items: [{ examId: 'a', label: '組分け 第3回 算数', minutes: 50 }] },
      { weekStart: '2026-10-26', grade: 5, phase: '5年', items: [{ examId: 'b', label: '共立 2024 算数', minutes: 25 }] },
      { weekStart: '2026-11-02', grade: 5, phase: '5年', items: [] },
      { weekStart: '2026-11-23', grade: 5, phase: '5年', items: [{ examId: 'planned:kumiwake_202611_math', label: '組分け 11月（予定） 算数', minutes: 50, planned: true }] },
    ],
  },
};

describe('全体計画', () => {
  it('renders history, current week, milestones in their week and empty weeks', () => {
    const html = planCard(stats, { now: new Date('2026-10-20T00:00:00Z') });
    expect(html).toContain('全体計画');
    expect(html).toContain('⚠️ 1 / 2');
    expect(html).toContain('組分け 第2回 理科');            // やり残し
    expect(html).toContain('今週');
    expect(html).toContain('🚩 10/28 6年スタート');          // inside the 10/26 week row
    expect(html).toContain('href="#/exam/b?g=5"');
    expect(html).toContain('やり直し・新しく追加される');
    expect(html).toContain('2026年10月');
    expect(planCard(stats, { links: false })).not.toContain('href="#/exam/');
    expect(html).toContain('<span class="planned">組分け 11月（予定） 算数</span>');   // not linkable yet
    expect(html).not.toContain('href="#/exam/planned:');
    expect(planCard({})).toBe('');
  });

  it('is a student page (parents see it on the child page)', () => {
    expect(parentRedirect({ admin: true }, 'plan')).toBe(true);
  });
});
