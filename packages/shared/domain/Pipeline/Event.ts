import { z } from "zod"
import { PipelineRunId } from "../ids"
import { Realtime } from "../Realtime/Realtime"
import { Run as RunD } from "./Run"

/** Live changes on pipeline runs: each run as it starts and ends, and its log as it's written. */
export namespace Event {

    export const Channel = Realtime.Channel.brand("Pipeline.Event.Channel")
    export type  Channel = z.infer<typeof Channel>

    /** Every run, started and finished. */
    export const RUNS_CHANNEL = "pipeline:runs" as Channel

    const PREFIX = "pipeline:run:"

    /** One run's log lines. */
    export const getRunChannel = (runId: PipelineRunId) => `${PREFIX}${runId}` as Channel

    export const Base = Realtime.Event.Base.extend({
        channel: Channel,
    })

    export namespace Run {

        /** A run started or finished: the run as it is now. */
        export namespace Updated {

            export const Schema = Base.extend({
                type: z.literal("pipeline:run:updated"),
                run:  RunD.Schema,
            })
        }
        export type Updated = z.infer<typeof Updated.Schema>

        /** Lines the run's process wrote (stdout and stderr), in order. */
        export namespace Logged {

            export const Schema = Base.extend({
                type:  z.literal("pipeline:run:logged"),
                runId: PipelineRunId,
                lines: z.string().array(),
            })
        }
        export type Logged = z.infer<typeof Logged.Schema>
    }

    export const Schema = z.discriminatedUnion("type", [
        Run.Updated.Schema,
        Run.Logged.Schema,
    ])

    export const create = Realtime.Event.defineFactory(Schema)
}
export type Event = z.infer<typeof Event.Schema>
