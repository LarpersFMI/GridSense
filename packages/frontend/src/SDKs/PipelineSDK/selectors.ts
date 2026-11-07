import type { Pipeline } from '@gridsense/shared/domain'
import type { PipelineSDK } from './sdk'

export const pipelineSelectors = {

    /** The ones Python defines first, then by name. */
    list: (state: PipelineSDK.State): PipelineSDK.Listed[] => {
        const pipelines = Object.values(state.pipelines)

        pipelines.sort((a, b) => Number(b.available) - Number(a.available) || a.name.localeCompare(b.name))

        return pipelines
    },

    /** Newest first. */
    runs: (state: PipelineSDK.State): Pipeline.Run[] => {
        const runs = Object.values(state.runs)

        runs.sort((a, b) => b.startedAt.getTime() - a.startedAt.getTime())

        return runs
    },

    /** Each pipeline's latest run. */
    lastRuns: (state: PipelineSDK.State): Record<Pipeline.Name, Pipeline.Run> => {
        const last: Record<Pipeline.Name, Pipeline.Run> = {}

        for (const run of Object.values(state.runs))
            if (!last[run.pipeline] || last[run.pipeline].startedAt < run.startedAt)
                last[run.pipeline] = run

        return last
    },
}
