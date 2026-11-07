import { z } from "zod"
import { Name } from "../Dataset/Name"

/**
 * When the Watchdog checks a trigger: when its dataset updates, or on a five-field cron (Romanian time). On a dataset,
 * the trigger reads the rows past its watermark on `incrementalColumn` — a timestamp column that only grows as rows are
 * appended: `issue_ts` for the predictions (a run's rows), `ts_utc` for the prices (a cleared day's hours).
 */
export namespace On {

    export const Schema = z.discriminatedUnion("type", [
        z.object({ type: z.literal("dataset"),  dataset: Name, incrementalColumn: z.string().min(1) }),
        z.object({ type: z.literal("schedule"), cron:    z.string().regex(/^\S+(\s+\S+){4}$/, "A cron pattern has five fields") }),
    ])
}
export type On = z.infer<typeof On.Schema>
