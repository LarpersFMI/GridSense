import { z } from "zod"
import { Realtime } from "../Realtime/Realtime"
import { Message } from "./Message"
import { Slot as SlotD } from "./Slot"
import { Thread as ThreadD } from "./Thread"

/** Live changes from the agent: every thread as it moves through the graph, and the slots it announces. */
export namespace Event {

    export const Channel = Realtime.Channel.brand("Agent.Event.Channel")
    export type  Channel = z.infer<typeof Channel>

    /** Every thread, at every step; the inbox is the ones awaiting review. */
    export const THREADS_CHANNEL = "agent:threads" as Channel

    /** Slots announced, confirmed, cancelled. */
    export const SLOTS_CHANNEL = "agent:slots" as Channel

    export const Base = Realtime.Event.Base.extend({
        channel: Channel,
    })

    export namespace Thread {

        /** A thread moved: a node ran, it paused, it ended — the thread as it is now. */
        export namespace Updated {

            export const Schema = Base.extend({
                type:   z.literal("agent:thread:updated"),
                thread: ThreadD.Schema,
            })
        }
        export type Updated = z.infer<typeof Updated.Schema>

        /** The agent is answering the operator's question: the tool calls it has made so far, live, before the answer. */
        export namespace Answering {

            export const Schema = Base.extend({
                type:     z.literal("agent:thread:answering"),
                threadId: ThreadD.Id,
                calls:    Message.ToolCall.array(),
            })
        }
        export type Answering = z.infer<typeof Answering.Schema>
    }

    export namespace Slot {

        export namespace Updated {

            export const Schema = Base.extend({
                type: z.literal("agent:slot:updated"),
                slot: SlotD.Schema,
            })
        }
        export type Updated = z.infer<typeof Updated.Schema>
    }

    export const Schema = z.discriminatedUnion("type", [
        Thread.Updated.Schema,
        Thread.Answering.Schema,
        Slot.Updated.Schema,
    ])

    /** `create("agent:thread:updated", { thread })` — without its channel; the publisher adds it. */
    export const create = Realtime.Event.defineFactory(Schema)
}
export type Event = z.infer<typeof Event.Schema>
