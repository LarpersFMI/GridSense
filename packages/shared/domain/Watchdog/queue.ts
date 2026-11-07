import { z } from "zod"
import { Dataset } from "../Dataset"
import { Foundations } from "../Foundations"
import { Trigger } from "../Trigger"

/** The Watchdog's queues. The server reports dataset updates and reconciles; BullMQ's job schedulers fire schedules. */
export namespace Queue {

    /** Hits raised by one check. */
    export const CheckResult = z.object({ hits: z.number().int().nonnegative() })
    export type  CheckResult = z.infer<typeof CheckResult>

    /** Check every enabled trigger on this dataset against its new rows. A repeated update finds none: no job id needed. */
    export namespace DatasetUpdated {

        export const Definition = Foundations.Queue.define({
            name:    "watchdog.dataset-updated",
            job:     Dataset.Update.Schema,
            result:  CheckResult,
            options: { removeOnComplete: 1000, removeOnFail: 1000 },
        })
    }

    /** A trigger's schedule fired. One BullMQ job scheduler per scheduled trigger, its id the trigger's id. */
    export namespace Schedule {

        export const Job = z.object({ triggerId: Trigger.Id })
        export type  Job = z.infer<typeof Job>

        export const Definition = Foundations.Queue.define({
            name:    "watchdog.schedule",
            job:     Job,
            result:  CheckResult,
            options: { removeOnComplete: 1000, removeOnFail: 1000 },
        })
    }

    /** Bring the job schedulers in line with the triggers: after an admin saves one, and on boot. */
    export namespace Reconcile {

        export const Result = z.object({ schedules: z.number().int().nonnegative() })
        export type  Result = z.infer<typeof Result>

        export const Definition = Foundations.Queue.define({
            name:    "watchdog.reconcile-schedules",
            job:     z.object({}),
            result:  Result,
            options: { removeOnComplete: 100, removeOnFail: 100 },
        })
    }
}
