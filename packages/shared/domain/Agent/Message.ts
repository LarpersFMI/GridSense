import { z } from "zod"

/**
 * One turn of the conversation on a thread: the operator's question, or the agent's answer — written by Claude from
 * what its read-only tools found (`tools`: the ones it consulted). Answers never change the decision.
 */
export namespace Message {

    /** One call the agent made to a read-only tool while answering: what it asked for, and what came back, in short. */
    export const ToolCall = z.object({
        name:    z.string(),                                 // the tool: get_forecast_history, get_daily_prices…
        input:   z.record(z.string(), z.unknown()),
        summary: z.string(),                                 // what it returned: "34 rows: 2 runs × 17 hours"
        at:      z.coerce.date(),
    })
    export type ToolCall = z.infer<typeof ToolCall>

    export const Role = z.enum(["operator", "agent"])
    export type  Role = z.infer<typeof Role>

    export const Schema = z.object({
        role:      Role,
        text:      z.string(),
        at:        z.coerce.date(),
        tools:     z.string().array().default([]),            // an answer's: the tools it consulted, in order
        calls:     ToolCall.array().default([]),             // an answer's: every tool call, in order
        writtenBy: z.enum(["llm", "template"]).nullable(),   // an answer's; null for the operator's question
    })
}
export type Message = z.infer<typeof Message.Schema>
