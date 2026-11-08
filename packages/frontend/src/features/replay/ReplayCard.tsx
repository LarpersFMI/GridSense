import { useState } from 'react'
import { Alert, Button, Dialog, DialogBody, DialogFooter, Icon, InputGroup, Menu, MenuDivider, MenuItem, PopoverNext, Tag } from '@blueprintjs/core'
import type { Replay } from '@gridsense/shared/domain'
import { PipelineSDK } from '@/SDKs/PipelineSDK/sdk'
import { ReplaySDK } from '@/SDKs/ReplaySDK/sdk'

// "Auto": a day every two minutes — the forecast on even minutes, the auction a minute after.
const AUTO_CRONS = {
    forecast: '0-58/2 * * * *',
    prices:   '1-59/2 * * * *',
} as const

// The menu scales in from its button, as the app's dropdowns do.
const MENU_TRANSITION_MS = 200

const DAY = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })

/** `2025-04-24` → `Thu 24 Apr 2025` */
const formatDay = (day: Replay.LocalDate) => DAY.format(new Date(`${day}T12:00:00Z`))

/** `2025-04-24`, 7 → `2025-05-01`: calendar days, so a clock change doesn't matter. */
const addDays = (day: Replay.LocalDate, days: number) => new Date(Date.parse(`${day}T12:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10)

/**
 * The replay, floating at the bottom of every page: where it is, and a day at a time. The rest — advancing on its own,
 * starting over from the same day or another, collapsing to a pill — is in its ⋯ menu.
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
    const [isMenuOpen, setIsMenuOpen] = useState(false)
    const [isPickingStart, setIsPickingStart] = useState(false)

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
        setIsMenuOpen(false)

        if (what === 'reset')
            await run(() => ReplaySDK.actions.replay.reset())

        if (what === 'start')
            await run(async () => {
                await ReplaySDK.actions.replay.setStart(chosenStart)
                setStart(null)
            })
    }

    function handleMenu(open: boolean) {
        setIsMenuOpen(open)
    }

    const menu = (
        <Menu>
            <MenuItem
                icon={isAuto ? 'pause' : 'play'}
                text={isAuto ? 'Stop advancing on its own' : 'Advance on its own (a day every 2 min)'}
                disabled={isBusy}
                onClick={() => void handleAuto(!isAuto)}
            />
            <MenuDivider />
            <MenuItem icon='reset' text={`Start over from ${formatDay(state.start)}`} disabled={isBusy} onClick={() => setConfirming('reset')} />
            <MenuItem icon='calendar' text='Start from another day…' disabled={isBusy} onClick={() => setIsPickingStart(true)} />
            <MenuDivider />
            <MenuItem icon='minimize' text='Collapse' onClick={() => setIsCollapsed(true)} />
        </Menu>
    )

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

            <div className='flex items-center gap-1'>
                {isAuto
                    ? <Tag intent='primary' minimal round icon='play' large>Advancing on its own</Tag>
                    : <Button icon='step-forward' intent='primary' text='Advance one day' disabled={isBusy} onClick={() => void run(() => ReplaySDK.actions.replay.step())} />}

                <PopoverNext
                    content={menu}
                    isOpen={isMenuOpen}
                    onInteraction={handleMenu}
                    placement='top-end'
                    animation='scale'
                    transitionDuration={MENU_TRANSITION_MS}
                >
                    <Button icon='more' variant='minimal' aria-label='Replay options' />
                </PopoverNext>
            </div>

            <Dialog title='Start the replay from another day' icon='calendar' isOpen={isPickingStart} onClose={() => setIsPickingStart(false)}>
                <DialogBody>
                    <p className='mt-0 text-sm text-gray-600'>
                        The first day the forecast is issued, between {formatDay(state.range.from)} and {formatDay(state.range.to)}.
                    </p>
                    <div className='w-48'>
                        <InputGroup type='date' value={chosenStart} min={state.range.from} max={state.range.to} onValueChange={setStart} />
                    </div>
                </DialogBody>
                <DialogFooter
                    actions={(
                        <>
                            <Button text='Cancel' onClick={() => setIsPickingStart(false)} />
                            <Button
                                intent='primary'
                                text='Start over here'
                                disabled={chosenStart === '' || chosenStart === state.start}
                                onClick={() => {
                                    setIsPickingStart(false)
                                    setConfirming('start')
                                }}
                            />
                        </>
                    )}
                />
            </Dialog>

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
                    The replay's forecasts and prices, its runs, the agent's decisions and the triggers' progress are cleared.
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
