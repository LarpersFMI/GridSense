import { z } from "zod"
import { Name } from "../Dataset/Name"

/** When the Watchdog checks a trigger: when a dataset's hours change, or on a five-field cron (Romanian time). */
export namespace On {

    export const Schema = z.discriminatedUnion("type", [
        z.object({ type: z.literal("dataset"),  dataset: Name }),
        z.object({ type: z.literal("schedule"), cron:    z.string().regex(/^\S+(\s+\S+){4}$/, "A cron pattern has five fields") }),
    ])
}
export type On = z.infer<typeof On.Schema>
