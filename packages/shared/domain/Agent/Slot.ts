import { z } from "zod"
import { Foundations } from "../Foundations"
import { Decision } from "./Decision"

/**
 * Zero-cost hours the agent announced to customers, by window key: a later hit on the same hours (the auction
 * confirming them, a forecast miss cancelling them) finds it here.
 */
export namespace Slot {

    export const Status = z.enum(["announced", "confirmed", "cancelled"])
    export type  Status = z.infer<typeof Status>

    export const Schema = z.object({
        key:       z.string(),
        start:     z.coerce.date(),
        end:       z.coerce.date(),
        label:     Decision.Label.extract(["confirmed", "likely", "possible"]),
        status:    Status,
        threadIds: Foundations.Thread.Id.array(),
        reason:    z.string(),
        updatedAt: z.coerce.date(),
    })
}
export type Slot = z.infer<typeof Slot.Schema>
