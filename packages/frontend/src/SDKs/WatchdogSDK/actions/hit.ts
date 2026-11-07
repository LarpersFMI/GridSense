import { Trigger } from '@gridsense/shared/domain'
import { api } from '../../api'
import { ActionGroup, log } from '../../core'
import type { WatchdogSDKImpl } from '../sdk'

/** `WatchdogSDK.actions.hit` */
export class HitActions extends ActionGroup<WatchdogSDKImpl> {

    protected readonly log = log.withContext('Watchdog.Actions.Hit')

    /** The latest hits from the agent's queue. */
    public async list(limit: number): Promise<Trigger.API.ListHits.Response> {
        const data = await Trigger.API.listHits(api, { limit })

        this.sdk.setState(state => {
            for (const queued of Object.values(data.hits))
                state.hits[queued.threadId] = queued
        })

        return data
    }
}
