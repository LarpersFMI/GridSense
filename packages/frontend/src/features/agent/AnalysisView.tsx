import { Icon, Tag } from '@blueprintjs/core'
import type { Agent } from '@gridsense/shared/domain'
import { formatCount } from '@/utils/format'
import { AiBadge } from './tags'

const EUR = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })

/**
 * The agent's impact analysis, with what wrote what in plain view: the text — recommendation, why, risks, what it
 * couldn't check — in a purple block when Claude wrote it (from the agent's tools), grey when the template did; the
 * impact's numbers below it, computed, never generated.
 */
export function AnalysisView({ analysis }: { analysis: Agent.Analysis }) {
    const { impact } = analysis
    const byAi = analysis.writtenBy === 'llm'

    return (
        <div className='flex flex-col gap-3'>
            <div className={`flex flex-col gap-3 rounded-md p-3 ${byAi ? 'bg-violet-50 ring-1 ring-violet-200' : 'bg-gray-50 ring-1 ring-gray-200'}`}>
                <div className='flex items-center gap-2'>
                    <div className='shrink-0'>
                        {byAi ? <AiBadge /> : <Tag minimal round icon='document'>Template</Tag>}
                    </div>
                    <span className='text-xs text-gray-500'>{byAi ? 'explains the decision, doesn’t take it' : 'the agent’s figures, fixed sentences'}</span>
                </div>

                <div className='flex items-start gap-2'>
                    <Icon icon='lightbulb' className='mt-0.5 text-amber-600' />
                    <p className='m-0 font-semibold leading-snug'>{analysis.recommendation}</p>
                </div>

                <Points title='Why' icon='tick-circle' points={analysis.why} />
                <Points title='Risks' icon='warning-sign' points={analysis.risks} />
                <Points title="Couldn't check" icon='help' points={analysis.unverified} />
            </div>

            {impact.customers !== null && (
                <div className='flex flex-col gap-1.5'>
                    <div className='grid grid-cols-3 gap-2'>
                        <Stat label='Customers reached' value={formatCount(impact.customers)} />
                        <Stat label='Consumption moved' value={impact.shiftedMwh === null ? '—' : `${impact.shiftedMwh} MWh`} />
                        <Stat label='Value for PPC' value={impact.valueEur === null ? '—' : EUR.format(impact.valueEur)} />
                    </div>
                    <div className='flex items-center gap-2 text-xs text-gray-500'>
                        <div className='shrink-0'>
                            <Tag minimal round icon='calculator'>Computed</Tag>
                        </div>
                        <span>{impact.basis}</span>
                    </div>
                </div>
            )}
        </div>
    )
}

function Stat({ label, value }: { label: string; value: string }) {
    return (
        <div className='rounded border border-gray-200 bg-white px-3 py-2'>
            <div className='text-xs text-gray-500'>{label}</div>
            <div className='text-lg font-semibold'>{value}</div>
        </div>
    )
}

function Points({ title, icon, points }: { title: string; icon: 'tick-circle' | 'warning-sign' | 'help'; points: string[] }) {
    if (points.length === 0)
        return null

    return (
        <div>
            <div className='mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500'>
                <Icon icon={icon} size={12} />
                {title}
            </div>
            <ul className='m-0 flex list-disc flex-col gap-1 pl-5 text-sm'>
                {points.map(point => <li key={point}>{point}</li>)}
            </ul>
        </div>
    )
}
