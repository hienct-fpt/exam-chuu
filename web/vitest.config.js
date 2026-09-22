import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    // worker startup is flaky on this Windows box with threads/forks; vmThreads + serial is stable
    pool: 'vmThreads',
    fileParallelism: false,
    env: { VITE_MOCK: '1' },
    include: ['tests/**/*.test.js'],
  },
});
