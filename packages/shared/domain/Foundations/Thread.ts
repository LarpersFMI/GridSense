import { z } from "zod"

/**
 * One piece of work the agent carries from a hit to its outcome, across a pause for review. Its id is
 * both the BullMQ job's and the LangGraph thread's. Deterministic, not a UUID: the same hit reported
 * twice gets the same id, so it's handled once.
 */
export namespace Thread {

    export const Id = z.string().min(1).brand("Foundations.Thread.Id")
    export type  Id = z.infer<typeof Id>
}
