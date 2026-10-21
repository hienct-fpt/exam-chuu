import { describe, expect, it, beforeEach } from 'vitest';
import { selectedChild, setSelectedChild, childPicker } from '../src/children.js';

const kids = [{ uid: 'a', name: '長女' }, { uid: 'b', name: '次女' }];

describe('several children', () => {
  beforeEach(() => localStorage.clear());
  it('remembers the chosen child, falls back to the first', () => {
    expect(selectedChild(kids).uid).toBe('a');
    setSelectedChild('b');
    expect(selectedChild(kids).uid).toBe('b');
    setSelectedChild('gone');
    expect(selectedChild(kids).uid).toBe('a');
    expect(selectedChild([])).toBeNull();
  });
  it('picker only with 2+ children', () => {
    expect(childPicker([kids[0]], kids[0])).toBe('');
    const html = childPicker(kids, kids[1], (k) => `#/parent/${k.uid}`);
    expect(html).toContain('href="#/parent/b"');
    expect(html).toMatch(/class="button on" href="#\/parent\/b"/);
  });
});
