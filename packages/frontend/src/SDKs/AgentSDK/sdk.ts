import type { Agent, Foundations } from '@gridsense/shared/domain'
import { createWithEqualityFn } from 'zustand/traditional'
import { immer } from 'zustand/middleware/immer'
import { shallow } from 'zustand/shallow'
import { BaseSDK } from '../core/BaseSDK'
import { SDK } from '../SDKManager'
import { AgentActions } from './actions'
import { agentSelectors } from './selectors'

/**
 * The agent's work: its threads (one per hit: decision, impact analysis, steps, actions) by id, and the slots it
 * announced by key. Listed once, then kept live from `agent:threads` and `agent:slots`.
 */
@SDK('Agent')
export class AgentSDKImpl extends BaseSDK<AgentSDK.State> {

    public readonly useStore: BaseSDK.Store<AgentSDK.State> = createWithEqualityFn(
        immer<AgentSDK.State>(() => ({
            threads:   {},
            slots:     {},
            answering: {},
        })),
        shallow,
    )

    public readonly actions: AgentSDK.Actions = new AgentActions(this)

    public readonly selectors = agentSelectors

    public override readonly query = {
        threads: {
            queryKey: ['agent', 'threads'] as const,
            queryFn:  () => this.actions.thread.list(),
        },

        slots: {
            queryKey: ['agent', 'slots'] as const,
            queryFn:  () => this.actions.slot.list(),
        },
    }

    public override cleanup(): void {
        this.setState({ threads: {}, slots: {}, answering: {} })
    }
}

export const AgentSDK = SDK.get<AgentSDKImpl>('Agent')

export namespace AgentSDK {

    export type State = {
        threads:   Record<Foundations.Thread.Id, Agent.Thread>
        slots:     Record<string, Agent.Slot>
        answering: Record<Foundations.Thread.Id, Agent.Message.ToolCall[]>     // live, while the agent answers a question
    }

    export type Actions = AgentActions
}
