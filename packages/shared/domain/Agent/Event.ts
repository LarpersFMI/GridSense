import { z } from "zod"
import { Foundations } from "../Foundations"
import { Realtime } from "../Realtime/Realtime"
import { Trigger } from "../Trigger/Trigger"
import { Queue } from "./queue"

/** Live changes from the agent: each thread as it works, and the admin's review inbox. */
export namespace Event {

    export const Channel = Realtime.Channel.brand("Agent.Event.Channel")
    export type  Channel = z.infer<typeof Channel>

    /** Reviews requested and resolved, across threads. */
    export const INBOX_CHANNEL = "agent:inbox" as Channel

    const PREFIX = "agent:thread:"

    /** One thread's steps. */
    export const getThreadChannel = (threadId: Foundations.Thread.Id) => `${PREFIX}${threadId}` as Channel

    export const Base = Realtime.Event.Base.extend({
        channel: Channel,
    })

    export namespace Thread {

        /** `running` a step · paused `awaiting-review` · finished: `acted`, `dismissed` or `failed`. */
        export const Status = z.enum(["running", "awaiting-review", "acted", "dismissed", "failed"])
        export type  Status = z.infer<typeof Status>

        /** Any change to a thread — a step started or finished, a pause, the end: the thread as it is now. */
        export namespace Updated {

            export const Schema = Base.extend({
                type:      z.literal("agent:thread:updated"),
                threadId:  Foundations.Thread.Id,
                triggerId: Trigger.Id,
                status:    Status,
                step:      z.string(),                  // the graph node it's in or just left: "decide", "act", …
                updatedAt: z.coerce.date(),
            })
        }
        export type Updated = z.infer<typeof Updated.Schema>
    }

    export namespace Review {

        /** A thread paused for an admin: what it would do, and why it isn't sure. */
        export namespace Requested {

            export const Schema = Base.extend({
                type:        z.literal("agent:review:requested"),
                threadId:    Foundations.Thread.Id,
                hit:         Trigger.Hit.Schema,
                proposal:    z.string(),
                reason:      z.string(),
                requestedAt: z.coerce.date(),
            })
        }
        export type Requested = z.infer<typeof Requested.Schema>

        /** An admin approved or rejected it; the thread resumes. */
        export namespace Resolved {

            export const Schema = Base.extend({
                type:       z.literal("agent:review:resolved"),
                threadId:   Foundations.Thread.Id,
                decision:   Queue.Resume.Decision,
                resolvedAt: z.coerce.date(),
            })
        }
        export type Resolved = z.infer<typeof Resolved.Schema>
    }

    export const Schema = z.discriminatedUnion("type", [
        Thread.Updated.Schema,
        Review.Requested.Schema,
        Review.Resolved.Schema,
    ])

    /** `create("agent:thread:updated", { … })` — without its channel; the publisher adds it. */
    export const create = Realtime.Event.defineFactory(Schema)
}
export type Event = z.infer<typeof Event.Schema>
