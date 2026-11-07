import { useState } from 'react'
import { Alert, Button, Icon, InputGroup, Switch } from '@blueprintjs/core'
import type { Replay } from '@gridsense/shared/domain'
import { PipelineSDK } from '@/SDKs/PipelineSDK/sdk'
import { ReplaySDK } from '@/SDKs/ReplaySDK/sdk'

// "Auto": a day every two minutes — the forecast on even minutes, the auction a minute after.
const AUTO_CRONS = {
    forecast: '0-58/2 * * * *',
    prices:   '1-59/2 * * * *',
} as const

const DAY = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })

/** `2025-04-24` → `Thu 24 Apr 2025` */
const formatDay = (day: Replay.LocalDate) => DAY.format(new Date(`${day}T12:00:00Z`))

/** `2025-04-24`, 7 → `2025-05-01`: calendar days, so a clock change doesn't matter. */
const addDays = (day: Replay.LocalDate, days: number) => new Date(Date.parse(`${day}T12:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10)

/**
 * The replay, floating at the bottom of every page: where it is, a day at a time or on its own, and starting over —
 * from the same day or another — so the demo can be rehearsed whichever page it's shown on. Collapses to a pill.
 */
export function ReplayCard() {
    const [, [replayRequest]] = ReplaySDK.useWith(
        () => null,
        query => [query.replay],
    )

    const schedules = PipelineSDK.useStore(state => state.schedules)
    const [start, setStart] = useState<string | null>(null)
    const [confirming, setConfirming] = useState<'reset' | 'start' | null>(null)
    const [isBusy, setIsBusy] = useState(false)
    const [isCollapsed, setIsCollapsed] = useState(false)

    // The card stays out of the way until the server answers; it never takes the page down with it.
    if (replayRequest.data === undefined)
        return null

    // Collapsed: a small pill in the corner, with the day — the card again on a click.
    if (isCollapsed)
        return (
            <div className='fixed bottom-4 right-4 z-20'>
                <Button
                    icon='history'
                    text={replayRequest.data.issued === null ? 'Replay' : `Replay · ${formatDay(replayRequest.data.issued)}`}
                    className='shadow-lg'
                    onClick={() => setIsCollapsed(false)}
                />
            </div>
        )

    const state = replayRequest.data
    const chosenStart = start ?? state.start
    const isAuto = schedules.forecast?.enabled === true && schedules.prices?.enabled === true

    async function run(action: () => Promise<unknown>) {
        setIsBusy(true)

        try {
            await action()
        }
        finally {
            setIsBusy(false)
        }
    }

    async function handleAuto(on: boolean) {
        await run(async () => {
            await PipelineSDK.actions.pipeline.setSchedule('forecast', { cron: AUTO_CRONS.forecast, enabled: on })
            await PipelineSDK.actions.pipeline.setSchedule('prices', { cron: AUTO_CRONS.prices, enabled: on })
        })
    }

    async function handleConfirm() {
        const what = confirming
        setConfirming(null)

        if (what === 'reset')
            await run(() => ReplaySDK.actions.replay.reset())

        if (what === 'start')
            await run(async () => {
                await ReplaySDK.actions.replay.setStart(chosenStart)
                setStart(null)
            })
    }

    return (
        <div className='fixed bottom-4 left-1/2 z-20 flex w-max max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-6 whitespace-nowrap rounded-lg border border-gray-200 bg-white/95 px-4 py-2 shadow-lg backdrop-blur'>
            <div className='flex items-center gap-2'>
                <Icon icon='history' className='text-gray-500' />
                <span className='font-semibold'>Replay</span>
            </div>

            <Stat label='Today (replay)' value={state.issued === null ? 'Not started' : formatDay(state.issued)} />
            <Stat
                label='Forecast (10:00)'
                value={state.issued === null ? '—' : `${formatDay(addDays(state.issued, 1))} → ${formatDay(addDays(state.issued, 7))}`}
            />
            <Stat label='Auction (14:00)' value={state.cleared === null ? '—' : `prices known for ${formatDay(state.cleared)}`} />

            <div className='flex items-center gap-3'>
                <Button
                    icon='step-forward'
                    intent='primary'
                    text='Advance one day'
                    disabled={isBusy || isAuto}
                    onClick={() => void run(() => ReplaySDK.actions.replay.step())}
                />
                <Switch
                    className='mb-0'
                    label='Auto: a day every 2 min'
                    checked={isAuto}
                    disabled={isBusy}
                    onChange={event => void handleAuto(event.currentTarget.checked)}
                />
            </div>

            <div
                className='flex items-center gap-2 border-l border-gray-200 pl-6'
                title={`A day is a forecast issued at 10:00, then that afternoon's auction. The replay may start between ${formatDay(state.range.from)} and ${formatDay(state.range.to)}.`}
            >
                <span className='text-xs text-gray-500'>Starts</span>
                <div className='w-40'>
                    <InputGroup
                        type='date'
                        value={chosenStart}
                        min={state.range.from}
                        max={state.range.to}
                        onValueChange={setStart}
                    />
                </div>
                {chosenStart !== state.start
                    ? <Button text='Start over here' disabled={isBusy || chosenStart === ''} onClick={() => setConfirming('start')} />
                    : <Button icon='reset' text='Reset' disabled={isBusy} onClick={() => setConfirming('reset')} />}
            </div>

            <Button icon='minimize' variant='minimal' size='small' aria-label='Collapse the replay' onClick={() => setIsCollapsed(true)} />

            <Alert
                isOpen={confirming !== null}
                icon='reset'
                intent='danger'
                confirmButtonText='Start over'
                cancelButtonText='Cancel'
                onConfirm={() => void handleConfirm()}
                onCancel={() => setConfirming(null)}
            >
                <p>
                    Start the replay over from <b>{formatDay(confirming === 'start' ? chosenStart : state.start)}</b>?
                    The replay's forecasts and prices, its runs, the hits waiting for the agent and the triggers' progress
                    are cleared.
                </p>
            </Alert>
        </div>
    )
}

function Stat({ label, value }: { label: string; value: string }) {
    return (
        <div className='flex flex-col leading-tight'>
            <span className='text-xs text-gray-500'>{label}</span>
            <span className='text-sm font-semibold'>{value}</span>
        </div>
    )
}
