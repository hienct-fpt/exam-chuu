import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    pool: 'threads',
    env: { VITE_MOCK: '1' },
    include: ['tests/**/*.test.js'],
  },
});
