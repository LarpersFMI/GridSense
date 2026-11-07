import { useState } from 'react'
import { Card, HTMLTable, NonIdealState, Spinner, Tag } from '@blueprintjs/core'
import type { Foundations, Forecaster, Trigger, Watchdog } from '@gridsense/shared/domain'
import { ErrorNotice } from '@/components/ErrorNotice'
import { ForecasterSDK } from '@/SDKs/ForecasterSDK/sdk'
import { TriggerSDK } from '@/SDKs/TriggerSDK/sdk'
import { WatchdogSDK } from '@/SDKs/WatchdogSDK/sdk'
import { HitDetails } from './HitDetails'
import { formatCause, formatClock, formatLocal, formatWindow } from './format'

const STATUS_INTENTS: Record<Trigger.Hit.Queued.Status, 'none' | 'primary' | 'success' | 'danger'> = {
    waiting:   'none',
    active:    'primary',
    completed: 'success',
    failed:    'danger',
}

/** What happened, live: the runs reported, the checks the Watchdog ran, and the hits it handed the agent. */
export function ActivityPage() {
    const [selected, setSelected] = useState<Foundations.Thread.Id | null>(null)

    const [hits, [hitsRequest]] = WatchdogSDK.useWith(
        WatchdogSDK.selectors.hits,
        query => [query.hits],
    )

    const triggers = TriggerSDK.useStore(state => state.triggers)

    const selectedHit = hits.find(queued => queued.threadId === selected) ?? null

    return (
        <div className='grid grid-cols-3 gap-4'>
            <div className='col-span-2 flex flex-col gap-4'>
                <h2 className='bp6-heading m-0'>Hits</h2>

                {hitsRequest.isError && <ErrorNotice title="Couldn't load the hits" error={hitsRequest.error} />}

                {hitsRequest.isPending && hits.length === 0 && <Spinner />}

                {hitsRequest.isSuccess && hits.length === 0 && (
                    <NonIdealState
                        icon='pulse'
                        title='No hits yet'
                        description='When a dataset updates and a trigger holds, its hits show up here as they happen.'
                    />
                )}

                {hits.length > 0 && (
                    <HTMLTable className='w-full bg-white' interactive compact>
                        <thead>
                            <tr>
                                <th>Raised</th>
                                <th>Trigger</th>
                                <th>Hours</th>
                                <th>From</th>
                                <th>Agent</th>
                            </tr>
                        </thead>
                        <tbody>
                            {hits.map(queued => (
                                <tr
                                    key={queued.threadId}
                                    onClick={() => setSelected(queued.threadId)}
                                    className={queued.threadId === selected ? 'bg-blue-50' : undefined}
                                >
                                    <td className='font-mono text-xs'>{formatClock(queued.raisedAt)}</td>
                                    <td className='font-semibold'>{triggers[queued.hit.triggerId]?.name ?? 'Deleted trigger'}</td>
                                    <td>
                                        <HitHours hit={queued.hit} />
                                    </td>
                                    <td className='text-xs text-gray-500'>{formatCause(queued.hit.cause)}</td>
                                    <td>
                                        <Tag minimal intent={STATUS_INTENTS[queued.status]}>{queued.status}</Tag>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </HTMLTable>
                )}

                {selectedHit && (
                    <HitDetails
                        queued={selectedHit}
                        trigger={triggers[selectedHit.hit.triggerId] ?? null}
                        onClose={() => setSelected(null)}
                    />
                )}
            </div>

            <div className='flex flex-col gap-4'>
                <h2 className='bp6-heading m-0'>Live</h2>
                <Feed />
            </div>
        </div>
    )
}

function HitHours({ hit }: { hit: Trigger.Hit }) {
    if (hit.window === null)
        return <span className='text-gray-500'>{hit.matchedHours} hours</span>

    return (
        <span>
            {formatWindow(hit.window)}
            <span className='ml-1 text-xs text-gray-500'>({hit.window.hours} h)</span>
        </span>
    )
}

type FeedItem =
    | { kind: 'run'; at: Date; run: Forecaster.Run }
    | { kind: 'check'; at: Date; check: Watchdog.Event.Check.Completed }

/** The runs reported and the checks run, newest first. Checks are live only: since this page opened. */
function Feed() {
    const [runs, [runsRequest]] = ForecasterSDK.useWith(
        ForecasterSDK.selectors.runs,
        query => [query.runs],
    )

    const checks = WatchdogSDK.useStore(WatchdogSDK.selectors.checks)

    const items: FeedItem[] = []

    for (const run of runs)
        items.push({ kind: 'run', at: run.reportedAt, run })

    for (const check of checks)
        items.push({ kind: 'check', at: check.checkedAt, check })

    items.sort((a, b) => b.at.getTime() - a.at.getTime())

    if (runsRequest.isError)
        return <ErrorNotice title="Couldn't load the runs" error={runsRequest.error} />

    return (
        <div className='flex flex-col gap-2'>
            {items.slice(0, 40).map(item => (
                <Card key={`${item.kind}-${item.at.getTime()}`} compact>
                    {item.kind === 'run' && <RunItem run={item.run} />}
                    {item.kind === 'check' && <CheckItem check={item.check} />}
                </Card>
            ))}
        </div>
    )
}

function RunItem({ run }: { run: Forecaster.Run }) {
    return (
        <div className='flex flex-col gap-1'>
            <div className='flex items-center justify-between'>
                <Tag intent='primary' minimal icon='predictive-analysis'>Run reported</Tag>
                <span className='font-mono text-xs text-gray-500'>{formatClock(run.reportedAt)}</span>
            </div>
            <div className='text-sm'>issued {formatLocal(run.issueTs)} · {run.rows} hours</div>
            <div className='text-xs text-gray-500'>{run.modelVersion}</div>
        </div>
    )
}

function CheckItem({ check }: { check: Watchdog.Event.Check.Completed }) {
    let source = 'schedule'

    if (check.source.type === 'dataset')
        source = `${check.source.dataset} updated`

    return (
        <div className='flex flex-col gap-1'>
            <div className='flex items-center justify-between'>
                <Tag minimal icon='eye-open'>Checked: {source}</Tag>
                <span className='font-mono text-xs text-gray-500'>{formatClock(check.checkedAt)}</span>
            </div>
            <div className='text-sm'>
                {plural(check.triggersChecked, 'trigger')} with new rows · <b>{plural(check.hits, 'hit')}</b>
                {check.cooledDown > 0 && <span className='text-gray-500'> · {check.cooledDown} cooled down</span>}
            </div>
        </div>
    )
}

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`
