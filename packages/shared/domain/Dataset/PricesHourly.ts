import { z } from "zod"
import { Local } from "../Time/Local"

/**
 * Cleared day-ahead prices, one row per delivery hour (the hourly mean of its 15-minute prices). Mirrors
 * `PRICES_HOURLY` in src/gridsense/schemas.py — change both together. Loose: a column the file adds passes through.
 */
export namespace PricesHourly {

    export const FILE = "prices_hourly.parquet"

    export namespace Row {

        export const Schema = z.looseObject({
            ts_utc:     z.coerce.date(),
            price_mean: z.number(),
            price_min:  z.number(),
            price_max:  z.number(),
        })
    }
    export type Row = z.infer<typeof Row.Schema>

    /** Columns the Watchdog computes per hour: local_hour and weekday (0 = Monday) in Romanian time. */
    export const COMPUTED_COLUMNS = ["local_hour", "weekday"] as const

    export function compute(row: Row): Record<string, number> {
        const local = Local.of(row.ts_utc)

        return {
            local_hour: local.hour,
            weekday:    Local.getWeekday(local.day),
        }
    }
}
