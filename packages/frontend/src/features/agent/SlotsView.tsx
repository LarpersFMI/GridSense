import { AnchorButton, HTMLTable, NonIdealState, Tag } from '@blueprintjs/core'
import { Agent, Time } from '@gridsense/shared/domain'
import { AgentSDK } from '@/SDKs/AgentSDK/sdk'
import { DecisionTag, SlotStatusTag } from './tags'

const DAY = new Intl.DateTimeFormat('en-GB', { timeZone: Time.Local.TIME_ZONE, weekday: 'long', day: 'numeric', month: 'long' })
const HOUR = new Intl.DateTimeFormat('en-GB', { timeZone: Time.Local.TIME_ZONE, hour: '2-digit', minute: '2-digit' })

/** The free-hours calendar: every slot the agent announced, confirmed or cancelled, by day, and the .ics of it. */
export function SlotsView() {
    const slots = AgentSDK.useStore(AgentSDK.selectors.slots)

    if (slots.length === 0)
        return <NonIdealState icon='calendar' title='No free hours yet' description='The agent announces a slot when every hour is ≥ 0.8, or when the operator approves one.' />

    const days = new Map<string, Agent.Slot[]>()

    for (const slot of slots) {
        const day = Time.Local.of(slot.start).day

        days.set(day, [...(days.get(day) ?? []), slot])
    }

    return (
        <div className='flex flex-col gap-3'>
            <div className='flex items-center gap-2'>
                <span className='text-sm text-gray-500'>Confirmed and announced slots, as customers' calendars get them.</span>
                <div className='ml-auto'>
                    <AnchorButton icon='calendar' text='Download calendar (.ics)' href={Agent.API.CALENDAR_PATH} />
                </div>
            </div>

            <div className='rounded-sm border border-gray-200 bg-white'>
                <HTMLTable className='w-full' compact>
                    <thead>
                        <tr>
                            <th>Day</th>
                            <th>Hours</th>
                            <th>Label</th>
                            <th>Status</th>
                            <th>Why</th>
                        </tr>
                    </thead>
                    <tbody>
                        {[...days.entries()].map(([day, items]) => items.map((slot, index) => (
                            <tr key={slot.key}>
                                <td className='whitespace-nowrap font-semibold'>{index === 0 ? DAY.format(slot.start) : ''}</td>
                                <td className='whitespace-nowrap'>{HOUR.format(slot.start)}–{HOUR.format(slot.end)}</td>
                                <td><DecisionTag label={slot.label} /></td>
                                <td><SlotStatusTag status={slot.status} /></td>
                                <td className='text-sm text-gray-600'>
                                    {slot.reason}
                                    {slot.threadIds.length > 1 && <Tag minimal round className='ml-2'>{slot.threadIds.length} decisions</Tag>}
                                </td>
                            </tr>
                        ))).flat()}
                    </tbody>
                </HTMLTable>
            </div>
        </div>
    )
}
