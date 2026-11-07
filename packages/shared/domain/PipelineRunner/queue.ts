import { z } from "zod"
import { Foundations } from "../Foundations"
import { Name } from "../Pipeline/Name"
import { Run } from "../Pipeline/Run"

/** The PipelineRunner's queues. Its own job schedulers fire runs; the server queues "Run now" and reconciles. */
export namespace Queue {

    /** Run a pipeline: a Python subprocess, its log live, its end reported. One BullMQ job scheduler per enabled schedule. */
    export namespace RunPipeline {

        export const Job = z.object({
            pipeline: Name,
            cause:    Run.Cause,
        })
        export type Job = z.infer<typeof Job>

        export const Result = z.object({ status: Run.Status })
        export type  Result = z.infer<typeof Result>

        export const Definition = Foundations.Queue.define({
            name:    "pipeline-runner.run-pipeline",
            job:     Job,
            result:  Result,
            options: { removeOnComplete: 500, removeOnFail: 500 },
        })
    }

    /** Bring the job schedulers in line with the schedules: after one is set from the UI, and on boot. */
    export namespace Reconcile {

        export const Result = z.object({ schedules: z.number().int().nonnegative() })
        export type  Result = z.infer<typeof Result>

        export const Definition = Foundations.Queue.define({
            name:    "pipeline-runner.reconcile-schedules",
            job:     z.object({}),
            result:  Result,
            options: { removeOnComplete: 100, removeOnFail: 100 },
        })
    }
}
