import { defineConfig } from 'vitest/config';

/** Unit tests for @gridsense/shared, in a tests/ folder beside the code they test. No infrastructure. */
export default defineConfig({
    test: {
        include: ['**/tests/**/*.test.ts'],
        exclude: ['node_modules/**', 'dist/**'],
    },
});
