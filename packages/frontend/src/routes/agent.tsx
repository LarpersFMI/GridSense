import { createFileRoute } from '@tanstack/react-router'
import { AgentPage } from '@/features/agent/AgentPage'

export const Route = createFileRoute('/agent')({
    component: () => (
        // Wider than a Page: the threads and the picked one side by side.
        <div className='mx-auto max-w-[1400px] p-6'>
            <AgentPage />
        </div>
    ),
})
