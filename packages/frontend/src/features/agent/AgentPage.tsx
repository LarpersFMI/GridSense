import { useState } from 'react'
import { Spinner } from '@blueprintjs/core'
import type { Foundations } from '@gridsense/shared/domain'
import { Choice } from '@/components/Choice'
import { ErrorNotice } from '@/components/ErrorNotice'
import { AgentSDK } from '@/SDKs/AgentSDK/sdk'
import { CalendarView } from './CalendarView'
import { ThreadCard } from './ThreadCard'
import { ThreadList } from './ThreadList'

type View = 'threads' | 'slots'

/**
 * The agent's side of the app: its threads on the left — the ones waiting for the operator first — and the one
 * picked on the right, with its impact analysis and, when it waits, Approve / Reject; and the free-hours calendar.
 */
export function AgentPage() {
    const [view, setView] = useState<View>('threads')
    const [picked, setPicked] = useState<Foundations.Thread.Id | null>(null)

    const [waiting, [threadsRequest]] = AgentSDK.useWith(
        AgentSDK.selectors.inbox,
        query => [query.threads, query.slots],
    )

    const newest = AgentSDK.useStore(state => AgentSDK.selectors.threads(state)[0] ?? null)

    // Nothing picked: the first thread waiting for the operator, else the newest.
    const selected = picked ?? waiting[0]?.id ?? newest?.id ?? null
    const thread = AgentSDK.useStore(AgentSDK.selectors.byId(selected))

    if (threadsRequest.isError)
        return <ErrorNotice title="Couldn't load the agent's threads" error={threadsRequest.error} />

    if (threadsRequest.isPending)
        return <Spinner />

    return (
        <div className='flex flex-col gap-4'>
            <div className='flex items-center gap-4'>
                <h3 className='bp6-heading m-0'>Agent</h3>
                <Choice
                    id='agent-view'
                    value={view}
                    onChange={setView}
                    options={[
                        { value: 'threads', label: waiting.length > 0 ? `Threads · ${waiting.length} waiting` : 'Threads', icon: 'chat' },
                        { value: 'slots', label: 'Free hours', icon: 'calendar' },
                    ]}
                />
            </div>

            {view === 'threads' && (
                <div className='grid grid-cols-5 items-start gap-4'>
                    {/* Stays in view while the thread on the right scrolls. */}
                    <div className='sticky top-2 col-span-2 max-h-[calc(100vh-9rem)] overflow-auto'>
                        <ThreadList selected={selected} onSelect={setPicked} />
                    </div>
                    <div className='col-span-3'>
                        <ThreadCard thread={thread} />
                    </div>
                </div>
            )}

            {view === 'slots' && (
                <CalendarView
                    onOpen={id => {
                        setPicked(id)
                        setView('threads')
                    }}
                />
            )}
        </div>
    )
}
