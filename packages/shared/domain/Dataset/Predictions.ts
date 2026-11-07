import { z } from "zod"
import { Local } from "../Time/Local"

/**
 * The Forecaster's output: one row per run and forecast hour. Mirrors `PREDICTIONS` in src/gridsense/schemas.py,
 * so columns keep their parquet names — change both together. Loose: a column the file adds passes through.
 */
export namespace Predictions {

    export const FILE = "predictions.parquet"

    /** `degraded`: an input was missing and a fallback was used · `failed`: input checks failed. */
    export const DataQuality = z.enum(["ok", "degraded", "failed"])
    export type  DataQuality = z.infer<typeof DataQuality>

    export namespace Row {

        export const Schema = z.looseObject({
            issue_ts:      z.coerce.date(),                // the run that forecast it
            target_ts_utc: z.coerce.date(),                // the hour forecast
            horizon_days:  z.number().int().min(1).max(7),
            p_cheap:       z.number().min(0).max(1),       // P(price ≤ 0 €/MWh)
            p_near_zero:   z.number().min(0).max(1),       // P(price ≤ 20 €/MWh), the primary label
            price_p10:     z.number(),
            price_p50:     z.number(),
            price_p90:     z.number(),
            data_quality:  DataQuality,
            top_features:  z.string(),                     // "ghi_forecast:+0.24; off_day:+0.20; …"
            model_name:    z.string().optional(),          // absent in files written before the column existed
            model_version: z.string().optional(),
        })
    }
    export type Row = z.infer<typeof Row.Schema>

    /**
     * Columns the Watchdog computes per hour, on top of the file's: local_hour and weekday (0 = Monday) in
     * Romanian time, interval_width (P90 − P10), and p_near_zero_change against the run before.
     */
    export const COMPUTED_COLUMNS = ["local_hour", "weekday", "interval_width", "p_near_zero_change"] as const

    /** The computed columns' values for a row; `previous` is the same hour in the run before — without it there's no change. */
    export function compute(row: Row, previous: Row | null): Record<string, number> {
        const local = Local.of(row.target_ts_utc)

        const values: Record<string, number> = {
            local_hour:     local.hour,
            weekday:        Local.getWeekday(local.day),
            interval_width: row.price_p90 - row.price_p10,
        }

        if (previous !== null)
            values.p_near_zero_change = row.p_near_zero - previous.p_near_zero

        return values
    }
}
