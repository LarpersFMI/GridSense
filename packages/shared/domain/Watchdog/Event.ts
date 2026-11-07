import { z } from "zod"
import { Foundations } from "../Foundations"
import { Realtime } from "../Realtime/Realtime"
import { Trigger } from "../Trigger"

/** Live changes from the Watchdog: what it checked, and the hits it raised. */
export namespace Event {

    export const Channel = Realtime.Channel.brand("Watchdog.Event.Channel")
    export type  Channel = z.infer<typeof Channel>

    /** Every check, whatever caused it. */
    export const ACTIVITY_CHANNEL = "watchdog:activity" as Channel

    const PREFIX = "watchdog:trigger:"

    /** One trigger's hits. */
    export const getTriggerChannel = (triggerId: Trigger.Id) => `${PREFIX}${triggerId}` as Channel

    export const Base = Realtime.Event.Base.extend({
        channel: Channel,
    })

    export namespace Check {

        /** A dataset update or a schedule was checked against the triggers on it. `cooledDown`: hits held back by a cooldown. */
        export namespace Completed {

            export const Schema = Base.extend({
                type:            z.literal("watchdog:check:completed"),
                cause:           Trigger.Check.Cause,
                triggersChecked: z.number().int().nonnegative(),
                hits:            z.number().int().nonnegative(),
                cooledDown:      z.number().int().nonnegative(),
                checkedAt:       z.coerce.date(),
            })
        }
        export type Completed = z.infer<typeof Completed.Schema>
    }

    export namespace Hit {

        /** A trigger held and the agent was handed the hit, on this thread. */
        export namespace Raised {

            export const Schema = Base.extend({
                type:     z.literal("watchdog:hit:raised"),
                hit:      Trigger.Hit.Schema,
                threadId: Foundations.Thread.Id,
            })
        }
        export type Raised = z.infer<typeof Raised.Schema>
    }

    export const Schema = z.discriminatedUnion("type", [
        Check.Completed.Schema,
        Hit.Raised.Schema,
    ])

    /** `create("watchdog:hit:raised", { hit, threadId })` — without its channel; the publisher adds it. */
    export const create = Realtime.Event.defineFactory(Schema)
}
export type Event = z.infer<typeof Event.Schema>
