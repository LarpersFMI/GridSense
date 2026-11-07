import { z } from "zod"
import { Name } from "./Name"

/** A dataset as its file holds it now: its columns and their types. What the UI builds condition editors from. */
export namespace Description {

    /** How a column compares: a number with every operator, text with ==, != and in. Timestamps and the rest aren't compared. */
    export const ColumnType = z.enum(["number", "text", "timestamp", "boolean", "other"])
    export type  ColumnType = z.infer<typeof ColumnType>

    export namespace Column {

        export const Schema = z.object({
            name:     z.string(),
            type:     ColumnType,
            computed: z.boolean(),                         // added by the Watchdog per hour, not in the file
        })
    }
    export type Column = z.infer<typeof Column.Schema>

    export const Schema = z.object({
        name:    Name,
        columns: Column.Schema.array(),
    })
}
export type Description = z.infer<typeof Description.Schema>
