import { useState } from 'react'
import { AnchorButton, Button, NonIdealState } from '@blueprintjs/core'
import { Agent, Time, type Foundations } from '@gridsense/shared/domain'
import { AgentSDK } from '@/SDKs/AgentSDK/sdk'
import { ReplaySDK } from '@/SDKs/ReplaySDK/sdk'

// The hours shown: free hours fall around midday; the evening is where the shifted consumption comes from.
const FIRST_HOUR = 7
const LAST_HOUR = 21
const HOUR_PX = 36

const DAY_MS = 86_400_000

const WEEKDAY = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short' })
const DATE = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short' })
const RANGE = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'long', year: 'numeric' })

/** `2025-04-24`, 7 → `2025-05-01`: calendar days. */
const addDays = (day: string, days: number) => new Date(Date.parse(`${day}T12:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10)
const asDate = (day: string) => new Date(`${day}T12:00:00Z`)

/** The Monday of the week a day falls in. */
const mondayOf = (day: string) => addDays(day, -Time.Local.getWeekday(day))

/** How a slot looks: by what became of it, and how sure it was when announced. */
function look(slot: Agent.Slot): { box: string; text: string } {
    if (slot.status === 'cancelled')
        return { box: 'bg-red-50 ring-red-300 line-through text-red-800', text: 'Cancelled' }

    if (slot.status === 'confirmed')
        return { box: 'bg-green-100 ring-green-400 text-green-900', text: 'Confirmed' }

    if (slot.label === 'possible')
        return { box: 'bg-amber-50 ring-amber-400 text-amber-900', text: 'Possible · approved' }

    return { box: 'bg-blue-100 ring-blue-400 text-blue-900', text: 'Likely · announced' }
}

/**
 * The free-hours calendar: a week of days by hours, each slot the agent announced, confirmed or cancelled as a block
 * where it falls, the replay's day marked. A block opens the thread that last decided it.
 */
export function CalendarView({ onOpen }: { onOpen: (id: Foundations.Thread.Id) => void }) {
    const slots = AgentSDK.useStore(AgentSDK.selectors.slots)
    const [, [replayRequest]] = ReplaySDK.useWith(() => null, query => [query.replay])

    const today = replayRequest.data?.issued ?? null
    const firstSlotDay = slots.length > 0 ? Time.Local.of(slots[0].start).day : null
    const [monday, setMonday] = useState<string | null>(null)

    const shown = monday ?? mondayOf(today ?? firstSlotDay ?? new Date().toISOString().slice(0, 10))
    const days = Array.from({ length: 7 }, (_, index) => addDays(shown, index))
    const hours = Array.from({ length: LAST_HOUR - FIRST_HOUR }, (_, index) => FIRST_HOUR + index)

    if (slots.length === 0)
        return <NonIdealState icon='calendar' title='No free hours yet' description='The agent announces a slot when every hour is ≥ 0.8, or when the operator approves one.' />

    return (
        <div className='flex flex-col gap-3'>
            <div className='flex flex-wrap items-center gap-2'>
                <Button icon='chevron-left' variant='minimal' aria-label='Previous week' onClick={() => setMonday(addDays(shown, -7))} />
                <Button icon='chevron-right' variant='minimal' aria-label='Next week' onClick={() => setMonday(addDays(shown, 7))} />
                {today && <Button size='small' text='Today' onClick={() => setMonday(mondayOf(today))} />}
                <span className='ml-1 font-semibold'>{RANGE.format(asDate(days[0]))} – {RANGE.format(asDate(days[6]))}</span>

                <div className='ml-auto flex flex-wrap items-center gap-3 text-xs text-gray-600'>
                    <Legend className='bg-green-100 ring-green-400' text='Confirmed' />
                    <Legend className='bg-blue-100 ring-blue-400' text='Likely, announced' />
                    <Legend className='bg-amber-50 ring-amber-400' text='Possible, approved' />
                    <Legend className='bg-red-50 ring-red-300' text='Cancelled' />
                    <AnchorButton size='small' icon='download' text='.ics' href={Agent.API.CALENDAR_PATH} />
                </div>
            </div>

            <div className='overflow-hidden rounded-sm border border-gray-200 bg-white'>
                <div className='grid grid-cols-[3.5rem_repeat(7,1fr)] border-b border-gray-200'>
                    <div />
                    {days.map(day => (
                        <div key={day} className={`border-l border-gray-100 px-2 py-1.5 text-center ${day === today ? 'bg-blue-50' : ''}`}>
                            <div className='text-xs text-gray-500'>{WEEKDAY.format(asDate(day))}</div>
                            <div className={`text-sm font-semibold ${day === today ? 'text-blue-700' : ''}`}>{DATE.format(asDate(day))}</div>
                        </div>
                    ))}
                </div>

                <div className='grid grid-cols-[3.5rem_repeat(7,1fr)]'>
                    <div>
                        {hours.map(hour => (
                            <div key={hour} className='pr-2 text-right font-mono text-[10px] text-gray-400' style={{ height: HOUR_PX }}>
                                {String(hour).padStart(2, '0')}:00
                            </div>
                        ))}
                    </div>

                    {days.map(day => (
                        <div key={day} className={`relative border-l border-gray-100 ${day === today ? 'bg-blue-50/40' : ''}`}>
                            {hours.map(hour => <div key={hour} className='border-t border-gray-100' style={{ height: HOUR_PX }} />)}

                            {slots.filter(slot => Time.Local.of(slot.start).day === day).map(slot => {
                                const start = Time.Local.of(slot.start).hour
                                const end = start + Math.round((slot.end.getTime() - slot.start.getTime()) / 3_600_000)
                                const { box, text } = look(slot)
                                const thread = slot.threadIds[slot.threadIds.length - 1] ?? null

                                return (
                                    <div
                                        key={slot.key}
                                        role='button'
                                        tabIndex={0}
                                        title={slot.reason}
                                        onClick={() => thread && onOpen(thread)}
                                        onKeyDown={event => event.key === 'Enter' && thread && onOpen(thread)}
                                        className={`absolute inset-x-1 cursor-pointer overflow-hidden rounded px-1.5 py-1 text-xs shadow-sm ring-1 hover:brightness-95 ${box}`}
                                        style={{ top: (start - FIRST_HOUR) * HOUR_PX + 1, height: (end - start) * HOUR_PX - 2 }}
                                    >
                                        <div className='font-semibold'>{String(start).padStart(2, '0')}:00–{String(end).padStart(2, '0')}:00</div>
                                        <div>{text}</div>
                                    </div>
                                )
                            })}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}

function Legend({ className, text }: { className: string; text: string }) {
    return (
        <span className='flex items-center gap-1.5'>
            <span className={`inline-block h-3 w-3 rounded-sm ring-1 ${className}`} />
            {text}
        </span>
    )
}
