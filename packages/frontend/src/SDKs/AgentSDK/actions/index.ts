import { ActionGroup, log } from '../../core'
import type { AgentSDKImpl } from '../sdk'
import { AgentSlotActions } from './slot'
import { AgentThreadActions } from './thread'

/** `AgentSDK.actions`: its groups, by what they act on. */
export class AgentActions extends ActionGroup<AgentSDKImpl> {

    protected readonly log = log.withContext('Agent.Actions')

    public readonly thread = new AgentThreadActions(this.sdk)

    public readonly slot = new AgentSlotActions(this.sdk)
}
