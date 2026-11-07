import type { Trigger, Watchdog } from '@gridsense/shared/domain'
import type { WatchdogSDK } from './sdk'

export const watchdogSelectors = {

    /** Newest first. */
    hits: (state: WatchdogSDK.State): Trigger.Hit.Queued[] => {
        const hits = Object.values(state.hits)

        hits.sort((a, b) => b.raisedAt.getTime() - a.raisedAt.getTime())

        return hits
    },

    /** How many hits each trigger has raised (of those listed). */
    hitCounts: (state: WatchdogSDK.State): Record<Trigger.Id, number> => {
        const counts: Record<Trigger.Id, number> = {}

        for (const queued of Object.values(state.hits))
            counts[queued.hit.triggerId] = (counts[queued.hit.triggerId] ?? 0) + 1

        return counts
    },

    checks: (state: WatchdogSDK.State): Watchdog.Event.Check.Completed[] => state.checks,
}
