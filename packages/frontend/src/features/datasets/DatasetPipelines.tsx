import { useState } from 'react'
import { Button, Card, NonIdealState, Spinner, Switch, Tag } from '@blueprintjs/core'
import type { Dataset, Pipeline } from '@gridsense/shared/domain'
import { ErrorNotice } from '@/components/ErrorNotice'
import { PipelineSDK } from '@/SDKs/PipelineSDK/sdk'
import { formatClock, formatLocal } from '@/utils/format'
import { CronInput } from '../pipelines/CronInput'
import { NextRun } from '../pipelines/NextRun'
import { RunLog } from '../pipelines/RunLog'
import { RunStatusTag } from '../pipelines/RunStatusTag'

const RUNS_SHOWN = 5

interface DatasetPipelinesProps {
    dataset: Dataset.Name
}

/** The pipelines that write this dataset: when they run, running one now, and their latest runs with the log. */
export function DatasetPipelines({ dataset }: DatasetPipelinesProps) {
    const [selected, setSelected] = useState<Pipeline.Run.Id | null>(null)

    const [pipelines, [pipelinesRequest]] = PipelineSDK.useWith(
        PipelineSDK.selectors.list,
        query => [query.pipelines, query.runs],
    )

    const schedules = PipelineSDK.useStore(state => state.schedules)
    const nextRuns = PipelineSDK.useStore(state => state.nextRuns)
    const runs = PipelineSDK.useStore(PipelineSDK.selectors.runs)

    const writing = pipelines.filter(pipeline => pipeline.outputs.includes(dataset))

    if (pipelinesRequest.isError)
        return <ErrorNotice title="Couldn't load the pipelines" error={pipelinesRequest.error} />

    if (pipelinesRequest.isPending)
        return <Spinner />

    if (writing.length === 0) {
        return (
            <NonIdealState
                icon='data-lineage'
                title={`No pipeline writes ${dataset}`}
                description='Pipelines are defined in Python (src/gridsense/pipelines) and show up once the PipelineRunner starts.'
            />
        )
    }

    return (
        <div className='flex flex-col gap-3'>
            {writing.map(pipeline => (
                <PipelineCard
                    key={pipeline.name}
                    pipeline={pipeline}
                    schedule={schedules[pipeline.name] ?? null}
                    nextRun={nextRuns[pipeline.name] ?? null}
                    runs={runs.filter(run => run.pipeline === pipeline.name).slice(0, RUNS_SHOWN)}
                    selected={selected}
                    onSelect={id => setSelected(id === selected ? null : id)}
                />
            ))}

            {selected !== null && <RunLog runId={selected} />}
        </div>
    )
}

interface PipelineCardProps {
    pipeline: PipelineSDK.Listed
    schedule: Pipeline.Schedule | null
    nextRun:  Date | null
    runs:     Pipeline.Run[]
    selected: Pipeline.Run.Id | null
    onSelect: (id: Pipeline.Run.Id) => void
}

function PipelineCard({ pipeline, schedule, nextRun, runs, selected, onSelect }: PipelineCardProps) {
    const cron = schedule?.cron ?? pipeline.defaultCron
    const enabled = schedule?.enabled ?? false
    const isRunning = runs[0]?.status === 'running'

    function handleCronChange(next: string) {
        void PipelineSDK.actions.pipeline.setSchedule(pipeline.name, { cron: next, enabled })
    }

    function handleEnabledChange() {
        void PipelineSDK.actions.pipeline.setSchedule(pipeline.name, { cron, enabled: !enabled })
    }

    return (
        <Card compact className={`flex flex-col gap-3 ${pipeline.available ? '' : 'opacity-50'}`}>
            <div className='flex items-start justify-between gap-2'>
                <div>
                    <div className='flex items-center gap-2'>
                        <span className='font-mono font-semibold'>{pipeline.name}</span>
                        {isRunning && <Tag minimal intent='primary' icon={<Spinner size={12} />}>running</Tag>}
                        {!isRunning && enabled && nextRun && <NextRun at={nextRun} />}
                        {!pipeline.available && <Tag minimal intent='warning'>no longer in Python</Tag>}
                    </div>
                    <div className='text-xs text-gray-500'>{pipeline.description}</div>
                </div>
                <Switch checked={enabled} disabled={!pipeline.available} onChange={handleEnabledChange} className='mb-0' />
            </div>

            <div className='flex items-center justify-between gap-2'>
                <CronInput value={cron} defaultValue={pipeline.defaultCron} disabled={!pipeline.available} onChange={handleCronChange} />
                <Button
                    icon='play'
                    text='Run now'
                    variant='outlined'
                    size='small'
                    disabled={!pipeline.available || isRunning}
                    onClick={() => void PipelineSDK.actions.pipeline.runNow(pipeline.name)}
                />
            </div>

            {runs.length === 0 && <div className='text-xs text-gray-500'>Never run.</div>}

            {runs.length > 0 && (
                <div className='flex flex-col'>
                    {runs.map(run => (
                        <div
                            key={run.id}
                            role='button'
                            tabIndex={0}
                            onClick={() => onSelect(run.id)}
                            className={`flex cursor-pointer items-center gap-2 rounded px-1 py-1 hover:bg-gray-100 ${run.id === selected ? 'bg-blue-50' : ''}`}
                        >
                            <RunStatusTag status={run.status} />
                            <span className='font-mono text-xs'>{formatClock(run.startedAt)}</span>
                            <span className='text-xs text-gray-500'>{run.cause === 'manual' ? 'run now' : 'schedule'}</span>
                            <span className='ml-auto text-xs'>{formatRows(run)}</span>
                        </div>
                    ))}
                </div>
            )}

            {schedule && enabled && (
                <div className='text-xs text-gray-500'>Runs on <span className='font-mono'>{cron}</span>, Romanian time{runs[0] && ` · last ${formatLocal(runs[0].startedAt)}`}</div>
            )}
        </Card>
    )
}

function formatRows(run: Pipeline.Run): string {
    if (run.rowsAppended === null)
        return ''

    const appended = Object.entries(run.rowsAppended)

    if (appended.length === 0)
        return 'nothing new'

    return appended.map(([dataset, rows]) => `${dataset} +${rows}`).join(' · ')
}
