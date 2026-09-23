import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseExamArg, selectItems, scaledTimeLimit } from '../src/views/exam.js';
import { GRADES, countUpTo, gradeBreakdown, gradeFilterFromPref, yearOptions } from '../src/views/home.js';

const exam = JSON.parse(readFileSync(resolve(__dirname, '..', 'public', 'bank', 'kyoritsu_2024_2-1_math.json'), 'utf-8'));

describe('grade filter', () => {
  it('parses exam arg', () => {
    expect(parseExamArg('kyoritsu_2024_2-1_math')).toEqual({ examId: 'kyoritsu_2024_2-1_math', gradeFilter: null });
    expect(parseExamArg('kyoritsu_2024_2-1_math?g=5')).toEqual({ examId: 'kyoritsu_2024_2-1_math', gradeFilter: 5 });
    expect(parseExamArg('x?g=all').gradeFilter).toBeNull();
  });
  it('selects only grade<=5 items and scales time', () => {
    const g5 = selectItems(exam, 5);
    expect(g5.length).toBe(exam.grade_counts['5']);
    expect(g5.every((it) => it.grade === 5)).toBe(true);
    expect(selectItems(exam, null).length).toBe(exam.item_count);
    const t = scaledTimeLimit(exam, g5);
    expect(t).toBeGreaterThanOrEqual(5);
    expect(t).toBeLessThan(exam.time_limit_min);
    expect(t % 5).toBe(0);
    expect(scaledTimeLimit(exam, exam.items)).toBe(exam.time_limit_min);
  });
  it('grade 4 scope is a subset of grade 5 scope', () => {
    const g4 = selectItems(exam, 4);
    const g5ids = new Set(selectItems(exam, 5).map((it) => it.id));
    expect(g4.every((it) => it.grade <= 4 && g5ids.has(it.id))).toBe(true);
    expect(g4.length).toBe(countUpTo(exam, 4));
  });
  it('index counts sum grade buckets <= N', () => {
    const e = { item_count: 10, grade_counts: { 4: 2, 5: 5, 6: 3 } };
    expect(countUpTo(e, 4)).toBe(2);
    expect(countUpTo(e, 5)).toBe(7);
    expect(countUpTo(e, null)).toBe(10);
    expect(countUpTo({ item_count: 3, grade_counts: { '?': 3 } }, 5)).toBe(0);
    expect(gradeBreakdown(e)).toBe('小4 2 / 小5 5 / 小6 3');
    expect(gradeBreakdown({ grade_counts: { 5: 1 } })).toBe('小5 1');
  });
  it('year options are distinct, newest first, labelled', () => {
    const idx = [{ year: 2024 }, { year: 2026 }, { year: 2024 }, { year: 2003, year_label: '2003年以前' }, { year: null }];
    expect(yearOptions(idx)).toEqual([['2026', '2026年度'], ['2024', '2024年度'], ['2003', '2003年以前']]);
  });
  it('grade pref maps to filter', () => {
    expect(GRADES.map(([g]) => g)).toEqual(['4', '5', 'all']);
    expect(gradeFilterFromPref('4')).toBe(4);
    expect(gradeFilterFromPref('5')).toBe(5);
    expect(gradeFilterFromPref('all')).toBeNull();
  });
});
