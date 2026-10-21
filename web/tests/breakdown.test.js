import { describe, expect, it } from 'vitest';
import { weakTabs } from '../src/views/dashboard.js';
import { subjectBreakdown } from '../src/parent-ui.js';

const topics = {
  割合: { subject: 'math', mastery: 0.3, weak: true, confident: true, correct: 3, attempts: 10 },
  速さ: { subject: 'math', mastery: 0.5, weak: true, confident: true, correct: 5, attempts: 10 },
  図形: { subject: 'math', mastery: 0.9, weak: false, confident: true, correct: 9, attempts: 10 },
  地理: { subject: 'social', mastery: 0.8, weak: false, confident: false, correct: 2, attempts: 2 },
};

describe('分野 per 教科', () => {
  it('student tabs: one per 教科, most weak first, others show 「もう少し」', () => {
    const html = weakTabs(topics, '&g=5');
    expect(html).toMatch(/kid-tab s-math on" data-tab="math"/);
    expect(html).toContain('<span class="kid-tab-n">2</span>');
    expect(html).toContain('href="#/practice/math?topic=%E5%89%B2%E5%90%88&g=5"');
    expect(html).toContain('社会は にがてな分野がないよ');
    expect(html.indexOf('割合')).toBeLessThan(html.indexOf('速さ'));   // weakest first
    expect(weakTabs({})).toBe('');
  });
  it('parent breakdown lists every 分野 of a 教科, weak marked', () => {
    const html = subjectBreakdown({ topics, subjects: { math: { accuracy: 0.57, attempts: 30 }, social: { accuracy: 0.8, attempts: 2 } } }, []);
    expect(html).toContain('弱点 2');
    expect(html).toContain('図形');
    expect(html).toContain('地理 <small class="muted">少</small>');
    expect(html.indexOf('割合')).toBeLessThan(html.indexOf('図形'));
  });
});
