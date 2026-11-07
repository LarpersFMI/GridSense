import { z } from "zod"
import * as Ids from "../ids"
import { Name } from "./Name"

/** One run of a pipeline: started by its schedule or by someone's "Run now", as a Python subprocess. */
export namespace Run {

    export import Id       = Ids.PipelineRunId
    export import createId = Ids.createPipelineRunId

    export const Cause = z.enum(["schedule", "manual"])
    export type  Cause = z.infer<typeof Cause>

    export const Status = z.enum(["running", "succeeded", "failed"])
    export type  Status = z.infer<typeof Status>

    export const Schema = z.object({
        id:           Id,
        pipeline:     Name,
        cause:        Cause,
        status:       Status,
        startedAt:    z.coerce.date(),
        finishedAt:   z.coerce.date().nullable(),
        rowsAppended: z.record(z.string(), z.number().int().nonnegative()).nullable(),   // by dataset, once finished
        error:        z.string().nullable(),
    })
}
export type Run = z.infer<typeof Run.Schema>
