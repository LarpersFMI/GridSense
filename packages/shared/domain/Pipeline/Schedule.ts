import { z } from "zod"
import { Name } from "./Name"

/**
 * When a pipeline runs: a five-field cron, Romanian time, set from the UI. A pipeline Python adds starts with its
 * default cron, disabled — nothing runs until someone switches it on.
 */
export namespace Schedule {

    export const Cron = z.string().regex(/^\S+(\s+\S+){4}$/, "A cron pattern has five fields")
    export type  Cron = z.infer<typeof Cron>

    export const Schema = z.object({
        pipeline: Name,
        cron:     Cron,
        enabled:  z.boolean(),
    })
}
export type Schedule = z.infer<typeof Schedule.Schema>
