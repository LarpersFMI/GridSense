import { Forecaster } from '@gridsense/shared/domain'
import { api } from '../../api'
import { ActionGroup, log } from '../../core'
import { RealtimeSDK } from '../../RealtimeSDK/sdk'
import type { ForecasterSDKImpl } from '../sdk'

/** `ForecasterSDK.actions.run` */
export class RunActions extends ActionGroup<ForecasterSDKImpl> {

    protected readonly log = log.withContext('Forecaster.Actions.Run')

    public async list(limit: number): Promise<Forecaster.API.ListRuns.Response> {
        const data = await Forecaster.API.listRuns(api, { limit })

        this.sdk.setState(state => {
            for (const run of data.runs)
                state.runs[run.id] = run
        })

        return data
    }

    /** Adds each run as it's reported, until the returned function is called. */
    public watch(): () => void {
        return RealtimeSDK.subscribeToChannel(Forecaster.Event.RUNS_CHANNEL, Forecaster.Event.Run.Reported.Schema, event => {
            this.sdk.setState(state => {
                state.runs[event.run.id] = event.run
            })
        })
    }
}
