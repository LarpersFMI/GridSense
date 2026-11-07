import { z } from "zod"
import { Dataset } from "../Dataset"
import type { Check } from "./Check"

/**
 * A test on one hour: one dataset's column against a value. Columns aren't known here — the UI reads them from
 * `Dataset.API.describe` — so a condition on a column the hour doesn't have, or of the wrong type, doesn't hold.
 */
export namespace Condition {

    export const Operator = z.enum([">=", "<=", ">", "<", "==", "!=", "between", "in"])
    export type  Operator = z.infer<typeof Operator>

    /** `between` takes [low, high], both included; `in` takes a list; `>=` `<=` `>` `<` a number. */
    export const Value = z.union([
        z.number(),
        z.string(),
        z.tuple([z.number(), z.number()]),
        z.array(z.union([z.number(), z.string()])).min(1),
    ])
    export type  Value = z.infer<typeof Value>

    /** How a trigger's conditions combine on an hour: `all` must hold, or `any` one is enough. */
    export const Match = z.enum(["all", "any"])
    export type  Match = z.infer<typeof Match>

    export const Schema = z.object({
        dataset:  Dataset.Name,
        column:   z.string().min(1),
        operator: Operator,
        value:    Value,
    })

    /** What's wrong with the value for its operator, or null. */
    export function getProblem(condition: Condition): string | null {
        const { operator, value } = condition

        if (operator === "between") {
            const isPair = Array.isArray(value) && value.length === 2 && typeof value[0] === "number" && typeof value[1] === "number"

            if (!isPair)
                return "between takes [low, high]"

            return null
        }

        if (operator === "in") {
            if (!Array.isArray(value))
                return "in takes a list"

            return null
        }

        if (Array.isArray(value))
            return `${operator} takes one value`

        if (operator !== "==" && operator !== "!=" && typeof value !== "number")
            return `${operator} takes a number`

        return null
    }

    export function matches(condition: Condition, hour: Check.Hour): boolean {
        const value = hour.values[condition.dataset]?.[condition.column]

        if (value === undefined)
            return false

        switch (condition.operator) {
            case "==":
                return value === condition.value

            case "!=":
                return value !== condition.value

            case "in":
                return (condition.value as (number | string)[]).includes(value)

            case "between": {
                const [low, high] = condition.value as [number, number]

                return typeof value === "number" && value >= low && value <= high
            }
        }

        if (typeof value !== "number")
            return false

        const threshold = condition.value as number

        switch (condition.operator) {
            case ">=":
                return value >= threshold

            case "<=":
                return value <= threshold

            case ">":
                return value > threshold

            case "<":
                return value < threshold
        }
    }

    /** Whether an hour matches the conditions combined as `match` says. Without conditions, every hour does. */
    export function matchAll(conditions: Condition[], match: Match, hour: Check.Hour): boolean {
        if (conditions.length === 0)
            return true

        for (const condition of conditions) {
            const holds = matches(condition, hour)

            if (match === "all" && !holds)
                return false

            if (match === "any" && holds)
                return true
        }

        return match === "all"
    }
}
export type Condition = z.infer<typeof Condition.Schema>
