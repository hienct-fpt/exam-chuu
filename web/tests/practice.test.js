import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pickPractice } from '../src/views/practice.js';

const PUB = resolve(__dirname, '..', 'public');

describe('pickPractice (JS mirror of analytics.practice_set)', () => {
  const items = [
    { id: 'e#1-1', exam_id: 'e', topic: '速さ', grade: 5, answer_type: 'number', image: 'a', shared_image: false },
    { id: 'e#1-2', exam_id: 'e', topic: '速さ', grade: 6, answer_type: 'number', image: 'b', shared_image: false },
    { id: 'e#2-1', exam_id: 'e', topic: '速さ', grade: 5, answer_type: 'number', image: 'c', shared_image: true },
    { id: 'e#2-2', exam_id: 'e', topic: '速さ', grade: 5, answer_type: 'number', image: 'c', shared_image: true },
    { id: 'e#3-1', exam_id: 'e', topic: '速さ', grade: 5, answer_type: 'essay', image: 'd', shared_image: false },
    { id: 'e#4-1', exam_id: 'e', topic: '計算', grade: 5, answer_type: 'number', image: 'f', shared_image: false },
  ];
  const day = 86400000;
  const hist = { 'e#1-1': { correct: true, t: new Date(Date.now() - day).toISOString() },
    'e#2-1': { correct: false, t: new Date(Date.now() - 3 * day).toISOString() } };
  it('orders wrong > unseen > correct, pulls shared siblings, respects grade and type filters', () => {
    const ids = pickPractice(items, new Set(['速さ']), hist, { n: 3, gradeFilter: 5 }).map((p) => p.id);
    expect(ids[0]).toBe('e#2-1');
    expect(ids).toContain('e#2-2');
    expect(ids).not.toContain('e#1-2');
    expect(ids).not.toContain('e#3-1');
    expect(ids).not.toContain('e#4-1');
    expect(ids[ids.length - 1]).toBe('e#1-1');
  });
  it('no topic filter = all topics', () => {
    expect(pickPractice(items, null, {}, { n: 20 }).length).toBe(5); // essay excluded
  });
});

describe('dashboard + practice views render with mocked stats', () => {
  it('dashboard shows weak topics and practice links', async () => {
    const stats = {
      attemptCount: 2, weekly: [{ weekStart: '2026-09-14', attempts: 5, correct: 2, accuracy: 0.4 }],
      subjects: { math: { attempts: 5, correct: 2, accuracy: 0.4, weak: ['速さ・旅人算'] } },
      topics: { '速さ・旅人算': { subject: 'math', attempts: 3, correct: 0, pending: 0, mastery: 0, confident: true, weak: true, streak: 0, grade: 5 },
        '計算': { subject: 'math', attempts: 2, correct: 2, pending: 0, mastery: 1, confident: false, weak: false, streak: 2, grade: 5 } },
      itemHistory: {}, suggestions: {},
    };
    globalThis.fetch = vi.fn(async (url, opts) => {
      if (url === '/api/stats') return new Response(JSON.stringify(stats), { status: 200 });
      if (String(url).startsWith('/bank/')) return new Response(readFileSync(resolve(PUB, String(url).slice(1)), 'utf-8'), { status: 200 });
      return new Response('nf', { status: 404 });
    });
    const { renderDashboard } = await import('../src/views/dashboard.js');
    const app = document.createElement('main');
    await renderDashboard({ app });
    expect(app.textContent).toContain('速さ・旅人算');
    expect(app.querySelector('a[href^="#/practice/math?topic="]')).toBeTruthy();
    expect(app.querySelectorAll('tr.weak').length).toBeGreaterThan(0);

    const { renderPractice } = await import('../src/views/practice.js');
    const app2 = document.createElement('main');
    await renderPractice({ app: app2 }, 'math?weak=1&g=5');
    expect(app2.querySelectorAll('#topics .chip.on').length).toBe(1);
    expect(app2.querySelector('#preview').textContent).toContain('問');
    expect(app2.querySelector('#start').disabled).toBe(false);
  });
});
