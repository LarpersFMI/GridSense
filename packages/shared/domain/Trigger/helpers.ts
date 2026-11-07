import type { z } from "zod"
import type { Foundations } from "../Foundations"
import type { Predictions } from "../Dataset/Predictions"
import type { PricesHourly } from "../Dataset/PricesHourly"
import { Local } from "../Time/Local"
import { Window } from "../Time/Window"
import { Trigger } from "./Trigger"

/** Rejects conditions the trigger's source can't answer, and values that don't fit their operator. */
export function checkTrigger(trigger: Trigger, context: z.RefinementCtx): void {
    const source = getSource(trigger)

    if (source === null && trigger.conditions.length > 0)
        context.addIssue({
            code:    "custom",
            path:    ["conditions"],
            message: "A trigger on the clock or on failed input checks has no rows to test: leave its conditions empty",
        })

    if (trigger.grouping.type === "window" && trigger.grouping.minHours > trigger.grouping.maxHours)
        context.addIssue({
            code:    "custom",
            path:    ["grouping", "minHours"],
            message: "minHours can't exceed maxHours",
        })

    if (source === null)
        return

    const columns = new Set(Trigger.COLUMNS_OF[source])

    for (let i = 0; i < trigger.conditions.length; i++) {
        const condition = trigger.conditions[i]
        const isText = Trigger.TEXT_COLUMNS.has(condition.column)
        let problem: string | null = null

        if (!columns.has(condition.column))
            problem = `${condition.column} isn't a column of ${source}`
        else if (isText && !Trigger.Condition.TEXT_OPERATORS.has(condition.operator))
            problem = `${condition.column} holds text: use ==, != or in`
        else if (condition.operator === "between" && !isPair(condition.value))
            problem = "between takes [low, high]"
        else if (condition.operator === "in" && !Array.isArray(condition.value))
            problem = "in takes a list"
        else if (condition.operator !== "between" && condition.operator !== "in" && Array.isArray(condition.value))
            problem = `${condition.operator} takes one value`
        else if (!isText && condition.operator !== "in" && condition.operator !== "between" && typeof condition.value !== "number")
            problem = `${condition.column} holds numbers`

        if (problem !== null)
            context.addIssue({
                code:    "custom",
                path:    ["conditions", i],
                message: problem,
            })
    }
}

const isPair = (value: Trigger.Condition.Value): value is [number, number] =>
    Array.isArray(value) && value.length === 2 && typeof value[0] === "number" && typeof value[1] === "number"

/** The rows the trigger's conditions read, or null when it runs on the clock or on a signal without rows. */
export function getSource(trigger: Pick<Trigger, "on">): Trigger.Source | null {
    if (trigger.on.type === "schedule")
        return null

    return Trigger.SOURCE_OF[trigger.on.signal]
}

/** False when the hour has no value in the column — p_near_zero_change on an hour's first forecast. */
export function matchesCondition(condition: Trigger.Condition, row: Trigger.Row): boolean {
    const value = row.values[condition.column]

    if (value === undefined)
        return false

    switch (condition.operator) {
        case ">=":
            return value >= condition.value

        case "<=":
            return value <= condition.value

        case ">":
            return value > condition.value

        case "<":
            return value < condition.value

        case "==":
            return value === condition.value

        case "!=":
            return value !== condition.value

        // checkTrigger only lets between onto number columns, with [low, high].
        case "between": {
            const [low, high] = condition.value as [number, number]

            return (value as number) >= low && (value as number) <= high
        }

        case "in":
            return (condition.value as (number | string)[]).includes(value)
    }
}

/** A prediction as a trigger reads it; `previous` is the same hour in the run before, if it forecast it. */
export function rowFromPrediction(prediction: Predictions.Row, previous: Predictions.Row | null): Trigger.Row {
    const local = Local.of(prediction.target_ts_utc)

    const values: Trigger.Row["values"] = {
        p_near_zero:    prediction.p_near_zero,
        p_cheap:        prediction.p_cheap,
        price_p10:      prediction.price_p10,
        price_p50:      prediction.price_p50,
        price_p90:      prediction.price_p90,
        interval_width: prediction.price_p90 - prediction.price_p10,
        horizon_days:   prediction.horizon_days,
        data_quality:   prediction.data_quality,
        local_hour:     local.hour,
        weekday:        Local.getWeekday(local.day),
    }

    if (previous !== null)
        values.p_near_zero_change = prediction.p_near_zero - previous.p_near_zero

    return {
        at: prediction.target_ts_utc,
        values,
    }
}

export function rowFromPrice(price: PricesHourly.Row): Trigger.Row {
    const local = Local.of(price.ts_utc)

    return {
        at:     price.ts_utc,
        values: {
            price_mean: price.price_mean,
            price_min:  price.price_min,
            price_max:  price.price_max,
            local_hour: local.hour,
            weekday:    Local.getWeekday(local.day),
        },
    }
}

/** For each number column the conditions read, its min, mean and max over the rows; for each text column, counts. */
function summarize(trigger: Trigger, rows: Trigger.Row[]): Record<string, number> {
    const evidence: Record<string, number> = {}
    const columns = new Set<Trigger.Column>()

    for (const condition of trigger.conditions)
        columns.add(condition.column)

    for (const column of columns) {
        if (Trigger.TEXT_COLUMNS.has(column)) {
            for (const row of rows) {
                const key = `${column}=${row.values[column]}`

                if (!(key in evidence))
                    evidence[key] = 0

                evidence[key] += 1
            }

            continue
        }

        let min = Infinity
        let max = -Infinity
        let sum = 0
        let count = 0

        for (const row of rows) {
            const value = row.values[column]

            if (typeof value !== "number")
                continue

            min = Math.min(min, value)
            max = Math.max(max, value)
            sum += value
            count += 1
        }

        evidence[`${column}.min`] = min
        evidence[`${column}.mean`] = sum / count
        evidence[`${column}.max`] = max
    }

    return evidence
}

function createHit(trigger: Trigger, context: Trigger.Context, rows: Trigger.Row[], window: Window | null): Trigger.Hit {
    return {
        triggerId:    trigger.id,
        cause:        context.cause,
        runId:        context.runId,
        window,
        matchedHours: rows.length,
        evidence:     summarize(trigger, rows),
    }
}

/** The hits a trigger makes in this context: none when no hour matches. A trigger without conditions matches every hour. */
export function evaluate(trigger: Trigger, context: Trigger.Context): Trigger.Hit[] {
    if (getSource(trigger) === null)
        return [createHit(trigger, context, [], null)]

    const matched: Trigger.Row[] = []

    for (const row of context.rows) {
        let matches = trigger.match === "all"

        for (const condition of trigger.conditions) {
            const holds = matchesCondition(condition, row)

            if (trigger.match === "all" && !holds)
                matches = false

            if (trigger.match === "any" && holds)
                matches = true
        }

        if (trigger.conditions.length === 0)
            matches = true

        if (matches)
            matched.push(row)
    }

    if (matched.length === 0)
        return []

    const hits: Trigger.Hit[] = []

    switch (trigger.grouping.type) {
        case "hour":
            for (const row of matched)
                hits.push(createHit(trigger, context, [row], Window.of([row])))

            break

        case "window":
            for (const rows of Window.group(matched, trigger.grouping))
                hits.push(createHit(trigger, context, rows, Window.of(rows)))

            break

        case "run":
            hits.push(createHit(trigger, context, matched, null))

            break
    }

    return hits
}

/** The same window of the same trigger hits at most once per cooldown. */
export function getHitCooldownKey(hit: Trigger.Hit): string {
    let subject = "run"

    if (hit.window !== null)
        subject = hit.window.key

    return `${hit.triggerId}_${subject}`
}

/**
 * The hit's thread: one per trigger, window and occasion — the run, the auction day or the
 * schedule's firing — so the same hit reported twice is handled once.
 */
export function getHitThreadId(hit: Trigger.Hit): Foundations.Thread.Id {
    let occasion: string

    if (hit.cause.type === "schedule")
        occasion = `schedule-${hit.cause.firedAt.getTime()}`
    else if (hit.cause.signal.type === "auction.published")
        occasion = `auction-${hit.cause.signal.deliveryDate}`
    else if (hit.runId !== null)
        occasion = `run-${hit.runId}`
    else
        occasion = `signal-${Date.now()}`

    return `${getHitCooldownKey(hit)}_${occasion}` as Foundations.Thread.Id
}
