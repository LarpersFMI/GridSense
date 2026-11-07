import { z } from "zod"

/**
 * The Forecaster's output: one row per run and forecast hour. Mirrors `PREDICTIONS` in
 * src/gridsense/schemas.py, so columns keep their parquet names — change both together.
 */
export namespace Predictions {

    export const FILE = "predictions.parquet"

    /** `degraded`: an input was missing and a fallback was used · `failed`: input checks failed. */
    export const DataQuality = z.enum(["ok", "degraded", "failed"])
    export type  DataQuality = z.infer<typeof DataQuality>

    export namespace Row {

        export const Schema = z.object({
            issue_ts:      z.coerce.date(),                    // the run that forecast it
            target_ts_utc: z.coerce.date(),                    // the hour forecast
            horizon_days:  z.number().int().min(1).max(7),
            p_cheap:       z.number().min(0).max(1),           // P(price ≤ 0 €/MWh)
            p_near_zero:   z.number().min(0).max(1),           // P(price ≤ 20 €/MWh), the primary label
            price_p10:     z.number(),
            price_p50:     z.number(),
            price_p90:     z.number(),
            data_quality:  DataQuality,
            top_features:  z.string(),                         // "ghi_forecast:+0.24; off_day:+0.20; …"
        })
    }
    export type Row = z.infer<typeof Row.Schema>
}
