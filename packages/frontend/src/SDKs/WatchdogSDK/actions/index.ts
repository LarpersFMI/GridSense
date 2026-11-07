import { ActionGroup, log } from '../../core'
import type { WatchdogSDKImpl } from '../sdk'
import { HitActions } from './hit'
import { LiveActions } from './live'

/** `WatchdogSDK.actions`: its groups, by what they act on. */
export class WatchdogActions extends ActionGroup<WatchdogSDKImpl> {

    protected readonly log = log.withContext('Watchdog.Actions')

    public readonly hit = new HitActions(this.sdk)

    public readonly live = new LiveActions(this.sdk)
}
