import { z } from "zod"
import { Name as DatasetName } from "../Dataset/Name"
import { Name } from "./Name"
import { Schedule } from "./Schedule"

/**
 * A pipeline as Python defines it (`gridsense.pipelines`): what it does, the datasets it appends to, and the cron it
 * suggests. The PipelineRunner reads these from Python and syncs them to the server; when it runs is the Schedule's.
 */
export const Schema = z.object({
    name:        Name,
    description: z.string(),
    outputs:     DatasetName.array(),
    defaultCron: Schedule.Cron,
})

export type Pipeline = z.infer<typeof Schema>
