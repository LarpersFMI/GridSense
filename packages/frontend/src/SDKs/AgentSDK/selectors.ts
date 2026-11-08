import type { Agent, Foundations } from '@gridsense/shared/domain'
import type { AgentSDK } from './sdk'

export const agentSelectors = {

    /** Every thread, newest first. */
    threads: (state: AgentSDK.State): Agent.Thread[] =>
        Object.values(state.threads).sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime()),

    /** The threads waiting for the operator, the soonest hours first. */
    inbox: (state: AgentSDK.State): Agent.Thread[] =>
        Object.values(state.threads)
            .filter(thread => thread.status === 'awaiting-review')
            .sort((a, b) => (a.hit.window?.start.getTime() ?? 0) - (b.hit.window?.start.getTime() ?? 0)),

    byId: (id: Foundations.Thread.Id | null) => (state: AgentSDK.State): Agent.Thread | null =>
        (id === null ? null : state.threads[id] ?? null),

    /** Every slot, by its hours. */
    slots: (state: AgentSDK.State): Agent.Slot[] =>
        Object.values(state.slots).sort((a, b) => a.start.getTime() - b.start.getTime()),
}
