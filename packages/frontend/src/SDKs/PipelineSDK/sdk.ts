import type { Pipeline } from '@gridsense/shared/domain'
import { createWithEqualityFn } from 'zustand/traditional'
import { immer } from 'zustand/middleware/immer'
import { shallow } from 'zustand/shallow'
import { BaseSDK } from '../core/BaseSDK'
import { SDK } from '../SDKManager'
import { PipelineActions } from './actions'
import { pipelineSelectors } from './selectors'

const RUNS_LISTED = 100

/**
 * The pipelines Python defines, the schedules set for them here, and their runs: listed once, then kept live from
 * `pipeline:runs`. A run's log comes whole once it's finished, line by line while it runs.
 */
@SDK('Pipeline')
export class PipelineSDKImpl extends BaseSDK<PipelineSDK.State> {

    public readonly useStore: BaseSDK.Store<PipelineSDK.State> = createWithEqualityFn(
        immer<PipelineSDK.State>(() => ({
            pipelines: {},
            schedules: {},
            runs:      {},
            logs:      {},
            nextRuns:  {},
        })),
        shallow,
    )

    public readonly actions: PipelineSDK.Actions = new PipelineActions(this)

    public readonly selectors = pipelineSelectors

    public override readonly query = {
        pipelines: {
            queryKey: ['pipelines'] as const,
            queryFn:  () => this.actions.pipeline.list(),
        },

        runs: {
            queryKey: ['pipelines', 'runs'] as const,
            queryFn:  () => this.actions.run.list(RUNS_LISTED),
        },

        // Again once the run ends: the server has its whole log from then on.
        run: (id: Pipeline.Run.Id, status: Pipeline.Run.Status | undefined) => ({
            queryKey: ['pipelines', 'runs', id, status] as const,
            queryFn:  () => this.actions.run.get(id),
        }),
    }

    public override cleanup(): void {
        this.setState({
            pipelines: {},
            schedules: {},
            runs:      {},
            logs:      {},
            nextRuns:  {},
        })
    }
}

export const PipelineSDK = SDK.get<PipelineSDKImpl>('Pipeline')

export namespace PipelineSDK {

    export type Listed = Pipeline & { available: boolean }

    export type State = {
        pipelines: Record<Pipeline.Name, Listed>
        schedules: Record<Pipeline.Name, Pipeline.Schedule>
        runs:      Record<Pipeline.Run.Id, Pipeline.Run>
        logs:      Record<Pipeline.Run.Id, string[]>
        nextRuns:  Record<Pipeline.Name, Date>             // enabled schedules only
    }

    export type Actions = PipelineActions
}
