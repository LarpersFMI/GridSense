import { useState } from 'react'
import { Button, Collapse, Icon, InputGroup, Spinner } from '@blueprintjs/core'
import type { Agent } from '@gridsense/shared/domain'
import { AgentSDK } from '@/SDKs/AgentSDK/sdk'
import { formatClock } from '@/utils/format'
import { AiBadge } from './tags'

// Questions an operator usually has before approving: one click each.
const SUGGESTIONS = [
    'How has the forecast for these hours moved?',
    'How did middays clear over the past week?',
    'Which hour is the weakest, and why?',
]

/**
 * Asking the agent about a decision: the operator's questions, and its answers — Claude, looking things up with the
 * agent's read-only tools, each answer saying which it consulted. It explains; the decision stays the rule's and yours.
 */
export function Conversation({ thread }: { thread: Agent.Thread }) {
    const [question, setQuestion] = useState('')
    const [sending, setSending] = useState(false)

    // The last word is the operator's: the agent is looking it up, and these are the calls it made so far.
    const thinking = thread.messages.length > 0 && thread.messages[thread.messages.length - 1].role === 'operator'
    const calls = AgentSDK.useStore(state => state.answering[thread.id] ?? NO_CALLS)

    async function send(text: string) {
        if (text.trim() === '')
            return

        setSending(true)

        try {
            await AgentSDK.actions.thread.ask(thread.id, text.trim())
            setQuestion('')
        }
        finally {
            setSending(false)
        }
    }

    return (
        <div className='flex flex-col gap-2'>

            {thread.messages.map(message => <Bubble key={`${message.role}-${message.at.toISOString()}`} message={message} />)}

            {thinking && (
                <div className='flex max-w-[92%] flex-col gap-1 self-start'>
                    {calls.length > 0 && <ToolsUsed calls={calls} />}
                    <div className='flex items-center gap-2 rounded-md bg-violet-50 px-3 py-2 text-sm text-violet-900 shadow-sm ring-1 ring-violet-200'>
                        <Spinner size={14} />
                        {calls.length === 0 ? 'The agent is deciding what to look up…' : 'Looking further, then answering…'}
                    </div>
                </div>
            )}

            {thread.messages.length === 0 && (
                <div className='flex flex-wrap gap-1.5'>
                    {SUGGESTIONS.map(suggestion => (
                        <Button key={suggestion} size='small' variant='outlined' text={suggestion} disabled={sending} onClick={() => void send(suggestion)} />
                    ))}
                </div>
            )}

            <form onSubmit={event => { event.preventDefault(); void send(question) }}>
                <div className='flex gap-2'>
                    <div className='flex-1'>
                        <InputGroup
                            fill
                            leftIcon='chat'
                            placeholder='Ask about this decision: the forecast, the inputs, past prices…'
                            value={question}
                            disabled={sending || thinking}
                            onValueChange={setQuestion}
                        />
                    </div>
                    <Button type='submit' icon='send-message' text='Ask' disabled={sending || thinking || question.trim() === ''} />
                </div>
            </form>
        </div>
    )
}

function Bubble({ message }: { message: Agent.Message }) {
    if (message.role === 'operator')
        return (
            <div className='max-w-[85%] self-end rounded-md bg-white px-3 py-2 text-sm shadow-sm ring-1 ring-gray-200'>
                {message.text}
                <div className='mt-1 text-right font-mono text-[10px] text-gray-400'>{formatClock(message.at)}</div>
            </div>
        )

    const byAi = message.writtenBy === 'llm'

    return (
        <div className='flex max-w-[92%] flex-col gap-1 self-start'>
            {message.calls.length > 0 && <ToolsUsed calls={message.calls} />}
            <div className={`rounded-md px-3 py-2 text-sm shadow-sm ${byAi ? 'bg-violet-50 ring-1 ring-violet-200' : 'bg-white ring-1 ring-gray-200'}`}>
                {byAi && <div className='mb-1'><AiBadge text='Claude' /></div>}
                <div className='whitespace-pre-wrap'>{withBold(message.text)}</div>
            </div>
        </div>
    )
}

const NO_CALLS: Agent.Message.ToolCall[] = []

/**
 * The tool calls behind an answer, outside its bubble: "2 tools used", and the calls themselves — the tool, what it
 * asked for, what came back — on a click. Not purple: these are lookups in the data, not text Claude wrote.
 */
function ToolsUsed({ calls }: { calls: Agent.Message.ToolCall[] }) {
    const [open, setOpen] = useState(false)

    return (
        <div className='self-start'>
            <Button
                variant='minimal'
                size='small'
                icon='wrench'
                endIcon={open ? 'chevron-down' : 'chevron-right'}
                text={calls.length === 1 ? '1 tool used' : `${calls.length} tools used`}
                onClick={() => setOpen(!open)}
            />
            <Collapse isOpen={open}>
                <div className='mt-1'>
                    <ToolCalls calls={calls} />
                </div>
            </Collapse>
        </div>
    )
}

function ToolCalls({ calls }: { calls: Agent.Message.ToolCall[] }) {
    return (
        <div className='flex flex-col gap-1'>
            {calls.map(call => (
                <div key={`${call.name}-${call.at.toISOString()}`} className='flex items-center gap-1.5 rounded bg-white px-2 py-1 font-mono text-[11px] text-gray-700 ring-1 ring-gray-200'>
                    <Icon icon='wrench' size={11} className='text-gray-500' />
                    <span className='font-semibold'>{call.name}</span>
                    <span className='text-gray-500'>({formatInput(call.input)})</span>
                    <span className='text-gray-400'>→</span>
                    <span className='truncate'>{call.summary}</span>
                </div>
            ))}
        </div>
    )
}

/** `{ from: "2025-04-27", to: "2025-05-03" }` → `from: 2025-04-27, to: 2025-05-03` */
const formatInput = (input: Record<string, unknown>) => Object.entries(input).map(([key, value]) => `${key}: ${String(value)}`).join(', ')

/** `**words**` as bold: the one bit of markdown an answer may still carry; the rest stays plain text. */
function withBold(text: string) {
    return text.split(/\*\*(.+?)\*\*/g).map((part, index) => (index % 2 === 1 ? <b key={index}>{part}</b> : part))
}
