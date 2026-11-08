import { z } from "zod"

/**
 * What the agent's `decide` node made of a hit: deterministic, from the model's numbers in the hit's evidence —
 * never from the LLM. `rule` names the rule that decided, `inputs` the numbers it read.
 */
export namespace Decision {

    /**
     * Free hours — confirmed (the auction cleared them), likely or possible (forecast, by confidence) — or cancel
     * (announced hours that no longer hold), alert (tell a team), none (nothing to do).
     */
    export const Label = z.enum(["confirmed", "likely", "possible", "cancel", "alert", "none"])
    export type  Label = z.infer<typeof Label>

    export const Schema = z.object({
        label:            Label,
        confidence:       z.number().min(0).max(1).nullable(),
        expectedValueEur: z.number().nullable(),
        needsReview:      z.boolean(),
        rule:             z.string(),
        reason:           z.string(),
        inputs:           z.record(z.string(), z.number()),
    })
}
export type Decision = z.infer<typeof Decision.Schema>
