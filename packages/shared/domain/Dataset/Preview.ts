import { z } from "zod"
import { Description } from "./Description"

/**
 * A dataset's latest rows as its file holds them, for the dataset viewer: newest first by `orderBy` (a timestamp
 * column), then by the file's other timestamps. Only the file's columns — the computed ones exist per hour, in the
 * Watchdog.
 */
export namespace Preview {

    /** A cell as JSON carries it: timestamps as ISO strings. */
    export const Cell = z.union([z.string(), z.number(), z.boolean(), z.null()])
    export type  Cell = z.infer<typeof Cell>

    export const Row = z.record(z.string(), Cell)
    export type  Row = z.infer<typeof Row>

    export const Schema = z.object({
        columns: Description.Column.Schema.array(),
        rows:    Row.array(),
        orderBy: z.string(),
        total:   z.number().int().nonnegative(),          // rows in the file
    })
}
export type Preview = z.infer<typeof Preview.Schema>
