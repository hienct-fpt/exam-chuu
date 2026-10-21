import { describe, expect, it } from 'vitest';
import { headlineSession, hensachiCard, kpiCards } from '../src/parent-ui.js';

const sess = (over) => ({ school: 'kyoritsu', schoolName: '共立女子', session: '2-1', label: '2/1入試', y80: 50, y50: 46, first: true,
  lineBasis: '合格率 45% から推定', coverage: { math: 'school', japanese: 'school', science: 'other', social: 'school' },
  estimate: { y: 47.6, prob: 0.62, score: 180, line: 176 }, trendPerMonth: 1.3, reach80: '2027-01',
  series: [{ week: '2026-09-01', y: 44, prob: 0.3 }, { week: '2026-09-15', y: 46.2, prob: 0.51 }, { week: '2026-10-13', y: 47.6, prob: 0.62 }], ...over });

describe('推定偏差値 (保護者)', () => {
  it('headline = 第一志望 回 with the best 合格可能性', () => {
    const h = { sessions: [sess({ session: '2-2', label: '2/2入試', estimate: { y: 48, prob: 0.7 } }), sess(),
      sess({ school: 'shinagawa', first: false, estimate: { y: 55, prob: 0.95 } })] };
    expect(headlineSession(h).session).toBe('2-2');
    expect(headlineSession({ sessions: [sess({ estimate: null })] })).toBeNull();
  });

  it('table, trend, reach month and the chart against the 80/50 lines', () => {
    const html = hensachiCard({ sessions: [sess(), sess({ session: '2-2', label: '2/2入試', estimate: null, coverage: { math: 'school', social: null } })],
      assumptions: { spread: 0.18, rho: 0.6 }, source: '四谷大塚' });
    expect(html).toContain('<b>47.6</b>');
    expect(html).toContain('<b>62%</b>');
    expect(html).toContain('50〜80%');
    expect(html).toContain('▲ 1.3/月');
    expect(html).toContain('2027年1月ごろ');
    expect(html).toContain('自校の過去問 3/4教科');
    expect(html).toContain('未受験: 社会');
    expect(html).toContain('class="ref80"');
    expect(html).toContain('出典: 四谷大塚');
    expect(hensachiCard({ sessions: [] })).toBe('');
  });

  it('KPI dark card shows the headline estimate or how to get one', () => {
    const goals = { firstName: '共立', subjects: { math: { level: 0.5, target: 0.7, atRisk: true } } };
    expect(kpiCards({ goals, hensachi: { sessions: [sess()] } }, [])).toContain('合格可能性 <b class="kpi-prob">62%</b>');
    expect(kpiCards({ goals }, [])).toContain('過去問を全教科とくと推定できます');
  });
});
