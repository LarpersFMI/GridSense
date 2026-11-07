import { z } from "zod"
import * as Ids from "../ids"

/** One run of the Forecaster: issued daily at 10:00 local time, it writes one Predictions row per hour of D+1…D+7. */
export namespace Run {

    export import Id = Ids.RunId
    export import createId = Ids.createRunId

    export const Schema = z.object({
        id:              Id,
        issueTs:         z.coerce.date(),           // the issue_ts of its rows in Dataset.Predictions
        modelVersion:    z.string().min(1),
        rows:            z.number().int().positive(),
        predictionsPath: z.string().min(1),
        reportedAt:      z.coerce.date(),
    })

    /** What the Python pipeline reports once the run's rows are fully written (POST /internal/runs). */
    export namespace Report {

        export const Schema = Run.Schema.omit({ id: true, reportedAt: true }).extend({
            start: z.coerce.date(),                 // the first target hour it forecast
            end:   z.coerce.date(),                 // the hour after its last: the predictions update is [start, end)
        })
    }
    export type Report = z.infer<typeof Report.Schema>
}
export type Run = z.infer<typeof Run.Schema>
