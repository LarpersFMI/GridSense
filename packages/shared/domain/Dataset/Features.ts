import { z } from "zod"

/**
 * What the model read for each hour it forecast: the training table's row for that issue and hour, as known at 10:00
 * on the issue day — prices so far, the weather forecast, the calendar, yesterday's load. Written by the `forecast`
 * pipeline next to the predictions, same key. Feature names lose their `f_` prefix (as in `top_features`); the labels
 * (the real price) are left out: they weren't known then. Loose: every feature passes through.
 */
export namespace Features {

    export const FILE = "features.parquet"

    export namespace Row {

        export const Schema = z.looseObject({
            issue_ts:      z.coerce.date(),
            target_ts_utc: z.coerce.date(),
            horizon_days:  z.number().int().min(1).max(7),
        })
    }
    export type Row = z.infer<typeof Row.Schema>
}
