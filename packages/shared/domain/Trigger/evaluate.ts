import { Check } from "./Check"
import { Condition } from "./Condition"
import { Grouping } from "./Grouping"
import { Hit } from "./Hit"
import type { Trigger } from "./Schema"

/** The hits a trigger makes in a check: none when no hour matches. On the clock, without hours, it holds once. */
export function evaluate(trigger: Trigger, check: Check): Hit[] {
    if (trigger.on.type === "schedule")
        return [{
            triggerId:    trigger.id,
            cause:        check.cause,
            runId:        check.runId,
            window:       null,
            matchedHours: 0,
            evidence:     {},
        }]

    const matched: Check.Hour[] = []

    for (const hour of check.hours)
        if (Condition.matchAll(trigger.conditions, trigger.match, hour))
            matched.push(hour)

    if (matched.length === 0)
        return []

    const hits: Hit[] = []

    for (const group of Grouping.split(trigger.grouping, matched))
        hits.push({
            triggerId:    trigger.id,
            cause:        check.cause,
            runId:        check.runId,
            window:       group.window,
            matchedHours: group.hours.length,
            evidence:     Hit.summarize(trigger.conditions, group.hours),
        })

    return hits
}
