import { describe, expect, it } from 'vitest';
import { normCdf, schoolSim, schoolNeeds, kumiwakeSim, toruPoints, simulatorCard, Z80 } from '../src/simulator.js';

// a session as exported by hensachi_report: 4 subjects, line 176, sigmaC 22.75 (= 0.5 × 45.5)
const x = { schoolName: '共立', label: '2/1', y80: 52, y50: 46,
  model: { max: { math: 100, japanese: 100, science: 50, social: 50 }, line: 176, sigmaC: 22.75 },
  levels: { math: 0.6, japanese: 0.7, science: 0.55, social: 0.65 } };   // score 60+70+27.5+32.5 = 190

describe('偏差値シミュレーター (school)', () => {
  it('normCdf matches known values', () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 6);
    expect(normCdf(Z80)).toBeCloseTo(0.8, 5);
    expect(normCdf(-1.96)).toBeCloseTo(0.025, 4);
  });

  it('recomputes the estimate like hensachi.estimate() and moves with added points', () => {
    const now = schoolSim(x);
    expect(now.score).toBeCloseTo(190, 6);
    const z = (190 - 176) / 22.75;
    expect(now.y).toBeCloseTo(46 + (6 / Z80) * z, 6);
    expect(now.prob).toBeCloseTo(normCdf(z), 6);
    const plus = schoolSim(x, { science: 10 });
    expect(plus.score).toBeCloseTo(200, 6);
    expect(plus.y - now.y).toBeCloseTo(10 * schoolNeeds(x).perPoint, 6);
    expect(schoolSim(x, { science: 999 }).score).toBeCloseTo(190 - 27.5 + 50, 6);   // capped at full marks
  });

  it('points to the 80% line', () => {
    const n = schoolNeeds(x);
    expect(n.to80).toBeCloseTo(176 + Z80 * 22.75 - 190, 6);
    expect(schoolSim(x, { math: Math.ceil(n.to80) }).prob).toBeGreaterThanOrEqual(0.8);
    expect(schoolSim({ ...x, levels: { math: 0.5 } })).toBeNull();                // a subject without a level
  });
});

describe('偏差値シミュレーター (組分け)', () => {
  const r = { round: 6, total: 52, sdTotal: 80,
    subjects: { math: { y: 50, pct: 50, max: 200, sd: 36, examId: 'kumiwake_2026_r6_math' },
      social: { y: 48, pct: 40, max: 100, sd: 18, examId: 'kumiwake_2026_r6_social' } } };

  it('adds points per subject and to the 4科 total', () => {
    const s = kumiwakeSim(r, { math: 18, social: 9 });
    expect(s.subjects.math).toBeCloseTo(55, 6);
    expect(s.subjects.social).toBeCloseTo(53, 6);
    expect(s.total).toBeCloseTo(52 + 270 / 80, 6);
    expect(kumiwakeSim(r, { social: 500 }).subjects.social).toBeCloseTo(48 + 10 * 60 / 18, 6);   // only the missed points
  });

  it('sums the 配点 of the 取るべき問題 that belong to that round', () => {
    const list = { math: [{ item: { exam_id: 'kumiwake_2026_r6_math', points: 8 } }, { item: { exam_id: 'kumiwake_2026_r5_math', points: 8 } }],
      social: [{ item: { exam_id: 'kumiwake_2026_r6_social', points: 2 } }] };
    expect(toruPoints(r, list)).toEqual({ math: 8, social: 2 });
  });

  it('card renders the per-point table and nothing without data', () => {
    expect(simulatorCard({ sessions: [x], kumiwake: { rounds: [r] } })).toContain('第6回');
    expect(simulatorCard({ sessions: [], kumiwake: { rounds: [] } })).toBe('');
  });
});
