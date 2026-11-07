import { Button, Spinner, Tag } from '@blueprintjs/core'
import type { Dataset } from '@gridsense/shared/domain'
import { Dropdown } from '@/components/Dropdown'
import { DatasetSDK } from '@/SDKs/DatasetSDK/sdk'
import { formatCount } from '@/utils/format'
import { MAX_SERIES, SERIES_COLORS, toSeries, type ChartSpec } from './charts'
import { LineChart } from './LineChart'

interface ChartCardProps {
    dataset:  Dataset.Name
    columns:  Dataset.Description.Column[]
    chart:    ChartSpec
    hoverAt:  number | null
    onHover:  (at: number | null) => void
    onChange: (chart: ChartSpec) => void
    onRemove: () => void
}

/** One chart and its controls in one row above it: the time column, the lines, which rows. */
export function ChartCard({ dataset, columns, chart, hoverAt, onHover, onChange, onRemove }: ChartCardProps) {
    const timestamps = columns.filter(column => column.type === 'timestamp').map(column => column.name)
    const numbers = columns.filter(column => column.type === 'number').map(column => column.name)

    // With `latest`, newest first by it: its newest value's rows come first, whatever their `x`.
    const orderBy = chart.latest ?? chart.x

    const [, [rowsRequest]] = DatasetSDK.useWith(
        () => null,
        query => [query.chartRows(dataset, orderBy)],
    )

    const rows = rowsRequest.data?.rows ?? []
    const series = toSeries(chart, rows)
    const plotted = Math.max(0, ...series.map(line => line.points.length))

    const rowOptions = [
        { value: '', label: 'All rows' },
        ...timestamps.filter(column => column !== chart.x).map(column => ({ value: column, label: `Newest ${column} only` })),
    ]

    function handleXChange(x: string) {
        onChange({ ...chart, x, latest: chart.latest === x ? null : chart.latest })
    }

    return (
        <div className='rounded border border-gray-200 bg-white'>
            <div className='flex flex-wrap items-center gap-2 border-b border-gray-100 px-3 py-2'>
                {chart.y.map((column, index) => (
                    <Tag
                        key={column}
                        minimal
                        onRemove={chart.y.length > 1 ? () => onChange({ ...chart, y: chart.y.filter(other => other !== column) }) : undefined}
                        icon={<span className='inline-block h-0.5 w-3 rounded' style={{ background: SERIES_COLORS[index] }} />}
                    >
                        {column}
                    </Tag>
                ))}

                {chart.y.length < MAX_SERIES && (
                    <Dropdown
                        value=''
                        placeholder='Add line'
                        options={numbers.filter(column => !chart.y.includes(column)).map(column => ({ value: column, label: column }))}
                        onChange={column => onChange({ ...chart, y: [...chart.y, column] })}
                    />
                )}

                <span className='ml-2 text-xs text-gray-500'>over</span>
                <Dropdown
                    value={chart.x}
                    options={timestamps.map(column => ({ value: column, label: column }))}
                    onChange={handleXChange}
                />

                {rowOptions.length > 1 && (
                    <Dropdown
                        value={chart.latest ?? ''}
                        options={rowOptions}
                        onChange={latest => onChange({ ...chart, latest: latest === '' ? null : latest })}
                    />
                )}

                <span className='ml-auto text-xs text-gray-500'>
                    {rowsRequest.isFetching && <Spinner size={12} className='mr-1 inline-block align-middle' />}
                    {formatCount(plotted)} points
                </span>
                <Button icon='cross' variant='minimal' size='small' aria-label='Remove chart' onClick={onRemove} />
            </div>

            <div className='px-2 py-2'>
                {rowsRequest.data === undefined
                    ? <div className='flex h-[220px] items-center justify-center'><Spinner size={20} /></div>
                    : <LineChart series={series} hoverAt={hoverAt} onHover={onHover} dimmed={rowsRequest.isPlaceholderData} />}
            </div>
        </div>
    )
}
