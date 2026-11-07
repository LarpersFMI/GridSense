import { z } from "zod"

/**
 * Cleared day-ahead prices, one row per delivery hour (the hourly mean of its 15-minute prices).
 * Mirrors `PRICES_HOURLY` in src/gridsense/schemas.py, so columns keep their parquet names — change both together.
 */
export namespace PricesHourly {

    export const FILE = "prices_hourly.parquet"

    export namespace Row {

        export const Schema = z.object({
            ts_utc:     z.coerce.date(),
            price_mean: z.number(),
            price_min:  z.number(),
            price_max:  z.number(),
        })
    }
    export type Row = z.infer<typeof Row.Schema>
}
