import { z } from "zod"

/**
 * The agent's impact analysis of a decision, for the operator who approves it (or reads why it was taken alone):
 * what it recommends and why, what it touches, what could go wrong, and what it couldn't check. Every number in it
 * comes from the agent's tools — the model's forecast, what it read, the cleared prices — never from the LLM, which
 * only writes it up; without one, the template does.
 */
export namespace Analysis {

    export const Impact = z.object({
        customers:  z.number().int().nullable(),        // customers the slot would reach (pilot assumption)
        shiftedMwh: z.number().nullable(),              // consumption moved into the slot (pilot assumption)
        valueEur:   z.number().nullable(),              // shiftedMwh × (evening P50 − slot P50)
        basis:      z.string(),                         // the assumptions, stated
    })
    export type Impact = z.infer<typeof Impact>

    export const Schema = z.object({
        recommendation: z.string(),
        why:            z.string().array(),             // each with the figure and where it comes from
        impact:         Impact,
        risks:          z.string().array(),
        unverified:     z.string().array(),             // what the agent couldn't check
        writtenBy:      z.enum(["llm", "template"]),
        at:             z.coerce.date(),
    })
}
export type Analysis = z.infer<typeof Analysis.Schema>
