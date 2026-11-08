import { Agent, type Foundations } from '@gridsense/shared/domain'
import { api, describeError, errorMessage } from '../../api'
import { ActionGroup, log } from '../../core'
import { NotificationSDK } from '../../NotificationSDK/sdk'
import { RealtimeSDK } from '../../RealtimeSDK/sdk'
import type { AgentSDKImpl } from '../sdk'

const THREADS_LISTED = 300

/** `AgentSDK.actions.thread`: the threads, and the operator's answer to one. */
export class AgentThreadActions extends ActionGroup<AgentSDKImpl> {

    protected readonly log = log.withContext('Agent.Actions.Thread')

    public async list(): Promise<Agent.Thread[]> {
        const data = await Agent.API.listThreads(api, { limit: THREADS_LISTED })

        this.sdk.setState(state => {
            state.threads = data.threads
        })

        return Object.values(data.threads)
    }

    public async get(id: Foundations.Thread.Id): Promise<Agent.Thread> {
        const data = await Agent.API.getThread(api, id)

        this.sdk.setState(state => {
            state.threads[id] = data.thread
        })

        return data.thread
    }

    /** The operator approves or rejects a thread awaiting review; the agent resumes it and the result comes live. */
    public async review(id: Foundations.Thread.Id, decision: 'approve' | 'reject', note: string | null): Promise<void> {
        try {
            await Agent.API.review(api, id, { decision, note })

            NotificationSDK.toast.success(decision === 'approve' ? 'Approved: the agent acts on it' : 'Rejected: nothing is announced')
        }
        catch (error) {
            this.log.error('review failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't send the answer", errorMessage(error))

            throw error
        }
    }

    /** The operator asks the agent about a thread; the question shows at once, the answer comes live. */
    public async ask(id: Foundations.Thread.Id, question: string): Promise<void> {
        try {
            await Agent.API.ask(api, id, { question })
        }
        catch (error) {
            this.log.error('ask failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't send the question", errorMessage(error))

            throw error
        }
    }

    /**
     * Keeps the threads live, until the returned function is called — and, while the agent answers a question, the
     * tool calls it has made so far (gone once the answer is on the thread).
     */
    public watch(): () => void {
        return RealtimeSDK.subscribeToChannel(Agent.Event.THREADS_CHANNEL, Agent.Event.Schema, event => {
            this.sdk.setState(state => {
                if (event.type === 'agent:thread:updated') {
                    state.threads[event.thread.id] = event.thread

                    if (event.thread.messages.at(-1)?.role === 'agent')
                        delete state.answering[event.thread.id]
                }

                if (event.type === 'agent:thread:answering')
                    state.answering[event.threadId] = event.calls
            })
        })
    }
}
