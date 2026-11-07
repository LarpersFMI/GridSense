import { Button, HTMLTable, Section, SectionCard } from '@blueprintjs/core'
import type { Trigger } from '@gridsense/shared/domain'
import { formatCondition } from '../triggers/format'
import { formatCause, formatWindow } from './format'

interface HitDetailsProps {
    queued:  Trigger.Hit.Queued
    trigger: Trigger | null
    onClose: () => void
}

/** One hit as the agent gets it: which trigger, on which hours, and what the matching hours looked like. */
export function HitDetails({ queued, trigger, onClose }: HitDetailsProps) {
    const { hit } = queued

    let hours = `${hit.matchedHours} hours`

    if (hit.window !== null)
        hours = formatWindow(hit.window)

    return (
        <Section
            title={trigger?.name ?? 'Deleted trigger'}
            subtitle={hours}
            compact
            rightElement={<Button icon='cross' variant='minimal' onClick={onClose} aria-label='Close' />}
        >
            <SectionCard>
                <dl className='grid grid-cols-[10rem_1fr] gap-y-1 text-sm'>
                    <dt className='text-gray-500'>Read</dt>
                    <dd className='m-0'>{formatCause(hit.cause)}</dd>
                    <dt className='text-gray-500'>Forecast from run</dt>
                    <dd className='m-0 font-mono text-xs'>{hit.runId ?? 'none'}</dd>
                    <dt className='text-gray-500'>Thread</dt>
                    <dd className='m-0 font-mono text-xs break-all'>{queued.threadId}</dd>
                    <dt className='text-gray-500'>Conditions</dt>
                    <dd className='m-0 font-mono text-xs'>
                        {trigger?.conditions.map((condition, index) => (
                            <div key={index}>{formatCondition(condition)}</div>
                        ))}
                    </dd>
                </dl>
            </SectionCard>
            <SectionCard padded={false}>
                <HTMLTable compact className='w-full'>
                    <thead>
                        <tr>
                            <th>Evidence</th>
                            <th className='text-right'>Value</th>
                        </tr>
                    </thead>
                    <tbody>
                        {Object.entries(hit.evidence).map(([name, value]) => (
                            <tr key={name}>
                                <td className='font-mono text-xs'>{name}</td>
                                <td className='text-right font-mono text-xs'>{formatNumber(value)}</td>
                            </tr>
                        ))}
                    </tbody>
                </HTMLTable>
            </SectionCard>
        </Section>
    )
}

const formatNumber = (value: number) => Number.isInteger(value) ? String(value) : value.toFixed(3)
