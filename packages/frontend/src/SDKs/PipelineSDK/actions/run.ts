import { Pipeline } from '@gridsense/shared/domain'
import { api } from '../../api'
import { ActionGroup, log } from '../../core'
import { RealtimeSDK } from '../../RealtimeSDK/sdk'
import type { PipelineSDKImpl } from '../sdk'

// A running run's log, as kept in the browser: the latest lines.
const LIVE_LINES_KEPT = 2_000

/** `PipelineSDK.actions.run` */
export class RunActions extends ActionGroup<PipelineSDKImpl> {

    protected readonly log = log.withContext('Pipeline.Actions.Run')

    public async list(limit: number): Promise<Pipeline.API.ListRuns.Response> {
        const data = await Pipeline.API.listRuns(api, { limit })

        this.sdk.setState(state => {
            Object.assign(state.runs, data.runs)
        })

        return data
    }

    /** The run and, once it's finished, its whole log; while it runs, the server has none yet and the live lines stay. */
    public async get(id: Pipeline.Run.Id): Promise<Pipeline.API.GetRun.Response> {
        const data = await Pipeline.API.getRun(api, id)

        this.sdk.setState(state => {
            state.runs[id] = data.run

            if (data.run.status !== 'running')
                state.logs[id] = data.log === '' ? [] : data.log.replace(/\n$/, '').split('\n')
        })

        return data
    }

    /** Every run as it starts and ends, until the returned function is called. */
    public watch(): () => void {
        return RealtimeSDK.subscribeToChannel(Pipeline.Event.RUNS_CHANNEL, Pipeline.Event.Run.Updated.Schema, event => {
            this.sdk.setState(state => {
                state.runs[event.run.id] = event.run
            })
        })
    }

    /** One run's lines as it writes them, until the returned function is called. */
    public watchLog(id: Pipeline.Run.Id): () => void {
        return RealtimeSDK.subscribeToChannel(Pipeline.Event.getRunChannel(id), Pipeline.Event.Run.Logged.Schema, event => {
            this.sdk.setState(state => {
                const lines = state.logs[id] ?? []

                lines.push(...event.lines)
                lines.splice(0, Math.max(0, lines.length - LIVE_LINES_KEPT))
                state.logs[id] = lines
            })
        })
    }
}
