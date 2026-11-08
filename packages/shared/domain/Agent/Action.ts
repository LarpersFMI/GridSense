import { z } from "zod"

/** Something the agent did, or proposed and an admin turned down: a message to an audience, worded from the numbers. */
export namespace Action {

    export const Type = z.enum(["announce", "confirm", "cancel", "alert"])
    export type  Type = z.infer<typeof Type>

    export const Audience = z.enum(["customers", "trading-desk", "data-owner", "operator"])
    export type  Audience = z.infer<typeof Audience>

    export const Schema = z.object({
        type:     Type,
        audience: Audience,
        title:    z.string(),
        text:     z.string(),
        wordedBy: z.enum(["llm", "template"]),         // the LLM words it when one is set up; the template otherwise
        at:       z.coerce.date(),
    })
}
export type Action = z.infer<typeof Action.Schema>
