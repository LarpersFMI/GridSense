import { z } from "zod"
import { Realtime } from "../Realtime/Realtime"
import { Run as RunD } from "./Run"

/** Live changes on the Forecaster's runs. */
export namespace Event {

    export const Channel = Realtime.Channel.brand("Forecaster.Event.Channel")
    export type  Channel = z.infer<typeof Channel>

    /** Every run, as the pipeline reports it. */
    export const RUNS_CHANNEL = "forecaster:runs" as Channel

    export const Base = Realtime.Event.Base.extend({
        channel: Channel,
    })

    export namespace Run {

        /** The pipeline reported a run: its predictions are written. */
        export namespace Reported {

            export const Schema = Base.extend({
                type: z.literal("forecaster:run:reported"),
                run:  RunD.Schema,
            })
        }
        export type Reported = z.infer<typeof Reported.Schema>
    }

    export const Schema = z.discriminatedUnion("type", [
        Run.Reported.Schema,
    ])

    /** `create("forecaster:run:reported", { run })` — without its channel; the publisher adds it. */
    export const create = Realtime.Event.defineFactory(Schema)
}
export type Event = z.infer<typeof Event.Schema>
