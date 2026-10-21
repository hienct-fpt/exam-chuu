import { describe, expect, it } from 'vitest';
import { activeTimer, IDLE_MS } from '../src/views/exam.js';
import { attemptSeconds, duration, groupAttempts } from '../src/views/parent.js';

describe('working time', () => {
  it('counts visible, active time; idle gaps count only up to IDLE_MS; carries the saved seconds', () => {
    let t = 0;
    const tm = activeTimer(60, () => t);
    tm.show();
    t = 5 * 60e3; tm.touch();                       // 5 min working
    t += IDLE_MS + 20 * 60e3; tm.touch();           // 30 min without input -> only 10 count
    t += 60e3; tm.hide();                           // 1 more min, then tab hidden
    t += 60 * 60e3;                                 // hidden hour: nothing
    tm.show(); t += 2 * 60e3;
    expect(tm.seconds()).toBe(60 + (5 + 10 + 1 + 2) * 60);
  });

  it('falls back to start→submit only when plausible', () => {
    expect(attemptSeconds({ activeSec: 1500 })).toEqual({ sec: 1500, approx: false });
    expect(attemptSeconds({ startedAt: '2026-10-20T10:00:00Z', submittedAt: '2026-10-20T10:40:00Z' })).toEqual({ sec: 2400, approx: true });
    expect(attemptSeconds({ startedAt: '2026-10-20T10:00:00Z', submittedAt: '2026-10-21T10:00:00Z' })).toBeNull();   // left open overnight
    expect(duration(2400)).toBe('40分');
    expect(duration(3900)).toBe('1時間5分');
  });

  it('groups attempts per exam (redo joins its exam), 1回目 first, newest group first', () => {
    const name = (a) => (a.examId ? `試験 ${a.examId}` : a.title);
    const g = groupAttempts([
      { id: '3', examId: null, redoOf: 'k24', mode: 'practice', items: ['x'], startedAt: '2026-10-15', status: 'graded', percent: 80, activeSec: 600 },
      { id: '1', examId: 'k24', mode: 'exam', startedAt: '2026-10-01', status: 'graded', percent: 55, activeSec: 2400 },
      { id: '2', examId: 'c26', mode: 'exam', startedAt: '2026-10-10', status: 'graded', percent: 70, pendingCount: 2 },
    ], name);
    expect(g.map((x) => x.key)).toEqual(['k24', 'c26']);
    expect(g[0].label).toBe('試験 k24');
    expect(g[0].list.map((a) => a.id)).toEqual(['1', '3']);
    expect(g[0].totalSec).toBe(3000);
    expect(g[1].pending).toBe(true);
  });
});
