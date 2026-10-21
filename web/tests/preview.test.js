import { describe, expect, it } from 'vitest';
import { answerText } from '../src/views/preview.js';

describe('問題の確認: answer text', () => {
  it('formats keys', () => {
    expect(answerText({ answer: '36', unit: 'cm' })).toBe('36 cm');
    expect(answerText({ answer: ['2', '3'], parts: ['ア', 'イ'] })).toBe('ア 2 / イ 3');
    expect(answerText({ answer: ['A', 'D'], answer_type: 'set' })).toBe('A・D');
    expect(answerText({ answer: '3/4', variants: ['0.75'] })).toBe('3/4（別解 0.75）');
    expect(answerText({ answer: null, answer_type: 'manual', note: '作図' })).toBe('保護者が採点（作図）');
    expect(answerText(undefined)).toBe('—');
  });
});
