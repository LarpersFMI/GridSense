import { useEffect, useState } from 'react'
import { Button, HTMLTable, NonIdealState, Spinner, Switch, Tag } from '@blueprintjs/core'
import type { Pipeline } from '@gridsense/shared/domain'
import { ErrorNotice } from '@/components/ErrorNotice'
import { PipelineSDK } from '@/SDKs/PipelineSDK/sdk'
import { formatClock, formatLocal } from '@/utils/format'
import { CronInput } from './CronInput'
import { NextRun } from './NextRun'
import { RunLog } from './RunLog'
import { RunStatusTag } from './RunStatusTag'

/**
 * The pipelines Python defines: when each runs (set here), switching it on, running it now, and every run with its
 * log, live.
 */
export function PipelinesPage() {
    const [selected, setSelected] = useState<Pipeline.Run.Id | null>(null)

    // After "Run now", the next run of that pipeline is opened as soon as it starts.
    const [following, setFollowing] = useState<{ pipeline: Pipeline.Name; since: Date } | null>(null)

    const [pipelines, [pipelinesRequest]] = PipelineSDK.useWith(
        PipelineSDK.selectors.list,
        query => [query.pipelines],
    )

    const [runs, [runsRequest]] = PipelineSDK.useWith(
        PipelineSDK.selectors.runs,
        query => [query.runs],
    )

    const schedules = PipelineSDK.useStore(state => state.schedules)
    const lastRuns = PipelineSDK.useStore(PipelineSDK.selectors.lastRuns)
    const nextRuns = PipelineSDK.useStore(state => state.nextRuns)

    useEffect(() => {
        if (!following)
            return

        const started = runs.find(run => run.pipeline === following.pipeline && run.startedAt >= following.since)

        if (started) {
            setSelected(started.id)
            setFollowing(null)
        }
    }, [runs, following])

    async function handleRunNow(name: Pipeline.Name) {
        // The server's clock may be a little behind this one: a run started a few seconds before counts.
        setFollowing({ pipeline: name, since: new Date(Date.now() - 5_000) })
        await PipelineSDK.actions.pipeline.runNow(name)
    }

    if (pipelinesRequest.isError)
        return <ErrorNotice title="Couldn't load the pipelines" error={pipelinesRequest.error} />

    if (pipelinesRequest.isPending)
        return <Spinner />

    return (
        <div className='flex flex-col gap-6'>
            <section className='flex flex-col gap-3 rounded-sm border border-gray-200 bg-white p-4 shadow-sm'>
                <h4 className='bp6-heading m-0'>Pipelines</h4>

                {pipelines.length === 0 && (
                    <NonIdealState
                        icon='data-lineage'
                        title='No pipelines yet'
                        description='The PipelineRunner lists the ones in gridsense.pipelines when it starts: is it running?'
                    />
                )}

                {pipelines.length > 0 && (
                    <HTMLTable className='pipelines-table w-full bg-white' compact>
                        <thead>
                            <tr>
                                <th>Pipeline</th>
                                <th>Writes</th>
                                <th>Schedule <span className='font-normal text-gray-500'>(Romanian time)</span></th>
                                <th>On</th>
                                <th>Last run</th>
                                <th>Next run</th>
                                <th />
                            </tr>
                        </thead>
                        <tbody>
                            {pipelines.map(pipeline => (
                                <PipelineRow
                                    key={pipeline.name}
                                    pipeline={pipeline}
                                    schedule={schedules[pipeline.name] ?? null}
                                    lastRun={lastRuns[pipeline.name] ?? null}
                                    nextRun={nextRuns[pipeline.name] ?? null}
                                    onRunNow={() => void handleRunNow(pipeline.name)}
                                    onSelectRun={setSelected}
                                />
                            ))}
                        </tbody>
                    </HTMLTable>
                )}
            </section>

            <section className='grid grid-cols-5 items-start gap-4'>
                <div className='col-span-2 flex flex-col gap-3 rounded-sm border border-gray-200 bg-white p-4 shadow-sm'>
                    <h4 className='bp6-heading m-0'>Runs</h4>

                    {runsRequest.isError && <ErrorNotice title="Couldn't load the runs" error={runsRequest.error} />}

                    {runsRequest.isSuccess && runs.length === 0 && (
                        <NonIdealState icon='history' title='No runs yet' description='Switch a pipeline on, or run it now.' />
                    )}

                    {runs.length > 0 && (
                        <HTMLTable className='w-full bg-white' interactive compact>
                            <thead>
                                <tr>
                                    <th>Started</th>
                                    <th>Pipeline</th>
                                    <th>By</th>
                                    <th>Status</th>
                                    <th>Rows</th>
                                </tr>
                            </thead>
                            <tbody>
                                {runs.map(run => (
                                    <tr
                                        key={run.id}
                                        onClick={() => setSelected(run.id)}
                                        className={run.id === selected ? 'bg-blue-50' : undefined}
                                    >
                                        <td className='font-mono text-xs'>{formatClock(run.startedAt)}</td>
                                        <td className='font-semibold'>{run.pipeline}</td>
                                        <td className='text-xs text-gray-500'>{run.cause}</td>
                                        <td><RunStatusTag status={run.status} /></td>
                                        <td className='text-xs'>{formatRows(run)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </HTMLTable>
                    )}
                </div>

                <div className='col-span-3 flex flex-col gap-3 rounded-sm border border-gray-200 bg-white p-4 shadow-sm'>
                    <h4 className='bp6-heading m-0'>Log</h4>

                    {selected === null && (
                        <NonIdealState icon='console' title='Pick a run' description='Its log shows here — live while it runs.' />
                    )}

                    {selected !== null && <RunLog runId={selected} />}
                </div>
            </section>
        </div>
    )
}

interface PipelineRowProps {
    pipeline:    PipelineSDK.Listed
    schedule:    Pipeline.Schedule | null
    lastRun:     Pipeline.Run | null
    nextRun:     Date | null
    onRunNow:    () => void
    onSelectRun: (id: Pipeline.Run.Id) => void
}

function PipelineRow({ pipeline, schedule, lastRun, nextRun, onRunNow, onSelectRun }: PipelineRowProps) {
    const cron = schedule?.cron ?? pipeline.defaultCron
    const enabled = schedule?.enabled ?? false

    function handleCronChange(next: string) {
        void PipelineSDK.actions.pipeline.setSchedule(pipeline.name, { cron: next, enabled })
    }

    function handleEnabledChange(next: boolean) {
        void PipelineSDK.actions.pipeline.setSchedule(pipeline.name, { cron, enabled: next })
    }

    return (
        <tr className={pipeline.available ? undefined : 'opacity-50'}>
            <td>
                <div className='flex items-center gap-2'>
                    <span className='font-mono font-semibold'>{pipeline.name}</span>
                    {!pipeline.available && <Tag minimal intent='warning'>no longer in Python</Tag>}
                </div>
                <div className='text-xs text-gray-500'>{pipeline.description}</div>
            </td>
            <td>
                <div className='flex gap-1'>
                    {pipeline.outputs.map(output => <Tag key={output} minimal icon='database'>{output}</Tag>)}
                </div>
            </td>
            <td>
                <CronInput value={cron} defaultValue={pipeline.defaultCron} disabled={!pipeline.available} onChange={handleCronChange} />
            </td>
            <td>
                <Switch
                    checked={enabled}
                    disabled={!pipeline.available}
                    onChange={event => handleEnabledChange(event.currentTarget.checked)}
                    className='m-0'
                />
            </td>
            <td>
                {lastRun === null && <span className='text-xs text-gray-500'>never</span>}
                {lastRun !== null && (
                    <div className='flex items-center gap-2'>
                        <RunStatusTag status={lastRun.status} onClick={() => onSelectRun(lastRun.id)} />
                        <span className='text-xs text-gray-500'>{formatLocal(lastRun.startedAt)}</span>
                    </div>
                )}
            </td>
            <td>
                {enabled && nextRun ? <NextRun at={nextRun} /> : <span className='text-xs text-gray-500'>off</span>}
            </td>
            <td>
                <Button icon='play' text='Run now' variant='outlined' size='small' disabled={!pipeline.available} onClick={onRunNow} />
            </td>
        </tr>
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
