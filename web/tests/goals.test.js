import { describe, expect, it } from 'vitest';
import { assignmentList, daysUntil, goalCard, goalStatus } from '../src/views/goals.js';
import { redoItems } from '../src/views/redo.js';

const goals = {
  weekStart: '2026-10-19', examDate: '2028-02-01', deadline: '2027-12-07', weeksLeft: 60,
  first: 'kyoritsu', second: 'shinagawa', firstName: '共立女子', secondName: '品川女子学院中等部',
  subjects: {
    math: { target: 0.7, provisional: true, level: 0.5, goalAccuracy: 0.51, goalItems: 20, behind: true, atRisk: false,
      focus: [{ topic: '割合と比', mastery: 0.3, freq: 0.2, score: 0.14 }] },
    science: { target: 0.7, provisional: true, level: null, goalAccuracy: null, goalItems: 20, behind: false, atRisk: false, focus: [] },
  },
  actual: { math: { items: 20, correct: 12, accuracy: 0.6 }, science: { items: 3, correct: 0, accuracy: 0 } },
};

describe('goals card', () => {
  it('counts days to the exam in JST', () => {
    expect(daysUntil('2028-02-01', new Date('2028-01-31T15:00:00Z'))).toBe(0);   // 2/1 00:00 JST
    expect(daysUntil('2028-02-01', new Date('2028-01-30T23:00:00Z'))).toBe(1);
  });

  it('status: met / in progress / accuracy below goal', () => {
    expect(goalStatus(goals.subjects.math, goals.actual.math)).toBe('done');
    expect(goalStatus(goals.subjects.science, goals.actual.science)).toBe('progress');
    expect(goalStatus(goals.subjects.math, { items: 8, correct: 2, accuracy: 0.25 })).toBe('low');
  });

  it('renders rows, focus links and the provisional note', () => {
    const html = goalCard(goals, { gradeQ: '&g=5' });
    expect(html).toContain('今週の目標');
    expect(html).toContain('10/19〜10/25');
    expect(html).toContain('20 / 20問');
    expect(html).toContain('先週未達');
    expect(html).toContain('#/practice/math?topic=%E5%89%B2%E5%90%88%E3%81%A8%E6%AF%94&g=5');
    expect(html).toContain('合格点が未登録');
    expect(goalCard(goals, { practice: false })).not.toContain('#/practice/');
    expect(goalCard(undefined)).toBe('');
  });
});

describe('今週の課題', () => {
  const g = { ...goals,
    assignments: { grade: 5, budget: 180, remaining: 40, queue: 42, items: [
      { kind: 'new', examId: 'kumiwake_2026_r3_math', label: '組分け 第3回 算数', minutes: 50 },
      { kind: 'review', examId: 'kumiwake_2026_r1_math', label: '組分け 第1回 算数', minutes: 40, items: ['kumiwake_2026_r1_math#2-1'] },
    ] },
    assignmentsDone: [true, false] };

  it('lists new exams and やり直し with links, minutes done / planned', () => {
    const html = assignmentList(g);
    expect(html).toContain('50 / 90分');
    expect(html).toContain('目安 3時間');
    expect(html).toContain('href="#/redo/kumiwake_2026_r1_math"');
    expect(html).not.toContain('href="#/exam/kumiwake_2026_r3_math');      // done -> no link
    expect(html).toContain('間違い・未回答 1問');
    expect(goalCard(g)).toContain('今週の課題');
    expect(assignmentList(goals)).toBe('');
  });

  it('redo items: frozen assignment first, else latest wrong outcomes', () => {
    const stats = { goals: g, itemHistory: { 'x#1': { correct: false }, 'x#2': { correct: true }, 'y#1': { correct: false } } };
    expect(redoItems(stats, 'kumiwake_2026_r1_math')).toEqual(['kumiwake_2026_r1_math#2-1']);
    expect(redoItems(stats, 'x')).toEqual(['x#1']);
  });
});
