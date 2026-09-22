import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseExamArg, selectItems, scaledTimeLimit } from '../src/views/exam.js';

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
});
