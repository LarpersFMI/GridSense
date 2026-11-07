import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'

// .env lives at the repository root, with the server's address.
const REPOSITORY_ROOT = fileURLToPath(new URL('../../', import.meta.url))

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, REPOSITORY_ROOT, '')
    const server = env.GRIDSENSE_SERVER_URL || 'http://localhost:4000'

    const proxy = {
        '/api': {
            target:       server,
            changeOrigin: true,
        },

        // The realtime socket (RealtimeSDK ↔ the server's RealtimeGateway).
        '/socket': {
            target: server,
            ws:     true,
        },
    }

    return {
        plugins: [
            tanstackRouter({
                target:            'react',
                autoCodeSplitting: true,
            }),
            // Babel must parse the SDKs' @SDK decorators like TypeScript's experimentalDecorators.
            react({
                babel: {
                    plugins: [
                        ['@babel/plugin-proposal-decorators', { legacy: true }],
                        ['@babel/plugin-proposal-class-properties', { loose: true }],
                    ],
                },
            }),
            tailwindcss(),
        ],
        envDir: REPOSITORY_ROOT,

        resolve: {
            dedupe: ['react', 'react-dom'],
            alias: {
                '@':                 fileURLToPath(new URL('./src', import.meta.url)),
                '@gridsense/shared': fileURLToPath(new URL('../shared', import.meta.url)),
            },
        },

        server: {
            port:       5173,
            strictPort: true,
            proxy,
        },

        preview: {
            proxy,
        },
    }
})
