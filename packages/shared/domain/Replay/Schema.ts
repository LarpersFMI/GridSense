import { z } from "zod"

/** A local calendar day, `2025-04-24`, in Romanian time. */
export const LocalDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "A day as YYYY-MM-DD")
export type  LocalDate = z.infer<typeof LocalDate>

/**
 * The replay: the real models run day by day over a past period (`gridsense.pipelines.replay`). `forecast` issues the
 * next day at 10:00, `prices` clears it; `start` is the first issue day. Set from the UI, one for the whole app.
 */
export const Schema = z.object({
    start: LocalDate,
})
export type Replay = z.infer<typeof Schema>

/** Where the replay may start: validation (Mar – Sep 2025); with ALLOW_TEST_REPLAY, also the test split, once evaluated. */
export const RANGES = {
    validation: { from: "2025-03-01", to: "2025-09-30" },
    test:       { from: "2026-03-01", to: "2026-10-31" },
} as const

/** Where it is: the last day issued (forecast) and the last day cleared (prices), from the dataset files. */
export const State = Schema.extend({
    issued:  LocalDate.nullable(),
    cleared: LocalDate.nullable(),
    range:   z.object({ from: LocalDate, to: LocalDate }),
})
export type State = z.infer<typeof State>
