import { describe, expect, it } from 'vitest';
import { mistakeStats, mistakeCard, mistakePicker } from '../src/mistakes.js';
import { gapLine } from '../src/views/goals.js';

const att = (examId, perItem, mistakes) => ({ status: 'graded', examId, result: { perItem }, mistakes });

describe('まちがいの原因', () => {
  const list = [
    att('kyoritsu_2026_2-1_math', { '1-1': { correct: false }, '1-2': { correct: false }, '1-3': { correct: true }, '2-1': { correct: false, pending: true } },
      { '1-1': 'careless', '1-2': 'careless' }),
    att(null, { 'kumiwake_2026_r6_social#1-1': { correct: false, subject: 'social' }, 'kumiwake_2026_r6_social#1-2': { correct: false, subject: 'social' } },
      { 'kumiwake_2026_r6_social#1-1': 'knowledge', 'kumiwake_2026_r6_social#1-2': 'bogus' }),
  ];
  it('counts tagged wrong answers per cause and 教科, skipping correct / pending / unknown tags', () => {
    const s = mistakeStats(list);
    expect(s.total).toBe(4);
    expect(s.tagged).toBe(3);
    expect(s.untagged).toBe(1);
    expect(s.byCause).toEqual({ careless: 2, knowledge: 1 });
    expect(s.bySubject).toEqual({ math: { careless: 2 }, social: { knowledge: 1 } });
  });
  it('card names the biggest cause; picker keeps the current value', () => {
    expect(mistakeCard(list)).toContain('ケアレスミスが一番多いです');
    expect(mistakeCard([])).toBe('');
    expect(mistakePicker('1-1', 'time')).toContain('value="time" selected');
  });
});

describe('今週の課題: gap-weighted やり直し', () => {
  it('lists the share per 教科, biggest first', () => {
    const html = gapLine({ reviewShares: { math: 0.7, social: 0.3 }, gaps: { math: 0.2 } });
    expect(html.indexOf('算数 70%')).toBeLessThan(html.indexOf('社会 30%'));
    expect(html).toContain('目標まで 20pt');
    expect(html).toContain('目標データなし');
    expect(gapLine({})).toBe('');
  });
});
