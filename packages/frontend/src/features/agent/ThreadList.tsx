import { useState } from 'react'
import { Icon, Spinner, Switch } from '@blueprintjs/core'
import type { Agent, Foundations } from '@gridsense/shared/domain'
import { AgentSDK } from '@/SDKs/AgentSDK/sdk'
import { TriggerSDK } from '@/SDKs/TriggerSDK/sdk'
import { formatClock, formatWindow } from '@/utils/format'
import { isAnalyzing } from './ThreadCard'
import { DecisionTag } from './tags'

interface ThreadListProps {
    selected: Foundations.Thread.Id | null
    onSelect: (id: Foundations.Thread.Id) => void
}

/** The agent's threads: the ones waiting for the operator first, then the rest, newest first; closed ones on demand. */
export function ThreadList({ selected, onSelect }: ThreadListProps) {
    const waiting = AgentSDK.useStore(AgentSDK.selectors.inbox)
    const threads = AgentSDK.useStore(AgentSDK.selectors.threads)
    const [showClosed, setShowClosed] = useState(false)

    const done = threads.filter(thread => thread.status !== 'awaiting-review' && (showClosed || thread.status !== 'dismissed'))
    const closed = threads.filter(thread => thread.status === 'dismissed').length

    return (
        <div className='flex flex-col gap-3'>
            {waiting.length > 0 && (
                <Group title={`Waiting for you (${waiting.length})`}>
                    {waiting.map(thread => <Row key={thread.id} thread={thread} selected={thread.id === selected} onSelect={onSelect} />)}
                </Group>
            )}

            <Group title='Decided'>
                {done.length === 0 && <div className='px-3 py-2 text-sm text-gray-500'>Nothing yet: advance the replay.</div>}
                {done.map(thread => <Row key={thread.id} thread={thread} selected={thread.id === selected} onSelect={onSelect} />)}
            </Group>

            {closed > 0 && (
                <Switch
                    className='mb-0 text-xs text-gray-500'
                    label={`Show closed (${closed}) — nothing to do, or answered by a newer forecast`}
                    checked={showClosed}
                    onChange={event => setShowClosed(event.currentTarget.checked)}
                />
            )}
        </div>
    )
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div className='overflow-hidden rounded-sm border border-gray-200 bg-white'>
            <div className='border-b border-gray-100 bg-gray-50 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500'>{title}</div>
            <div className='flex flex-col'>{children}</div>
        </div>
    )
}

function Row({ thread, selected, onSelect }: { thread: Agent.Thread; selected: boolean; onSelect: (id: Foundations.Thread.Id) => void }) {
    const trigger = TriggerSDK.useStore(state => state.triggers[thread.triggerId] ?? null)
    const waiting = thread.status === 'awaiting-review'
    const closed = thread.status === 'dismissed'

    return (
        <div
            role='button'
            tabIndex={0}
            onClick={() => onSelect(thread.id)}
            onKeyDown={event => event.key === 'Enter' && onSelect(thread.id)}
            className={`flex cursor-pointer items-start gap-2.5 border-b border-gray-100 px-3 py-2 last:border-b-0 hover:bg-gray-50 ${selected ? 'bg-blue-50' : ''} ${closed ? 'opacity-60' : ''}`}
        >
            {isAnalyzing(thread)
                ? <div className='mt-0.5'><Spinner size={16} /></div>
                : <Icon icon='chat' className={`mt-0.5 ${waiting ? 'text-amber-600' : 'text-gray-400'}`} />}
            <div className='min-w-0 flex-1'>
                <div className='truncate text-sm font-semibold'>{thread.hit.window ? formatWindow(thread.hit.window) : 'No window'}</div>
                <div className='flex items-center gap-1.5 text-xs text-gray-500'>
                    <span className='truncate'>{trigger?.name}</span>
                    {thread.decision && <DecisionTag label={thread.decision.label} />}
                </div>
            </div>
            <span className='font-mono text-xs text-gray-400'>{formatClock(thread.updatedAt)}</span>
        </div>
    )
}
