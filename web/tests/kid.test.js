import { describe, expect, it } from 'vitest';
import { streakDays, weekSeconds, badges, heroCard, taskCards } from '../src/kid.js';

const now = new Date('2026-10-21T03:00:00Z');   // 10/21 12:00 JST
const sub = (iso, extra = {}) => ({ status: 'graded', submittedAt: iso, ...extra });

describe('kid dashboard', () => {
  it('streak counts JST days in a row ending today or yesterday', () => {
    expect(streakDays([sub('2026-10-20T12:00:00Z'), sub('2026-10-19T12:00:00Z'), sub('2026-10-17T12:00:00Z')], now)).toBe(2);
    expect(streakDays([sub('2026-10-20T16:00:00Z')], now)).toBe(1);   // 10/21 01:00 JST = today
    expect(streakDays([sub('2026-10-18T12:00:00Z')], now)).toBe(0);
  });
  it('weekly time and badges come from real attempts', () => {
    const list = [sub('2026-10-20T01:00:00Z', { activeSec: 1800, examId: 'e', mode: 'exam', percent: 100 }), sub('2026-10-10T01:00:00Z', { activeSec: 600 })];
    expect(weekSeconds(list, '2026-10-19')).toBe(1800);
    const goals = { assignments: { items: [{}, {}] }, assignmentsDone: [true, true] };
    const got = Object.fromEntries(badges(list, goals, now).map((b) => [b.name, b.got]));
    expect(got).toMatchObject({ はじめの一歩: true, 満点: true, 今週コンプリート: true, '3日つづけた': false });
  });
  it('hero and task cards', () => {
    const goals = { firstName: '共立', examDate: '2028-02-01', weekStart: '2026-10-19',
      assignments: { grade: 5, items: [{ kind: 'new', examId: 'k_math', label: '組分け 算数', minutes: 50 }, { kind: 'review', examId: 'c_social', label: '中大 社会', minutes: 20, items: ['a', 'b'] }] },
      assignmentsDone: [false, true] };
    expect(heroCard('たろう', goals, [], now)).toContain('あと <b>1</b> こ');
    const cards = taskCards(goals, (id) => id.split('_')[1]);
    expect(cards).toContain('href="#/exam/k_math?g=5"');
    expect(cards).toContain('できた！');
    expect(cards).toContain('s-social');
    expect(taskCards({}, () => 'math')).toBe('');
  });
});
