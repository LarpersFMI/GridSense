import { defineConfig } from 'vitest/config';

/** Unit tests for the PipelineRunner, in a tests/ folder beside the code they test. No Python, no infrastructure. */
export default defineConfig({
    test: {
        include: ['src/**/tests/**/*.test.ts'],
    },
});
