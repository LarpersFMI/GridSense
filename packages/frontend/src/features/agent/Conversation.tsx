import { useState } from 'react'
import { Button, InputGroup, Spinner } from '@blueprintjs/core'
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

    // The last word is the operator's: the agent is looking it up.
    const thinking = thread.messages.length > 0 && thread.messages[thread.messages.length - 1].role === 'operator'

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
                <div className='flex items-center gap-2 self-start rounded-md bg-violet-50 px-3 py-2 text-sm text-violet-900 shadow-sm ring-1 ring-violet-200'>
                    <Spinner size={14} />
                    The agent is looking it up…
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
        <div className={`max-w-[92%] self-start rounded-md px-3 py-2 text-sm shadow-sm ${byAi ? 'bg-violet-50 ring-1 ring-violet-200' : 'bg-white ring-1 ring-gray-200'}`}>
            <div className='mb-1 flex flex-wrap items-center gap-2'>
                {byAi && <AiBadge text='Claude' />}
                {message.tools.length > 0 && <span className='text-xs text-gray-500'>consulted: {message.tools.join(', ')}</span>}
            </div>
            <div className='whitespace-pre-wrap'>{withBold(message.text)}</div>
        </div>
    )
}

/** `**words**` as bold: the one bit of markdown an answer may still carry; the rest stays plain text. */
function withBold(text: string) {
    return text.split(/\*\*(.+?)\*\*/g).map((part, index) => (index % 2 === 1 ? <b key={index}>{part}</b> : part))
}
