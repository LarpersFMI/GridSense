import { Agent } from '@gridsense/shared/domain'
import { api } from '../../api'
import { ActionGroup, log } from '../../core'
import { RealtimeSDK } from '../../RealtimeSDK/sdk'
import type { AgentSDKImpl } from '../sdk'

/** `AgentSDK.actions.slot`: the free-hours slots the agent announced, confirmed or cancelled. */
export class AgentSlotActions extends ActionGroup<AgentSDKImpl> {

    protected readonly log = log.withContext('Agent.Actions.Slot')

    public async list(): Promise<Agent.Slot[]> {
        const data = await Agent.API.listSlots(api)

        this.sdk.setState(state => {
            state.slots = data.slots
        })

        return Object.values(data.slots)
    }

    /** Keeps the slots live, until the returned function is called. */
    public watch(): () => void {
        return RealtimeSDK.subscribeToChannel(Agent.Event.SLOTS_CHANNEL, Agent.Event.Slot.Updated.Schema, event => {
            this.sdk.setState(state => {
                state.slots[event.slot.key] = event.slot
            })
        })
    }
}
