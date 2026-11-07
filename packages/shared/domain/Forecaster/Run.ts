import { z } from "zod"
import { Foundations } from "../Foundations"

/** One run of the Forecaster: issued daily at 10:00 local time, it writes one Predictions row per hour of D+1…D+7. */
export namespace Run {

    export const Id = Foundations.Id.define("Forecaster.Run.Id")
    export type  Id = z.infer<typeof Id>
    export const createId = () => Foundations.uuidv7() as Id

    /** What the Python pipeline reports once the run's rows are fully written (POST /internal/runs). */
    export namespace Report {

        export const Schema = z.object({
            issueTs:         z.coerce.date(),           // the issue_ts of its rows in Dataset.Predictions
            modelVersion:    z.string().min(1),
            rows:            z.number().int().positive(),
            predictionsPath: z.string().min(1),
        })
    }
    export type Report = z.infer<typeof Report.Schema>

    export const Schema = Report.Schema.extend({
        id:         Id,
        reportedAt: z.coerce.date(),
    })
}
export type Run = z.infer<typeof Run.Schema>
