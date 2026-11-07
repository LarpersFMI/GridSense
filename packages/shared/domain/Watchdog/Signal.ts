import { z } from "zod"
import { Run } from "../Forecaster/Run"

/** Something that happened outside the Watchdog and may make a trigger hold. The clock is not one: see Queue.Schedule. */
export namespace Signal {

    /** A Forecaster run's rows are fully written (the Python pipeline reported it). */
    export namespace PredictionsReady {

        export const Schema = z.object({
            type:   z.literal("predictions.ready"),
            runId:  Run.Id,
        })
    }
    export type PredictionsReady = z.infer<typeof PredictionsReady.Schema>

    /** The day-ahead auction cleared prices for one local delivery day. */
    export namespace AuctionPublished {

        export const Schema = z.object({
            type:         z.literal("auction.published"),
            deliveryDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
        })
    }
    export type AuctionPublished = z.infer<typeof AuctionPublished.Schema>

    /** Input checks failed before or during a run. */
    export namespace ValidationFailed {

        export const Schema = z.object({
            type:     z.literal("data.validation-failed"),
            runId:    Run.Id.nullable(),
            problems: z.string().array().min(1),
        })
    }
    export type ValidationFailed = z.infer<typeof ValidationFailed.Schema>

    export const Schema = z.discriminatedUnion("type", [
        PredictionsReady.Schema,
        AuctionPublished.Schema,
        ValidationFailed.Schema,
    ])

    export const Type = z.enum([
        "predictions.ready",
        "auction.published",
        "data.validation-failed",
    ])
    export type  Type = z.infer<typeof Type>

    /** One job per run or delivery day, so a repeated report is ignored; every failed check counts. */
    export function getQueueJobId(signal: Signal): string | undefined {
        switch (signal.type) {
            case "predictions.ready":
                return `predictions-ready_${signal.runId}`

            case "auction.published":
                return `auction-published_${signal.deliveryDate}`

            case "data.validation-failed":
                return undefined
        }
    }
}
export type Signal = z.infer<typeof Signal.Schema>
