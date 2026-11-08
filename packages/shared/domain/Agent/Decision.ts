import { z } from "zod"
import { Window } from "../Time/Window"

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
        needsReview:      z.boolean(),
        rule:             z.string(),
        reason:           z.string(),
        inputs:           z.record(z.string(), z.number()),

        // The hours the decision is about when they're narrower than the hit's: an announcement keeps only the stretch
        // sure enough to announce on its own. null: the hit's window.
        window:           Window.Schema.nullable().default(null),

        // Hours of the hit this decision leaves to their own threads, each decided on its own: the less sure hours
        // around an announced stretch, the hours a partly announced window still lacks.
        followUps:        Window.Schema.array().default([]),
    })
}
export type Decision = z.infer<typeof Decision.Schema>
