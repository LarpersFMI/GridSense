import { ActionGroup, log } from '../../core'
import type { TriggerSDKImpl } from '../sdk'
import { TriggerCrudActions } from './trigger'

/** `TriggerSDK.actions`: its groups, by what they act on. */
export class TriggerActions extends ActionGroup<TriggerSDKImpl> {

    protected readonly log = log.withContext('Trigger.Actions')

    public readonly trigger = new TriggerCrudActions(this.sdk)
}
