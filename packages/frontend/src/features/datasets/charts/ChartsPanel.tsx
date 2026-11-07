import { useState } from 'react'
import { Button } from '@blueprintjs/core'
import type { Dataset } from '@gridsense/shared/domain'
import { ChartCard } from './ChartCard'
import { createChart, loadCharts, saveCharts, type ChartSpec } from './charts'

interface ChartsPanelProps {
    dataset: Dataset.Name
    columns: Dataset.Description.Column[]
}

/**
 * The charts under a dataset's rows, kept in this browser per dataset (keyed by it: another dataset is another panel). Stacked one per row, so charts over the same
 * time column line up, and one crosshair moves across all of them: compare columns on different scales (a probability
 * and a price) as two charts, never on two axes.
 */
export function ChartsPanel({ dataset, columns }: ChartsPanelProps) {
    const [charts, setCharts] = useState<ChartSpec[]>(() => loadCharts(dataset))
    const [isOpen, setIsOpen] = useState(true)
    const [hoverAt, setHoverAt] = useState<number | null>(null)

    function update(next: ChartSpec[]) {
        setCharts(next)
        saveCharts(dataset, next)
    }

    const canChart = columns.some(column => column.type === 'timestamp') && columns.some(column => column.type === 'number')

    return (
        <section className={`flex min-h-0 flex-col border-t border-gray-200 bg-gray-50 ${isOpen && charts.length > 0 ? 'h-[55%]' : ''}`}>
            <div className='flex items-center gap-2 border-b border-gray-200 bg-white px-4 py-1.5'>
                <Button
                    icon={isOpen ? 'chevron-down' : 'chevron-up'}
                    variant='minimal'
                    size='small'
                    text={`Charts${charts.length > 0 ? ` (${charts.length})` : ''}`}
                    onClick={() => setIsOpen(!isOpen)}
                />
                <div className='ml-auto'>
                    <Button
                        icon='timeline-line-chart'
                        size='small'
                        text='Add chart'
                        disabled={!canChart}
                        onClick={() => {
                            setIsOpen(true)
                            update([...charts, createChart(dataset, columns)])
                        }}
                    />
                </div>
            </div>

            {isOpen && charts.length > 0 && (
                <div className='flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-3'>
                    {charts.map(chart => (
                        <ChartCard
                            key={chart.id}
                            dataset={dataset}
                            columns={columns}
                            chart={chart}
                            hoverAt={hoverAt}
                            onHover={setHoverAt}
                            onChange={next => update(charts.map(other => (other.id === next.id ? next : other)))}
                            onRemove={() => update(charts.filter(other => other.id !== chart.id))}
                        />
                    ))}
                </div>
            )}
        </section>
    )
}
