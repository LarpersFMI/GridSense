// Must stay first: tsyringe (the SDK container) reads decorator metadata as SDK classes load.
import 'reflect-metadata'
import '@blueprintjs/core/lib/css/blueprint.css'
import '@blueprintjs/table/lib/css/table.css'
import './index.css'
import { StrictMode } from 'react'
import { FocusStyleManager, HotkeysProvider } from '@blueprintjs/core'
import { createRoot } from 'react-dom/client'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { QuerySDK } from '@/SDKs/QuerySDK/sdk'
import { RealtimeSDK } from '@/SDKs/RealtimeSDK/sdk'
import { routeTree } from './routeTree.gen'

export const router = createRouter({
    routeTree,
    defaultPreload: 'intent',
})

declare module '@tanstack/react-router' {
    interface Register {
        router: typeof router
    }
}

// Blueprint's focus ring only when navigating with the keyboard (Tab), not after a click.
FocusStyleManager.onlyShowFocusOnTabs()

RealtimeSDK.connect()

const rootElement = document.getElementById('root')

if (!rootElement)
    throw new Error('Missing application root')

createRoot(rootElement).render(
    <StrictMode>
        <HotkeysProvider>
            <QuerySDK.Provider>
                <RouterProvider router={router} />
            </QuerySDK.Provider>
        </HotkeysProvider>
    </StrictMode>,
)
