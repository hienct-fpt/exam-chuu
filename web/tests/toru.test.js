import { describe, expect, it, vi } from 'vitest';

vi.mock('../src/api.js', () => ({}));
vi.mock('../src/qimg.js', () => ({ qimg: () => '' }));
const { toruList } = await import('../src/views/toru.js');

const it_ = (id, subject, rate) => ({ id, subject, rate, big: 1, label: '(1)' });

describe('取るべき問題', () => {
  const items = [
    it_('kumiwake_2026_r1_math#1-1', 'math', 92.5),
    it_('kumiwake_2026_r1_math#1-2', 'math', 55),
    it_('kumiwake_2026_r1_math#4-3', 'math', 12.1),
    it_('kumiwake_2026_r1_social#1-1', 'social', 80),
    it_('kumiwake_2026_r1_social#1-2', 'social', 70),
    { id: 'kyoritsu_2026_2-1_math#1-1', subject: 'math' },   // school paper: no 正答率
  ];
  const hist = {
    'kumiwake_2026_r1_math#1-1': { correct: false, tries: 2 },
    'kumiwake_2026_r1_math#1-2': { correct: false, tries: 1 },
    'kumiwake_2026_r1_math#4-3': { correct: false, tries: 1 },
    'kumiwake_2026_r1_social#1-1': { correct: true, tries: 1 },
    'kyoritsu_2026_2-1_math#1-1': { correct: false, tries: 1 },
  };

  it('keeps wrong/blank items at or above the threshold, highest 正答率 first, per 教科', () => {
    const l = toruList(hist, items, 50);
    expect(Object.keys(l)).toEqual(['math']);
    expect(l.math.map((r) => r.item.id)).toEqual(['kumiwake_2026_r1_math#1-1', 'kumiwake_2026_r1_math#1-2']);
    expect(l.math[0].tries).toBe(2);
  });

  it('skips correct items, items never tried and items without a 正答率', () => {
    const l = toruList(hist, items, 10);
    expect(l.math.map((r) => r.item.id)).toContain('kumiwake_2026_r1_math#4-3');
    expect(l.social).toBeUndefined();                 // 1-1 correct, 1-2 never tried
    expect(JSON.stringify(l)).not.toContain('kyoritsu');
  });

  it('a higher threshold narrows the list', () => {
    expect(toruList(hist, items, 60).math.map((r) => r.rate)).toEqual([92.5]);
    expect(toruList({}, items, 50)).toEqual({});
  });
});
