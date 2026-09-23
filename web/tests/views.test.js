// Smoke tests for the SPA views in mock mode (jsdom). Serves /bank/* from web/public, fakes /api/grade.
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const PUB = resolve(__dirname, '..', 'public');
const EXAM = 'kyoritsu_2026_2-1_math';

function fakeResult(exam, answers) {
  const perItem = {}; const perBig = {};
  for (const it of exam.items) {
    const sid = it.id.split('#')[1];
    const student = answers[sid] ?? '';
    const answered = Array.isArray(student) ? student.some(Boolean) : Boolean(student);
    const correct = answered && sid === '1-2'; // pretend only 1-2 is right
    perItem[sid] = { big: it.big, sub: it.sub, label: it.label, unit: it.unit, parts: it.parts, image: it.image,
      answered, correct, student, expected: 'X', variants: [], partsCorrect: [], points: 1, earned: correct ? 1 : 0 };
    const b = (perBig[it.big] ||= { big: it.big, items: 0, correct: 0, points: 0, earned: 0 });
    b.items++; b.points++; if (correct) { b.correct++; b.earned++; }
  }
  const score = Object.values(perItem).filter((x) => x.correct).length;
  return { score, max: exam.items.length, percent: Math.round(100 * score / exam.items.length),
    correctCount: score, answeredCount: Object.values(perItem).filter((x) => x.answered).length,
    itemCount: exam.items.length, perBig, perItem };
}

beforeAll(() => {
  if (!existsSync(resolve(PUB, 'bank', `${EXAM}.json`))) throw new Error('run scripts/sync_assets.py first');
  globalThis.fetch = vi.fn(async (url, opts) => {
    if (url.startsWith('/bank/')) {
      const p = resolve(PUB, url.slice(1));
      return new Response(readFileSync(p, 'utf-8'), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (url === '/api/grade') {
      const body = JSON.parse(opts.body);
      const exam = JSON.parse(readFileSync(resolve(PUB, 'bank', `${body.examId}.json`), 'utf-8'));
      const result = fakeResult(exam, body.answers);
      return new Response(JSON.stringify({ result, emailSubject: 'sub', emailHtml: '<p>mail</p>' }), { status: 200 });
    }
    return new Response('nf', { status: 404 });
  });
  globalThis.confirm = () => true;
  globalThis.alert = (m) => { throw new Error('alert: ' + m); };
});

describe('mock api + views', () => {
  it('home lists all exams', async () => {
    const { renderHome } = await import('../src/views/home.js');
    const app = document.createElement('main');
    await renderHome({ app });
    const index = JSON.parse(readFileSync(resolve(PUB, 'bank', 'index.json'), 'utf-8'));
    expect(app.querySelectorAll('.exam-tile').length).toBe(index.length);
    expect(app.textContent).toContain('2026年度');
    expect(app.textContent).toContain('品川女子学院');
    // school filter narrows the list
    app.querySelector('#schoolseg button[data-s="shinagawa"]').click();
    await new Promise((r) => setTimeout(r, 50));
    expect(app.querySelectorAll('.exam-tile').length).toBe(index.filter((e) => e.school === 'shinagawa').length);
    app.querySelector('#schoolseg button[data-s="all"]').click();
    await new Promise((r) => setTimeout(r, 50));
  });

  it('exam view renders every answer slot, autosaves, submits, and result view shows grading', async () => {
    const { renderExam } = await import('../src/views/exam.js');
    const { renderResult } = await import('../src/views/result.js');
    const api = await import('../src/api.js');
    const app = document.createElement('main');
    document.body.appendChild(app);
    const cleanup = await renderExam({ app }, EXAM);

    const exam = JSON.parse(readFileSync(resolve(PUB, 'bank', `${EXAM}.json`), 'utf-8'));
    const inputs = app.querySelectorAll('input[data-sid]');
    const expected = exam.items.reduce((n, it) => n + (it.parts ? it.parts.length : 1), 0);
    expect(inputs.length).toBe(expected); // 23 items, two multi (AD/BC, 2 parts) -> 25 inputs
    expect(app.querySelectorAll('img.qimg').length).toBeGreaterThan(20);
    expect(app.querySelectorAll('#big-5 input[data-sid]').length).toBe(8); // あ〜く share one image

    // type answers
    const set = (sid, v, part) => {
      const sel = part === undefined ? `input[data-sid="${sid}"]:not([data-part])` : `input[data-sid="${sid}"][data-part="${part}"]`;
      const el = app.querySelector(sel); el.value = v; el.dispatchEvent(new Event('input', { bubbles: true }));
    };
    set('1-1', '23/120'); set('1-2', '36'); set('6-1', '36', 0); set('6-1', '42', 1);
    expect(app.querySelector('#progress').textContent).toContain('回答 3 / 23');
    await new Promise((r) => setTimeout(r, 1000)); // debounce autosave
    const inProg = await api.findInProgress(EXAM);
    expect(inProg).toBeTruthy();
    expect(inProg.answers['1-1']).toBe('23/120');
    expect(inProg.answers['6-1']).toEqual(['36', '42']);

    app.querySelector('#submit').click();
    await new Promise((r) => setTimeout(r, 50));
    expect(location.hash).toMatch(/^#\/result\//);
    cleanup();
    const aid = location.hash.split('/').pop();
    const a = await api.getAttempt(aid);
    expect(a.status).toBe('graded');
    expect(a.result.score).toBe(1);

    const app2 = document.createElement('main');
    const unsub = await renderResult({ app: app2 }, aid);
    await new Promise((r) => setTimeout(r, 50));
    expect(app2.querySelector('.score').textContent).toContain('1 / 23');
    expect(app2.querySelectorAll('#items tr[data-ok]').length).toBe(23);
    expect(app2.querySelectorAll('#items tr[data-ok="true"]').length).toBe(1);
    unsub();
  });

  it('history lists the graded attempt', async () => {
    const { renderHistory } = await import('../src/views/history.js');
    const app = document.createElement('main');
    await renderHistory({ app });
    expect(app.textContent).toContain('採点済');
    expect(app.textContent).toContain('1 / 23');
  });
});
