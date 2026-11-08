import { z } from "zod"

/**
 * One turn of the conversation on a thread: the operator's question, or the agent's answer — written by Claude from
 * what its read-only tools found (`tools`: the ones it consulted). Answers never change the decision.
 */
export namespace Message {

    export const Role = z.enum(["operator", "agent"])
    export type  Role = z.infer<typeof Role>

    export const Schema = z.object({
        role:      Role,
        text:      z.string(),
        at:        z.coerce.date(),
        tools:     z.string().array().default([]),            // an answer's: the tools it consulted, in order
        writtenBy: z.enum(["llm", "template"]).nullable(),   // an answer's; null for the operator's question
    })
}
export type Message = z.infer<typeof Message.Schema>
