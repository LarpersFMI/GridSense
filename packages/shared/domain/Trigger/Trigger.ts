import { z } from "zod"
import { Foundations } from "../Foundations"
import { Run } from "../Forecaster/Run"
import { Window } from "../Time/Window"
import { Signal } from "../Watchdog/Signal"
import * as HelpersMod from "./helpers"

/**
 * A condition an admin writes on the columns of the Forecaster's predictions or of the cleared prices, checked when a signal
 * arrives or on a schedule. When it holds, the Watchdog wakes the agent with a Hit; whether to act, and
 * how, is the agent's decision. `description` tells the agent what the admin meant by it.
 */
export namespace Trigger {

    export const Id = Foundations.Id.define("Trigger.Id")
    export type  Id = z.infer<typeof Id>
    export const createId = () => Foundations.uuidv7() as Id

    /** The dataset a trigger's conditions read: a run's predictions, or a delivery day's cleared prices. */
    export const Source = z.enum(["predictions", "prices"])
    export type  Source = z.infer<typeof Source>

    /** Each signal's rows. A signal with none (and the clock) can only make a trigger without conditions hold. */
    export const SOURCE_OF: Record<Signal.Type, Source | null> = {
        "predictions.ready":      "predictions",
        "auction.published":      "prices",
        "data.validation-failed": null,
    }

    /**
     * What a condition can read. The parquet columns as they are, plus a few the Watchdog derives per hour:
     * local_hour and weekday (0 = Monday) in Romanian time, interval_width (P90 − P10), and
     * p_near_zero_change against the previous run's forecast of the same hour (absent for its first forecast).
     */
    export const Column = z.enum([
        "p_near_zero",
        "p_cheap",
        "price_p10",
        "price_p50",
        "price_p90",
        "interval_width",
        "p_near_zero_change",
        "horizon_days",
        "data_quality",
        "price_mean",
        "price_min",
        "price_max",
        "local_hour",
        "weekday",
    ])
    export type  Column = z.infer<typeof Column>

    export const COLUMNS_OF: Record<Source, readonly Column[]> = {
        predictions: [
            "p_near_zero",
            "p_cheap",
            "price_p10",
            "price_p50",
            "price_p90",
            "interval_width",
            "p_near_zero_change",
            "horizon_days",
            "data_quality",
            "local_hour",
            "weekday",
        ],
        prices: [
            "price_mean",
            "price_min",
            "price_max",
            "local_hour",
            "weekday",
        ],
    }

    /** Columns holding text; every other column holds a number. */
    export const TEXT_COLUMNS: ReadonlySet<Column> = new Set<Column>(["data_quality"])

    export namespace Condition {

        export const Operator = z.enum([">=", "<=", ">", "<", "==", "!=", "between", "in"])
        export type  Operator = z.infer<typeof Operator>

        /** Text columns compare by equality or membership only. */
        export const TEXT_OPERATORS: ReadonlySet<Operator> = new Set<Operator>(["==", "!=", "in"])

        /** `between` takes [low, high], both included; `in` takes a list. */
        export const Value = z.union([
            z.number(),
            z.string(),
            z.tuple([z.number(), z.number()]),
            z.array(z.union([z.number(), z.string()])).min(1),
        ])
        export type  Value = z.infer<typeof Value>

        export const Schema = z.object({
            column:   Column,
            operator: Operator,
            value:    Value,
        })

        export import matches = HelpersMod.matchesCondition
    }
    export type Condition = z.infer<typeof Condition.Schema>

    /** When the Watchdog checks it: on a signal, or on a five-field cron (Romanian time). */
    export const On = z.discriminatedUnion("type", [
        z.object({ type: z.literal("signal"),   signal: Signal.Type }),
        z.object({ type: z.literal("schedule"), cron:   z.string().regex(/^\S+(\s+\S+){4}$/, "A cron pattern has five fields") }),
    ])
    export type On = z.infer<typeof On>

    /**
     * How matching hours become hits. `hour`: one per hour · `window`: one per stretch of consecutive
     * matching hours on one local day, cut to at most maxHours and dropped under minHours · `run`: one for
     * all of them together.
     */
    export const Grouping = z.discriminatedUnion("type", [
        z.object({ type: z.literal("hour") }),
        z.object({ type: z.literal("window"), minHours: z.number().int().min(1), maxHours: z.number().int().min(1) }),
        z.object({ type: z.literal("run") }),
    ])
    export type Grouping = z.infer<typeof Grouping>

    /** `all`: every condition must hold for an hour to match · `any`: one is enough. */
    export const Match = z.enum(["all", "any"])
    export type  Match = z.infer<typeof Match>

    export const Schema = z.object({
        id:              Id,
        name:            z.string().min(1),
        description:     z.string(),
        enabled:         z.boolean(),
        on:              On,
        match:           Match,
        conditions:      Condition.Schema.array(),
        grouping:        Grouping,
        cooldownMinutes: z.number().int().nonnegative(),   // after a hit, the same window can't hit again for this long
    }).superRefine(HelpersMod.checkTrigger)

    /** Why the Watchdog checked: a signal arrived, or the trigger's schedule fired. */
    export const Cause = z.discriminatedUnion("type", [
        z.object({ type: z.literal("signal"),   signal:  Signal.Schema }),
        z.object({ type: z.literal("schedule"), firedAt: z.coerce.date() }),
    ])
    export type Cause = z.infer<typeof Cause>

    /** One hour as a trigger sees it: when it is, and its column values. */
    export interface Row {
        at:     Date
        values: Partial<Record<Column, number | string>>
    }

    export namespace Row {

        export import fromPrediction = HelpersMod.rowFromPrediction
        export import fromPrice      = HelpersMod.rowFromPrice
    }

    /** What a trigger is checked against: the cause, and the source's rows (empty without a source). */
    export interface Context {
        cause: Cause
        runId: Run.Id | null
        rows:  Row[]
    }

    /**
     * What the Watchdog hands the agent: which trigger held, on what, and what the matching hours looked like.
     * Evidence is `<column>.min / .mean / .max` for each number column the conditions read, and
     * `<column>=<value>` counts for each text one.
     */
    export namespace Hit {

        export const Schema = z.object({
            triggerId:    Id,
            cause:        Cause,
            runId:        Run.Id.nullable(),
            window:       Window.Schema.nullable(),        // null for `run` grouping and triggers without a source
            matchedHours: z.number().int().nonnegative(),
            evidence:     z.record(z.string(), z.number()),
        })

        export import getQueueJobId = HelpersMod.getHitQueueJobId
        export import getCooldownKey = HelpersMod.getHitCooldownKey
    }
    export type Hit = z.infer<typeof Hit.Schema>

    export import getSource = HelpersMod.getSource
    export import evaluate = HelpersMod.evaluate
}
export type Trigger = z.infer<typeof Trigger.Schema>
