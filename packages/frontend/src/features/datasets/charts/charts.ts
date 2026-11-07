import { Dataset, Time } from '@gridsense/shared/domain'

/**
 * A chart an admin made under a dataset: numeric columns over a timestamp column. Kept in this browser, per dataset —
 * a viewing convenience, not shared state.
 */
export interface ChartSpec {
    id:     string
    x:      string                  // a timestamp column
    y:      string[]                // numeric columns, one line each, on one axis
    latest: string | null           // a timestamp column: only the rows of its newest value (predictions: the newest run)
}

export interface Point {
    t: number                       // epoch ms
    v: number
}

export interface Series {
    column: string
    color:  string
    points: Point[]
}

/**
 * One line per column, in this order and never cycled: eight at most (validated: adjacent pairs clear colour-blind
 * separation). Aqua, yellow and pink are under 3:1 on white, so the chips above the chart and the tooltip always name
 * every line.
 */
export const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'] as const

export const MAX_SERIES = SERIES_COLORS.length

const STORAGE_KEY = (dataset: Dataset.Name) => `gridsense.charts.${dataset}`

export function loadCharts(dataset: Dataset.Name): ChartSpec[] {
    try {
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY(dataset)) ?? '[]')

        return Array.isArray(stored) ? stored : []
    }
    catch {
        return []
    }
}

export function saveCharts(dataset: Dataset.Name, charts: ChartSpec[]): void {
    try {
        localStorage.setItem(STORAGE_KEY(dataset), JSON.stringify(charts))
    }
    catch {
        // Storage blocked (private window): the charts last as long as the page.
    }
}

// What a new chart shows first, where the file has these columns: the forecast's price range, the cleared price.
const DEFAULT_LINES: Record<Dataset.Name, string[]> = {
    predictions: ['price_p10', 'price_p50', 'price_p90'],
    prices:      ['price_mean'],
}

/**
 * A first chart for a dataset's columns: its usual lines (or its first number) over its last timestamp, and — when
 * there's another timestamp, as `issue_ts` in predictions — only that one's newest rows, so runs don't overlap on the
 * same hours.
 */
export function createChart(dataset: Dataset.Name, columns: Dataset.Description.Column[]): ChartSpec {
    const timestamps = columns.filter(column => column.type === 'timestamp').map(column => column.name)
    const numbers = columns.filter(column => column.type === 'number').map(column => column.name)
    const defaults = DEFAULT_LINES[dataset].filter(column => numbers.includes(column))
    const x = timestamps[timestamps.length - 1] ?? ''

    return {
        id:     crypto.randomUUID(),
        x,
        y:      defaults.length > 0 ? defaults : numbers.slice(0, 1),
        latest: timestamps.find(column => column !== x) ?? null,
    }
}

/** The chart's lines from a preview: its rows (newest first) kept to the newest `latest`, oldest first along `x`. */
export function toSeries(chart: ChartSpec, rows: Dataset.Preview.Row[]): Series[] {
    let kept = rows

    if (chart.latest !== null && rows.length > 0) {
        const newest = rows[0][chart.latest]

        kept = rows.filter(row => row[chart.latest!] === newest)
    }

    return chart.y.map((column, index) => {
        const points: Point[] = []

        for (const row of kept) {
            const at = row[chart.x]
            const value = row[column]

            if (typeof at === 'string' && typeof value === 'number' && Number.isFinite(value))
                points.push({ t: Date.parse(at), v: value })
        }

        points.sort((a, b) => a.t - b.t)

        return { column, color: SERIES_COLORS[index], points }
    })
}

/** The point nearest `t` (points sorted by time), or null when there are none. */
export function nearest(points: Point[], t: number): Point | null {
    if (points.length === 0)
        return null

    let low = 0
    let high = points.length - 1

    while (high - low > 1) {
        const middle = (low + high) >> 1

        if (points[middle].t < t)
            low = middle
        else
            high = middle
    }

    return Math.abs(points[low].t - t) <= Math.abs(points[high].t - t) ? points[low] : points[high]
}

/** About `count` round values covering [min, max]: 0, 0.25, 0.5… or −50, 0, 50, 100. */
export function niceTicks(min: number, max: number, count = 5): number[] {
    if (min === max) {
        min -= 1
        max += 1
    }

    const raw = (max - min) / count
    const magnitude = 10 ** Math.floor(Math.log10(raw))
    const step = [1, 2, 2.5, 5, 10].map(factor => factor * magnitude).find(candidate => candidate >= raw) ?? raw
    const first = Math.floor(min / step)
    const last = Math.ceil(max / step)

    return Array.from({ length: last - first + 1 }, (_, index) => Number(((first + index) * step).toFixed(10)))
}

const HOUR_MS = 60 * 60_000
const DAY_MS = 24 * HOUR_MS

/** Local midnights across [start, end], every 1, 2, 7 or 14 days so that about eight fit; every 6 hours for under two days. */
export function timeTicks(start: number, end: number): number[] {
    const span = end - start

    if (span <= 2 * DAY_MS) {
        const ticks: number[] = []

        for (let tick = Math.ceil(start / (6 * HOUR_MS)) * 6 * HOUR_MS; tick <= end; tick += 6 * HOUR_MS)
            ticks.push(tick)

        return ticks
    }

    const every = [1, 2, 7, 14].find(days => span / (days * DAY_MS) <= 8) ?? 28
    const ticks: number[] = []
    let day = Time.Local.of(new Date(start)).day
    let index = 0

    while (true) {
        const midnight = Time.Local.startOfDay(day).getTime()

        if (midnight > end)
            break

        if (midnight >= start && index % every === 0)
            ticks.push(midnight)

        if (midnight >= start)
            index++

        day = new Date(Date.parse(`${day}T12:00:00Z`) + DAY_MS).toISOString().slice(0, 10)
    }

    return ticks
}

/** Whether the axis labels days (`Sat 16 May`) or hours (`Sat 16 May, 18:00`). */
export const isShortSpan = (start: number, end: number) => end - start <= 2 * DAY_MS

const VALUE = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 })
const SMALL_VALUE = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 3 })

/** `111.79`, `0.873`, `1,250` */
export const formatValue = (value: number) => (Math.abs(value) < 1 ? SMALL_VALUE : VALUE).format(value)
