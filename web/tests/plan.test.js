import { describe, expect, it } from 'vitest';
import { planCard, progressSeries, cumulativeChart, weeklyBars } from '../src/views/plan.js';
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
      { weekStart: '2026-11-09', grade: null, phase: '6年 後期', items: [{ examId: 'k24', label: '共立 2024 算数', minutes: 45, retake: true }] },
      { weekStart: '2026-11-23', grade: 5, phase: '5年', items: [{ examId: 'planned:kumiwake_202611_math', label: '組分け 11月（予定） 算数', minutes: 50, planned: true }] },
    ],
  },
};

describe('全体計画', () => {
  it('renders history, current week, milestones in their week and empty weeks', () => {
    const html = planCard(stats, { now: new Date('2026-10-20T00:00:00Z') });
    expect(html).toContain('全体計画');
    expect(html).toContain('⚠ やり残し 1週');
    expect(html).toContain('今週');
    expect(html).toContain('🚩 10/28 6年スタート');          // inside the 10/26 week row (chip)
    expect(html).toContain('href="#/exam/b?g=5"');
    expect(html).toContain('<span class="muted">やり直し</span>');
    expect(html).toContain('2026年10月');
    expect(planCard(stats, { links: false })).not.toContain('href="#/exam/');
    expect(html).toContain('組分け 11月（予定） 算数</span>');   // not linkable yet
    expect(html).not.toContain('<figure');                  // charts only on the parent's card
    expect(html).not.toContain('href="#/exam/planned:');
    expect(html).toContain('<span class="badge retake">2回目</span><a href="#/exam/k24">');
    expect(planCard({})).toBe('');
  });

  it('parent card: 予定 / 実績 series and charts', () => {
    const st = { ...stats, goals: { weekStart: '2026-10-19', assignments: { items: [{ label: 'x', minutes: 50 }, { label: 'y', minutes: 30 }] }, assignmentsDone: [true, false] } };
    const s = progressSeries(st);
    expect(s.map((p) => p.week)).toEqual(['2026-10-12', '2026-10-19', '2026-10-26', '2026-11-02', '2026-11-09', '2026-11-23']);
    expect(s[0]).toMatchObject({ plan: 80, done: 50, missed: ['組分け 第2回 理科'] });
    expect(s[1]).toMatchObject({ plan: 80, done: 50, current: true, missed: ['y'] });   // this week from goals, not plan.weeks
    expect(s[2]).toMatchObject({ plan: 25, done: null, future: true });
    const cum = cumulativeChart(s);
    expect(cum).toContain('累計の学習時間');
    expect(cum).toContain('実績 1.7h / 予定 2.7h');          // 100 of 160 min after this week
    const bars = weeklyBars(s);
    expect(bars).toContain('⚠');                             // 10/12 week left work undone
    expect(bars).toContain('10/19*');                        // this week marked, never ⚠
    expect(bars).toContain('やり残し: 組分け 第2回 理科');
    const html = planCard(st, { charts: true, now: new Date('2026-10-20T00:00:00Z') });
    expect(html.match(/<figure class="viz">/g)).toHaveLength(2);
    expect(cumulativeChart([{ week: '2026-11-02', plan: 30, done: null, future: true }])).toBe('');
  });

  it('is a parent page', () => {
    expect(parentRedirect({ admin: true }, 'plan')).toBe(false);
  });
});
