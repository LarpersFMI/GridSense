import type { Trigger } from '@gridsense/shared/domain'
import type { TriggerSDK } from './sdk'

export const triggerSelectors = {

    /** Every trigger, by name. */
    list: (state: TriggerSDK.State): Trigger[] => {
        const triggers = Object.values(state.triggers)

        triggers.sort((a, b) => a.name.localeCompare(b.name))

        return triggers
    },

    byId: (id: Trigger.Id) => (state: TriggerSDK.State): Trigger | null => state.triggers[id] ?? null,
}
