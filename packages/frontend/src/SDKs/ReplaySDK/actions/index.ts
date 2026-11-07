import { ActionGroup, log } from '../../core'
import type { ReplaySDKImpl } from '../sdk'
import { ReplayControlActions } from './replay'

/** `ReplaySDK.actions`: its groups, by what they act on. */
export class ReplayActions extends ActionGroup<ReplaySDKImpl> {

    protected readonly log = log.withContext('Replay.Actions')

    public readonly replay = new ReplayControlActions(this.sdk)
}
