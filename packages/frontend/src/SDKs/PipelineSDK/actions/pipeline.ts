import { Pipeline } from '@gridsense/shared/domain'
import { api, describeError, errorMessage } from '../../api'
import { ActionGroup, log } from '../../core'
import { NotificationSDK } from '../../NotificationSDK/sdk'
import type { PipelineSDKImpl } from '../sdk'

/** `PipelineSDK.actions.pipeline`: the pipelines, their schedules, and running one now. */
export class PipelineScheduleActions extends ActionGroup<PipelineSDKImpl> {

    protected readonly log = log.withContext('Pipeline.Actions.Pipeline')

    public async list(): Promise<Pipeline.API.List.Response> {
        const data = await Pipeline.API.list(api)

        this.sdk.setState(state => {
            state.pipelines = data.pipelines
            state.schedules = data.schedules

            for (const run of Object.values(data.lastRuns))
                state.runs[run.id] = run
        })

        return data
    }

    /** Changes when it runs, or switches it on or off; the PipelineRunner follows. */
    public async setSchedule(name: Pipeline.Name, request: Pipeline.API.SetSchedule.Request): Promise<Pipeline.Schedule> {
        try {
            const data = await Pipeline.API.setSchedule(api, name, request)

            this.sdk.setState(state => {
                state.schedules[name] = data.schedule
            })

            return data.schedule
        }
        catch (error) {
            this.log.error('setSchedule failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't save the schedule", errorMessage(error))

            throw error
        }
    }

    /** Queues a run; it shows up in the runs once the PipelineRunner starts it. */
    public async runNow(name: Pipeline.Name): Promise<void> {
        try {
            await Pipeline.API.runNow(api, name)

            NotificationSDK.toast.success(`Queued "${name}"`)
        }
        catch (error) {
            this.log.error('runNow failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't queue the run", errorMessage(error))

            throw error
        }
    }
}
