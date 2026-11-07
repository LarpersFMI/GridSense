import { Watchdog, type Trigger } from '@gridsense/shared/domain'
import { ActionGroup, log } from '../../core'
import { RealtimeSDK } from '../../RealtimeSDK/sdk'
import type { WatchdogSDKImpl } from '../sdk'

const CHECKS_KEPT = 100

/** `WatchdogSDK.actions.live`: the Watchdog's events into the store, while a screen shows them. */
export class LiveActions extends ActionGroup<WatchdogSDKImpl> {

    protected readonly log = log.withContext('Watchdog.Actions.Live')

    /** Every check, and these triggers' hits, until the returned function is called. */
    public watch(triggerIds: Trigger.Id[]): () => void {
        const stops = [
            RealtimeSDK.subscribeToChannel(Watchdog.Event.ACTIVITY_CHANNEL, Watchdog.Event.Check.Completed.Schema, check => {
                this.sdk.setState(state => {
                    state.checks.unshift(check)
                    state.checks.splice(CHECKS_KEPT)
                })
            }),
        ]

        for (const triggerId of triggerIds)
            stops.push(RealtimeSDK.subscribeToChannel(Watchdog.Event.getTriggerChannel(triggerId), Watchdog.Event.Hit.Raised.Schema, event => {
                this.sdk.setState(state => {
                    state.hits[event.threadId] = {
                        threadId: event.threadId,
                        hit:      event.hit,
                        raisedAt: new Date(),
                        status:   'waiting',
                    }
                })
            }))

        return () => {
            for (const stop of stops)
                stop()
        }
    }
}
