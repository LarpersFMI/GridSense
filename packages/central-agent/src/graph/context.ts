import { existsSync } from 'node:fs';
import { DuckDBInstance, type DuckDBConnection } from '@duckdb/node-api';
import { Time, type Trigger } from '@gridsense/shared/domain';
import { getDatasetPath, quoteSqlPath, toPlainRow } from '@gridsense/shared/server/datasets';

const HOUR_MS = 60 * 60_000;
const DAY_MS = 24 * HOUR_MS;

/** What the agent's tools found about a hit's hours: every number an impact analysis may use, and where it's from. */
export interface Context {

    /** The latest forecast of these hours: its issue, the probabilities and price range over them, the evening's P50. */
    forecast: {
        issuedAt:   string                  // `Thu 24 Apr, 10:00`
        horizon:    number                  // days ahead
        pMin:       number
        pMean:      number
        pCheapMean: number
        p10:        number                  // means over the window, EUR/MWh
        p50:        number
        p90:        number
        eveningP50: number | null           // 18:00–22:00 the same day
    } | null

    /** How the probability over these hours moved, one forecast after the other: the oldest first. */
    trajectory: { issuedAt: string; horizon: number; pMean: number }[]

    /** What the model read for these hours in that latest forecast (the features dataset). */
    inputs: {
        sunshine:       number | null       // ghi_mean, W/m²
        clouds:         number | null       // cloud_mean, %
        wind:           number | null       // wind100_mean, m/s
        holiday:        boolean
        weekend:        boolean
        negHours7d:     number | null       // negative-price hours the week before the issue
        missingWeather: number              // hours without a weather forecast
    } | null

    /** The auction's prices for these hours, once cleared. */
    cleared: { mean: number; max: number; hoursAbove20: number; hours: number } | null

    /** The week before: how many days had a midday (11–14) at or under 20 EUR/MWh. */
    recent: { days: number; cheapMiddays: number } | null
}

const ISSUED = new Intl.DateTimeFormat('en-GB', { timeZone: Time.Local.TIME_ZONE, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

let connection: Promise<DuckDBConnection> | undefined;

const connect = () => (connection ??= DuckDBInstance.create(':memory:').then((instance) => instance.connect()));

/** A dataset's rows for [from, to) on a timestamp column, as plain objects; none while its file doesn't exist. */
export async function read(name: 'predictions' | 'prices' | 'features', column: string, from: Date, to: Date): Promise<Record<string, unknown>[]> {
    const path = getDatasetPath(name);

    if (!existsSync(path))
        return [];

    const reader = await (await connect()).runAndReadAll(`
        select * from read_parquet(${quoteSqlPath(path)})
        where "${column}" >= $from::timestamptz and "${column}" < $to::timestamptz
        order by "${column}"
    `, { from: from.toISOString(), to: to.toISOString() });

    return reader.getRowObjectsJS().map(toPlainRow);
}

const mean = (values: number[]) => (values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length);
const numbers = (rows: Record<string, unknown>[], column: string) => rows.map((row) => row[column]).filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
const time = (value: unknown) => (value instanceof Date ? value.getTime() : Date.parse(String(value)));

/**
 * The agent's tools, run for one hit: the forecasts of its hours (latest and their trajectory), what the model read
 * for them, the cleared prices if the auction is in, and the week before. Read straight from the dataset files, as the
 * Watchdog does; nothing here is the LLM's.
 */
export async function gatherContext(hit: Trigger.Hit): Promise<Context> {
    const empty: Context = { forecast: null, trajectory: [], inputs: null, cleared: null, recent: null };

    if (hit.window === null)
        return empty;

    const { start, end } = hit.window;
    const predictions = await read('predictions', 'target_ts_utc', start, end);

    // Every forecast of these hours, by issue: the latest decides, the earlier ones show the trajectory.
    const byIssue = new Map<number, Record<string, unknown>[]>();

    for (const row of predictions) {
        const issue = time(row.issue_ts);

        byIssue.set(issue, [...(byIssue.get(issue) ?? []), row]);
    }

    const issues = [...byIssue.keys()].sort((a, b) => a - b);
    const trajectory = issues.map((issue) => {
        const rows = byIssue.get(issue)!;

        return { issuedAt: ISSUED.format(issue), horizon: Number(rows[0].horizon_days), pMean: mean(numbers(rows, 'p_near_zero')) };
    });

    let forecast: Context['forecast'] = null;
    let inputs: Context['inputs'] = null;

    if (issues.length > 0) {
        const latest = issues[issues.length - 1];
        const rows = byIssue.get(latest)!;

        // The same day's evening, 18:00–22:00 local: what the shifted consumption would otherwise cost.
        const day = Time.Local.of(start).day;
        const eveningStart = new Date(Time.Local.startOfDay(day).getTime() + 18 * HOUR_MS);
        const evening = (await read('predictions', 'target_ts_utc', eveningStart, new Date(eveningStart.getTime() + 4 * HOUR_MS)))
            .filter((row) => time(row.issue_ts) === latest);

        forecast = {
            issuedAt:   ISSUED.format(latest),
            horizon:    Number(rows[0].horizon_days),
            pMin:       Math.min(...numbers(rows, 'p_near_zero')),
            pMean:      mean(numbers(rows, 'p_near_zero')),
            pCheapMean: mean(numbers(rows, 'p_cheap')),
            p10:        mean(numbers(rows, 'price_p10')),
            p50:        mean(numbers(rows, 'price_p50')),
            p90:        mean(numbers(rows, 'price_p90')),
            eveningP50: evening.length > 0 ? mean(numbers(evening, 'price_p50')) : null,
        };

        const features = (await read('features', 'target_ts_utc', start, end)).filter((row) => time(row.issue_ts) === latest);

        if (features.length > 0) {
            const optional = (column: string) => (numbers(features, column).length > 0 ? mean(numbers(features, column)) : null);

            inputs = {
                sunshine:       optional('ghi_mean'),
                clouds:         optional('cloud_mean'),
                wind:           optional('wind100_mean'),
                holiday:        numbers(features, 'is_holiday').some((value) => value > 0),
                weekend:        numbers(features, 'is_weekend').some((value) => value > 0),
                negHours7d:     optional('neg_hours_7d'),
                missingWeather: features.filter((row) => row.data_quality !== 'ok').length,
            };
        }
    }

    const prices = await read('prices', 'ts_utc', start, end);
    const cleared = prices.length === 0 ? null : {
        mean:         mean(numbers(prices, 'price_mean')),
        max:          Math.max(...numbers(prices, 'price_mean')),
        hoursAbove20: numbers(prices, 'price_mean').filter((price) => price > 20).length,
        hours:        prices.length,
    };

    // The week before the window: on how many days did the midday clear near zero?
    const week = await read('prices', 'ts_utc', new Date(start.getTime() - 7 * DAY_MS), Time.Local.startOfDay(Time.Local.of(start).day));
    const middays = new Map<string, number[]>();

    for (const row of week) {
        const local = Time.Local.of(new Date(time(row.ts_utc)));

        if (local.hour >= 11 && local.hour < 15 && typeof row.price_mean === 'number')
            middays.set(local.day, [...(middays.get(local.day) ?? []), row.price_mean]);
    }

    const recent = middays.size === 0 ? null : {
        days:         middays.size,
        cheapMiddays: [...middays.values()].filter((values) => Math.min(...values) <= 20).length,
    };

    return { forecast, trajectory, inputs, cleared, recent };
}
