import type { Foundations, Trigger, Watchdog } from '@gridsense/shared/domain'
import { createWithEqualityFn } from 'zustand/traditional'
import { immer } from 'zustand/middleware/immer'
import { shallow } from 'zustand/shallow'
import { BaseSDK } from '../core/BaseSDK'
import { SDK } from '../SDKManager'
import { WatchdogActions } from './actions'
import { watchdogSelectors } from './selectors'

const HITS_LISTED = 500

/**
 * What the Watchdog does: the hits it raised (from the agent's queue, then live from each trigger's channel) and
 * the checks it ran (live only, from `watchdog:activity`).
 */
@SDK('Watchdog')
export class WatchdogSDKImpl extends BaseSDK<WatchdogSDK.State> {

    public readonly useStore: BaseSDK.Store<WatchdogSDK.State> = createWithEqualityFn(
        immer<WatchdogSDK.State>(() => ({
            hits:   {},
            checks: [],
        })),
        shallow,
    )

    public readonly actions: WatchdogSDK.Actions = new WatchdogActions(this)

    public readonly selectors = watchdogSelectors

    public override readonly query = {
        hits: {
            queryKey: ['hits'] as const,
            queryFn:  () => this.actions.hit.list(HITS_LISTED),
        },
    }

    public override cleanup(): void {
        this.setState({
            hits:   {},
            checks: [],
        })
    }
}

export const WatchdogSDK = SDK.get<WatchdogSDKImpl>('Watchdog')

export namespace WatchdogSDK {

    export type State = {
        hits:   Record<Foundations.Thread.Id, Trigger.Hit.Queued>
        checks: Watchdog.Event.Check.Completed[]            // newest first, since the page opened
    }

    export type Actions = WatchdogActions
}
