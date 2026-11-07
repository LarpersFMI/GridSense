import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { formatLocal } from '@/utils/format'
import { formatValue, isShortSpan, nearest, niceTicks, timeTicks, type Series } from './charts'

const HEIGHT = 220
const MARGIN = { top: 12, right: 16, bottom: 26, left: 52 }

// A longer gap between two points than this breaks the line: a missing day isn't drawn as a slope across it.
const GAP_MS = 3 * 60 * 60_000

const DAY = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Bucharest', weekday: 'short', day: 'numeric', month: 'short' })
const HOUR = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Bucharest', hour: '2-digit', minute: '2-digit' })

interface LineChartProps {
    series:  Series[]
    hoverAt: number | null               // shared by every chart on the page: the crosshair follows the pointer across them
    onHover: (at: number | null) => void
    dimmed?: boolean                     // refetching: the last render stays, faded
}

/**
 * Lines over time on one axis, as SVG: hairline grid, a stronger zero line when the values cross it, 2px lines, a
 * crosshair snapping to the nearest hour with every line's value in one tooltip.
 */
export function LineChart({ series, hoverAt, onHover, dimmed }: LineChartProps) {
    const boxRef = useRef<HTMLDivElement>(null)
    const [width, setWidth] = useState(0)

    useEffect(() => {
        const box = boxRef.current

        if (box === null)
            return

        const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))

        observer.observe(box)

        return () => observer.disconnect()
    }, [])

    const all = series.flatMap(line => line.points)

    // The same box either way: the size observer stays on it when values arrive.
    if (all.length === 0)
        return (
            <div ref={boxRef} className='relative flex items-center justify-center text-xs text-gray-500' style={{ height: HEIGHT }}>
                No numeric values in these rows.
            </div>
        )

    const start = Math.min(...all.map(point => point.t))
    const end = Math.max(...all.map(point => point.t))
    const yTicks = niceTicks(Math.min(...all.map(point => point.v)), Math.max(...all.map(point => point.v)))
    const yMin = yTicks[0]
    const yMax = yTicks[yTicks.length - 1]

    const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 1)
    const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
    const toX = (t: number) => MARGIN.left + (end === start ? plotWidth / 2 : ((t - start) / (end - start)) * plotWidth)
    const toY = (v: number) => MARGIN.top + plotHeight - ((v - yMin) / (yMax - yMin)) * plotHeight

    const short = isShortSpan(start, end)
    const xTicks = timeTicks(start, end)

    // The crosshair snaps to the first line's nearest point; every line reads its own nearest one.
    const snapped = hoverAt !== null && hoverAt >= start - GAP_MS && hoverAt <= end + GAP_MS
        ? nearest(series.find(line => line.points.length > 0)!.points, hoverAt)
        : null
    const readings = snapped === null ? [] : series.map(line => ({ line, point: nearest(line.points, snapped.t) }))

    function handlePointerMove(event: PointerEvent<SVGRectElement>) {
        const bounds = event.currentTarget.getBoundingClientRect()
        const ratio = (event.clientX - bounds.left) / bounds.width

        onHover(start + ratio * (end - start))
    }

    const tooltipLeft = snapped === null ? 0 : toX(snapped.t)
    const tooltipOnLeft = tooltipLeft > width - 200

    return (
        <div ref={boxRef} className='relative select-none' style={{ height: HEIGHT, opacity: dimmed ? 0.5 : 1 }}>
            {width > 0 && (
                <svg width={width} height={HEIGHT} className='block'>
                    {yTicks.map(tick => (
                        <g key={tick}>
                            <line
                                x1={MARGIN.left}
                                x2={MARGIN.left + plotWidth}
                                y1={toY(tick)}
                                y2={toY(tick)}
                                stroke={tick === 0 && yMin < 0 ? '#c3c2b7' : '#e1e0d9'}
                                strokeWidth={1}
                            />
                            <text x={MARGIN.left - 8} y={toY(tick)} dy='0.32em' textAnchor='end' fontSize={11} fill='#898781' className='tabular-nums'>
                                {formatValue(tick)}
                            </text>
                        </g>
                    ))}

                    {xTicks.map(tick => (
                        <g key={tick}>
                            <line x1={toX(tick)} x2={toX(tick)} y1={MARGIN.top + plotHeight} y2={MARGIN.top + plotHeight + 4} stroke='#c3c2b7' />
                            <text x={toX(tick)} y={HEIGHT - 6} textAnchor='middle' fontSize={11} fill='#898781'>
                                {short ? HOUR.format(tick) : DAY.format(tick)}
                            </text>
                        </g>
                    ))}

                    <line x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={MARGIN.top + plotHeight} y2={MARGIN.top + plotHeight} stroke='#c3c2b7' />

                    {series.map(line => (
                        <path
                            key={line.column}
                            d={toPath(line, toX, toY)}
                            fill='none'
                            stroke={line.color}
                            strokeWidth={2}
                            strokeLinejoin='round'
                            strokeLinecap='round'
                        />
                    ))}

                    {snapped !== null && (
                        <g pointerEvents='none'>
                            <line x1={toX(snapped.t)} x2={toX(snapped.t)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} stroke='#898781' strokeWidth={1} />
                            {readings.map(({ line, point }) => point !== null && (
                                <circle key={line.column} cx={toX(point.t)} cy={toY(point.v)} r={4} fill={line.color} stroke='#ffffff' strokeWidth={2} />
                            ))}
                        </g>
                    )}

                    {/* The hit area is the whole plot: the reader aims at a time, never at a 2px line. */}
                    <rect
                        x={MARGIN.left}
                        y={MARGIN.top}
                        width={plotWidth}
                        height={plotHeight}
                        fill='transparent'
                        onPointerMove={handlePointerMove}
                        onPointerLeave={() => onHover(null)}
                    />
                </svg>
            )}

            {snapped !== null && (
                <div
                    className='pointer-events-none absolute z-10 rounded border border-gray-200 bg-white px-2.5 py-2 text-xs shadow-md'
                    style={{
                        top:       MARGIN.top,
                        left:      tooltipOnLeft ? undefined : tooltipLeft + 12,
                        right:     tooltipOnLeft ? width - tooltipLeft + 12 : undefined,
                        minWidth:  140,
                    }}
                >
                    <div className='mb-1 text-gray-500'>{formatLocal(new Date(snapped.t))}</div>
                    {readings.map(({ line, point }) => (
                        <div key={line.column} className='flex items-center gap-2 leading-5'>
                            <span className='inline-block h-0.5 w-3 rounded' style={{ background: line.color }} />
                            <span className='font-semibold tabular-nums text-gray-900'>{point === null ? '—' : formatValue(point.v)}</span>
                            <span className='text-gray-500'>{line.column}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

/** The line as an SVG path, lifted wherever two points are more than GAP_MS apart. */
function toPath(line: Series, toX: (t: number) => number, toY: (v: number) => number): string {
    let path = ''
    let previous: number | null = null

    for (const point of line.points) {
        const command = previous === null || point.t - previous > GAP_MS ? 'M' : 'L'

        path += `${command}${toX(point.t).toFixed(1)},${toY(point.v).toFixed(1)}`
        previous = point.t
    }

    return path
}
