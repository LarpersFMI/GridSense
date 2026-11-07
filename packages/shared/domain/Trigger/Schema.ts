import { z } from "zod"
import { TriggerId } from "../ids"
import { Condition } from "./Condition"
import { Grouping } from "./Grouping"
import { On } from "./On"

/**
 * A trigger as an admin writes it and the server stores it. Its id is made where it's written (`Trigger.createId()`,
 * in the browser), so create and update both carry the whole trigger.
 */
export const Schema = z.object({
    id:              TriggerId,
    name:            z.string().min(1),
    description:     z.string(),                       // tells the agent what the admin meant
    enabled:         z.boolean(),
    on:              On.Schema,
    match:           Condition.Match,
    conditions:      Condition.Schema.array(),
    grouping:        Grouping.Schema,
    cooldownMinutes: z.number().int().nonnegative(),   // after a hit, the same window can't hit again for this long
}).superRefine((trigger, context) => {
    if (trigger.on.type === "schedule" && trigger.conditions.length > 0)
        context.addIssue({
            code:    "custom",
            path:    ["conditions"],
            message: "A trigger on the clock has no hours to test: leave its conditions empty",
        })

    if (trigger.grouping.type === "window" && trigger.grouping.minHours > trigger.grouping.maxHours)
        context.addIssue({
            code:    "custom",
            path:    ["grouping", "minHours"],
            message: "minHours can't exceed maxHours",
        })

    for (let i = 0; i < trigger.conditions.length; i++) {
        const problem = Condition.getProblem(trigger.conditions[i])

        if (problem !== null)
            context.addIssue({
                code:    "custom",
                path:    ["conditions", i],
                message: problem,
            })
    }
})

export type Trigger = z.infer<typeof Schema>
