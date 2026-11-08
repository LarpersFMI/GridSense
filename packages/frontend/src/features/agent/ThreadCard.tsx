import { useState } from 'react'
import { Button, Collapse, NonIdealState, Spinner, Tag, TextArea } from '@blueprintjs/core'
import type { Agent } from '@gridsense/shared/domain'
import { AgentSDK } from '@/SDKs/AgentSDK/sdk'
import { TriggerSDK } from '@/SDKs/TriggerSDK/sdk'
import { formatClock, formatWindow } from '@/utils/format'
import { AnalysisView } from './AnalysisView'
import { Conversation } from './Conversation'
import { AiBadge, DecisionTag, StatusTag } from './tags'

/**
 * One thread: the decision and its impact analysis, the operator's answer — asked for here when it waits for one —
 * what the agent did, and its steps on demand.
 */
export function ThreadCard({ thread }: { thread: Agent.Thread | null }) {
    const trigger = TriggerSDK.useStore(state => (thread === null ? null : state.triggers[thread.triggerId] ?? null))
    const [showSteps, setShowSteps] = useState(false)

    if (thread === null)
        return <NonIdealState icon='chat' title='Pick a thread' description='What the agent decided, why, and what it did.' />

    const waiting = thread.status === 'awaiting-review'
    const hours = windowOf(thread)

    return (
        <div className='flex flex-col gap-3'>
            {/* The first message: the agent's decision and its analysis, as a card. */}
            <section className={`flex flex-col gap-4 rounded-sm border bg-white p-4 shadow-sm ${waiting ? 'border-amber-300' : 'border-gray-200'}`}>
                <div className='flex flex-wrap items-center gap-2'>
                    {thread.decision && <DecisionTag label={thread.decision.label} />}
                    <span className='text-base font-semibold'>{hours ? formatWindow(hours) : 'No window'}</span>
                    <span className='text-sm text-gray-500'>· {trigger?.name ?? 'trigger'}</span>
                    <div className='ml-auto'>
                        <StatusTag status={thread.status} />
                    </div>
                </div>

                {thread.analysis && <AnalysisView analysis={thread.analysis} />}
                {!thread.analysis && isAnalyzing(thread) && <Analyzing />}
                {!thread.analysis && !isAnalyzing(thread) && (
                    <p className='m-0 text-sm'>{thread.decision?.reason ?? thread.steps[thread.steps.length - 1]?.summary}</p>
                )}

                {thread.actions.length > 0 && (
                    <div className='flex flex-col gap-2'>
                        <div className='text-xs font-semibold uppercase tracking-wide text-gray-500'>What it did</div>
                        {thread.actions.map(action => (
                            <div key={`${action.title}-${action.at.toISOString()}`} className='rounded border border-gray-200 p-3'>
                                <div className='mb-1 flex flex-wrap items-center gap-2 text-sm font-semibold'>
                                    {action.title}
                                    <Tag minimal round>{action.audience}</Tag>
                                    {action.wordedBy === 'llm' ? <AiBadge text='Worded by Claude' /> : <Tag minimal round icon='document'>Template</Tag>}
                                </div>
                                <p className='m-0 text-sm text-gray-700'>{action.text}</p>
                            </div>
                        ))}
                    </div>
                )}

                <div>
                    <Button
                        variant='minimal'
                        size='small'
                        icon={showSteps ? 'chevron-down' : 'chevron-right'}
                        text={`Steps (${thread.steps.length})`}
                        onClick={() => setShowSteps(!showSteps)}
                    />
                    <Collapse isOpen={showSteps}>
                        <ol className='m-0 mt-2 flex flex-col gap-1.5 pl-5 text-sm'>
                            {thread.steps.map(step => (
                                <li key={`${step.node}-${step.at.toISOString()}`}>
                                    <span className='font-mono text-xs text-gray-500'>{formatClock(step.at)}</span>{' '}
                                    <span className='font-semibold'>{step.node}</span> — {step.summary}
                                </li>
                            ))}
                        </ol>
                    </Collapse>
                </div>
            </section>

            {/* Under the first message, and stuck to the top once the conversation scrolls it away. */}
            {waiting && (
                <div className='sticky top-2 z-10 rounded-sm border border-amber-300 bg-white p-3 shadow-md'>
                    <Answer thread={thread} />
                </div>
            )}

            {thread.review && (
                <div className='rounded-sm border border-gray-200 bg-white px-3 py-2 text-sm'>
                    <span className='font-semibold'>{thread.review.decision === 'approve' ? 'Approved' : 'Rejected'}</span> by the operator at {formatClock(thread.review.at)}
                    {thread.review.note ? ` — “${thread.review.note}”` : ''}
                </div>
            )}

            {/* The rest of the conversation: on the page, outside the card. */}
            <Conversation thread={thread} />
        </div>
    )
}

/** The hours a thread is about: the ones its decision kept (a surer stretch of the hit's), or the hit's. */
export function windowOf(thread: Agent.Thread) {
    return thread.decision?.window ?? thread.hit.window
}

/** Decided, but its impact analysis not written yet: the agent's `analyze` node is at work (Claude, a few seconds). */
export function isAnalyzing(thread: Agent.Thread): boolean {
    return thread.status === 'running' && thread.decision !== null && thread.analysis === null
        && thread.decision.label !== 'none' && thread.decision.label !== 'alert'
}

function Analyzing() {
    return (
        <div className='flex items-center gap-3 rounded-md bg-violet-50 p-4 ring-1 ring-violet-200'>
            <Spinner size={18} />
            <div className='flex flex-col'>
                <span className='text-sm font-semibold text-violet-900'>Writing the impact analysis…</span>
                <span className='text-xs text-gray-500'>The agent’s tools have read the forecasts, the inputs and the prices; Claude is writing it up.</span>
            </div>
        </div>
    )
}

/** The operator's answer to a thread waiting for one: approve or reject, with an optional note for the record. */
function Answer({ thread }: { thread: Agent.Thread }) {
    const [note, setNote] = useState('')
    const [sending, setSending] = useState<'approve' | 'reject' | null>(null)

    async function answer(decision: 'approve' | 'reject') {
        setSending(decision)

        try {
            await AgentSDK.actions.thread.review(thread.id, decision, note.trim() === '' ? null : note.trim())
        }
        finally {
            setSending(null)
        }
    }

    return (
        <div className='flex items-end gap-3'>
            <div className='flex-1'>
                <TextArea fill rows={1} placeholder='A note for the record (optional)' value={note} onChange={event => setNote(event.currentTarget.value)} />
            </div>
            <Button intent='danger' variant='outlined' icon='cross' text='Reject' loading={sending === 'reject'} disabled={sending !== null} onClick={() => void answer('reject')} />
            <Button intent='success' icon='tick' text='Approve' loading={sending === 'approve'} disabled={sending !== null} onClick={() => void answer('approve')} />
        </div>
    )
}
