import { useEffect, useRef } from 'react'
import { Spinner } from '@blueprintjs/core'
import type { Pipeline } from '@gridsense/shared/domain'
import { ErrorNotice } from '@/components/ErrorNotice'
import { PipelineSDK } from '@/SDKs/PipelineSDK/sdk'
import { formatLocal } from '@/utils/format'
import { RunStatusTag } from './RunStatusTag'

/** One run: what it was, and its log — whole once it's finished, line by line while it runs, kept scrolled to the end. */
export function RunLog({ runId }: { runId: Pipeline.Run.Id }) {
    const end = useRef<HTMLDivElement>(null)

    const status = PipelineSDK.useStore(state => state.runs[runId]?.status)

    const [[run, lines], [request]] = PipelineSDK.useWith(
        state => [state.runs[runId] ?? null, state.logs[runId] ?? []] as const,
        query => [query.run(runId, status)],
    )

    useEffect(() => {
        return PipelineSDK.actions.run.watchLog(runId)
    }, [runId])

    useEffect(() => {
        end.current?.scrollIntoView({ block: 'nearest' })
    }, [lines.length])

    if (request.isError)
        return <ErrorNotice title="Couldn't load the run" error={request.error} />

    if (run === null)
        return <Spinner />

    return (
        <div className='flex flex-col gap-2'>
            <div className='flex items-center gap-3'>
                <span className='font-mono font-semibold'>{run.pipeline}</span>
                <RunStatusTag status={run.status} />
                <span className='text-xs text-gray-500'>
                    {run.cause === 'manual' ? 'run now' : 'on schedule'} · {formatLocal(run.startedAt)}
                    {run.finishedAt && ` · ${formatDuration(run.finishedAt.getTime() - run.startedAt.getTime())}`}
                </span>
            </div>

            {run.error && <div className='text-sm text-red-700'>{run.error}</div>}

            <div className='max-h-[480px] min-h-[160px] overflow-auto rounded bg-gray-900 p-3'>
                <pre className='m-0 font-mono text-xs leading-5 whitespace-pre-wrap text-gray-100'>
                    {lines.length === 0 && run.status === 'running' ? 'Waiting for output…' : lines.join('\n')}
                </pre>
                <div ref={end} />
            </div>
        </div>
    )
}

function formatDuration(milliseconds: number): string {
    if (milliseconds < 60_000)
        return `${(milliseconds / 1000).toFixed(1)} s`

    return `${Math.floor(milliseconds / 60_000)} min ${Math.round((milliseconds % 60_000) / 1000)} s`
}
