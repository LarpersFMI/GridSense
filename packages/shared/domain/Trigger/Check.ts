import { z } from "zod"
import type { Dataset } from "../Dataset"
import { Name } from "../Dataset/Name"
import type { RunId } from "../ids"

/** One check of the triggers: why the Watchdog checked, on which run, and the hours it read. */
export namespace Check {

    /**
     * New rows in the trigger's dataset — those whose incremental column is past `after` (the watermark; null the
     * first time) up to `upTo`, the new watermark — or the trigger's schedule fired.
     */
    export const Cause = z.discriminatedUnion("type", [
        z.object({
            type:              z.literal("dataset"),
            dataset:           Name,
            incrementalColumn: z.string(),
            after:             z.coerce.date().nullable(),
            upTo:              z.coerce.date(),
        }),
        z.object({ type: z.literal("schedule"), firedAt: z.coerce.date() }),
    ])
    export type Cause = z.infer<typeof Cause>

    /** One hour, with each dataset's values for it — its file's columns and the computed ones. A dataset without a row for it is absent. */
    export interface Hour {
        at:     Date
        values: Partial<Record<Dataset.Name, Record<string, number | string>>>
    }

    /** A dataset row's values as an hour holds them: its number and text columns, then the computed ones. Timestamps stay out. */
    export function toValues(row: object, computed: Record<string, number>): Record<string, number | string> {
        const values: Record<string, number | string> = {}

        for (const [column, value] of Object.entries(row)) {
            if (typeof value === "number" || typeof value === "string")
                values[column] = value
        }

        for (const [column, value] of Object.entries(computed))
            values[column] = value

        return values
    }
}

export interface Check {
    cause: Check.Cause
    runId: RunId | null              // the run the hours' forecast came from; null on the clock, or without one
    hours: Check.Hour[]               // none on the clock
}
