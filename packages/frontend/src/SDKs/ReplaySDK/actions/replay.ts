import { Pipeline, Replay } from '@gridsense/shared/domain'
import { api, describeError, errorMessage } from '../../api'
import { ActionGroup, log } from '../../core'
import { AgentSDK } from '../../AgentSDK/sdk'
import { ForecasterSDK } from '../../ForecasterSDK/sdk'
import { NotificationSDK } from '../../NotificationSDK/sdk'
import { PipelineSDK } from '../../PipelineSDK/sdk'
import { QuerySDK } from '../../QuerySDK/sdk'
import { RealtimeSDK } from '../../RealtimeSDK/sdk'
import { WatchdogSDK } from '../../WatchdogSDK/sdk'
import type { ReplaySDKImpl } from '../sdk'

/** `ReplaySDK.actions.replay`: reading it, moving its start, resetting it, one step. */
export class ReplayControlActions extends ActionGroup<ReplaySDKImpl> {

    protected readonly log = log.withContext('Replay.Actions.Replay')

    public async get(): Promise<Replay.State> {
        const data = await Replay.API.get(api)

        return data.replay
    }

    /** Moves the start: the replay starts over from it. */
    public async setStart(start: Replay.LocalDate): Promise<Replay.State> {
        try {
            const data = await Replay.API.setStart(api, { start })

            forgetBeforeReset()
            NotificationSDK.toast.success(`The replay starts over on ${start}`)

            return data.replay
        }
        catch (error) {
            this.log.error('setStart failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't move the replay's start", errorMessage(error))

            throw error
        }
    }

    /** Starts over from the same day. */
    public async reset(): Promise<Replay.State> {
        try {
            const data = await Replay.API.reset(api)

            forgetBeforeReset()
            NotificationSDK.toast.success('The replay starts over', `From ${data.replay.start}: no forecast, no prices, no hits yet.`)

            return data.replay
        }
        catch (error) {
            this.log.error('reset failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't reset the replay", errorMessage(error))

            throw error
        }
    }

    /** One day: the forecast issued, then the auction cleared. */
    public async step(): Promise<void> {
        try {
            await Replay.API.step(api)

            NotificationSDK.toast.success('Queued a day: forecast, then prices')
        }
        catch (error) {
            this.log.error('step failed', describeError(error))
            void NotificationSDK.toast.error("Couldn't queue the day", errorMessage(error))

            throw error
        }
    }

    /** Re-reads where the replay is whenever a pipeline run ends, until the returned function is called. */
    public watch(): () => void {
        return RealtimeSDK.subscribeToChannel(Pipeline.Event.RUNS_CHANNEL, Pipeline.Event.Run.Updated.Schema, event => {
            if (event.run.status !== 'running')
                void this.sdk.invalidate(this.sdk.query.replay)
        })
    }
}

/** After a reset, what the other SDKs kept from before it is gone on the server too: dropped, then read again. */
function forgetBeforeReset(): void {
    PipelineSDK.setState(state => {
        state.runs = {}
        state.logs = {}
    })
    WatchdogSDK.setState(state => {
        state.hits = {}
        state.checks = []
    })
    ForecasterSDK.setState(state => {
        state.runs = {}
    })
    AgentSDK.setState(state => {
        state.threads = {}
        state.slots = {}
        state.answering = {}
    })

    void QuerySDK.client.invalidateQueries()
}
