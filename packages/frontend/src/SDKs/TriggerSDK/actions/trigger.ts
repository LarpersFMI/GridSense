import { Trigger } from '@gridsense/shared/domain'
import { api, describeError, errorMessage } from '../../api'
import { ActionGroup, log } from '../../core'
import { NotificationSDK } from '../../NotificationSDK/sdk'
import type { TriggerSDKImpl } from '../sdk'

/** `TriggerSDK.actions.trigger` */
export class TriggerCrudActions extends ActionGroup<TriggerSDKImpl> {

    protected readonly log = log.withContext('Trigger.Actions.Trigger')

    public async list(): Promise<Trigger.API.List.Response> {
        const data = await Trigger.API.list(api)

        this.sdk.setState({ triggers: data.triggers })

        return data
    }

    public async get(id: Trigger.Id): Promise<Trigger.API.Get.Response> {
        const data = await Trigger.API.get(api, id)

        this.sdk.setState(state => {
            state.triggers[id] = data.trigger
        })

        return data
    }

    /** Saves a new trigger; it reads only rows appended from now on. */
    public async create(trigger: Trigger): Promise<Trigger> {
        try {
            const data = await Trigger.API.create(api, trigger)

            this.sdk.setState(state => {
                state.triggers[data.trigger.id] = data.trigger
            })

            NotificationSDK.toast.success(`Saved "${data.trigger.name}"`)

            return data.trigger
        }
        catch (error) {
            this.log.error('create failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't save the trigger", errorMessage(error))

            throw error
        }
    }

    public async update(trigger: Trigger): Promise<Trigger> {
        try {
            const data = await Trigger.API.update(api, trigger)

            this.sdk.setState(state => {
                state.triggers[data.trigger.id] = data.trigger
            })

            return data.trigger
        }
        catch (error) {
            this.log.error('update failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't save the trigger", errorMessage(error))

            throw error
        }
    }

    public async setEnabled(trigger: Trigger, enabled: boolean): Promise<Trigger> {
        return this.update({
            ...trigger,
            enabled,
        })
    }

    public async remove(id: Trigger.Id): Promise<Trigger> {
        try {
            const data = await Trigger.API.remove(api, id)

            this.sdk.setState(state => {
                delete state.triggers[id]
            })

            NotificationSDK.toast.success(`Deleted "${data.trigger.name}"`)

            return data.trigger
        }
        catch (error) {
            this.log.error('remove failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't delete the trigger", errorMessage(error))

            throw error
        }
    }
}
