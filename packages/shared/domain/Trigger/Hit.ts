import { z } from "zod"
import { Update } from "../Dataset/Update"
import { RunId, TriggerId, type ThreadId } from "../ids"
import { Window } from "../Time/Window"
import { Check } from "./Check"
import type { Condition } from "./Condition"

/**
 * What the Watchdog hands the agent: which trigger held, on what, and what the matching hours looked like.
 * Evidence is `<dataset>.<column>.min / .mean / .max` for each number column the conditions read, and
 * `<dataset>.<column>=<value>` counts for each text one.
 */
export namespace Hit {

    export const Schema = z.object({
        triggerId:    TriggerId,
        cause:        Check.Cause,
        runId:        RunId.nullable(),
        window:       Window.Schema.nullable(),        // null for `run` grouping and triggers without hours
        matchedHours: z.number().int().nonnegative(),
        evidence:     z.record(z.string(), z.number()),
    })

    /** The matching hours, summarized on the columns the conditions read. */
    export function summarize(conditions: Condition[], hours: Check.Hour[]): Record<string, number> {
        const evidence: Record<string, number> = {}

        // One entry per dataset and column, however many conditions read it.
        const read: Record<string, Condition> = {}

        for (const condition of conditions)
            read[`${condition.dataset}.${condition.column}`] = condition

        for (const [name, condition] of Object.entries(read)) {
            let min = Infinity
            let max = -Infinity
            let sum = 0
            let count = 0

            for (const hour of hours) {
                const value = hour.values[condition.dataset]?.[condition.column]

                if (typeof value === "number") {
                    min = Math.min(min, value)
                    max = Math.max(max, value)
                    sum += value
                    count += 1
                }
                else if (typeof value === "string") {
                    const key = `${name}=${value}`

                    if (!(key in evidence))
                        evidence[key] = 0

                    evidence[key] += 1
                }
            }

            if (count > 0) {
                evidence[`${name}.min`] = min
                evidence[`${name}.mean`] = sum / count
                evidence[`${name}.max`] = max
            }
        }

        return evidence
    }

    /** The same window of the same trigger hits at most once per cooldown. */
    export function getCooldownKey(hit: Hit): string {
        let subject = "run"

        if (hit.window !== null)
            subject = hit.window.key

        return `${hit.triggerId}_${subject}`
    }

    /**
     * The hit's thread: one per trigger, window and occasion — the dataset update (`Dataset.Update.getKey`) or the
     * schedule's firing — so the same hit reported twice is handled once.
     */
    export function getThreadId(hit: Hit): ThreadId {
        let occasion: string

        if (hit.cause.type === "dataset")
            occasion = Update.getKey(hit.cause.update)
        else
            occasion = `schedule-${hit.cause.firedAt.getTime()}`

        return `${getCooldownKey(hit)}_${occasion}` as ThreadId
    }
}
export type Hit = z.infer<typeof Hit.Schema>
