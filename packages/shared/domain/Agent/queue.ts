import { z } from "zod"
import { Foundations } from "../Foundations"
import { Trigger } from "../Trigger/Trigger"

/** The agent's queues: the Watchdog hands it hits; the server hands it an admin's review. */
export namespace Queue {

    /** `acted`: it carried out its actions · `awaiting-review`: paused for an admin · `dismissed`: nothing to do. */
    export const Outcome = z.enum(["acted", "awaiting-review", "dismissed"])
    export type  Outcome = z.infer<typeof Outcome>

    export const Result = z.object({ outcome: Outcome })
    export type  Result = z.infer<typeof Result>

    /** Decide and act on one hit. Its job id is the hit's `Foundations.Thread.Id` (`Trigger.Hit.getThreadId`). */
    export namespace HandleHit {

        export const Definition = Foundations.Queue.define({
            name:    "agent.handle-hit",
            job:     Trigger.Hit.Schema,
            result:  Result,
            options: { removeOnComplete: 1000, removeOnFail: 1000 },
        })
    }

    /** Resume a hit paused for review with the admin's decision. */
    export namespace Resume {

        export const Decision = z.enum(["approve", "reject"])
        export type  Decision = z.infer<typeof Decision>

        export const Job = z.object({
            threadId: Foundations.Thread.Id,
            decision: Decision,
            note:     z.string().nullable(),
        })
        export type Job = z.infer<typeof Job>

        export const Definition = Foundations.Queue.define({
            name:    "agent.resume",
            job:     Job,
            result:  Result,
            options: { removeOnComplete: 1000, removeOnFail: 1000 },
        })
    }
}
