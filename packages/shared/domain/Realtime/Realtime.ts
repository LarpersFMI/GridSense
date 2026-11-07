import { z } from "zod"

/**
 * Live messages over Redis pub/sub, relayed to browsers by the server's /socket (from Quarry's Realtime,
 * without authorization: any browser may subscribe to any channel). A domain declares its own events
 * (`Agent.Event`): a branded channel type, its channels, and a discriminated union on `type`
 * (`"domain:entity:verb"`).
 */
export namespace Realtime {

    export const Channel = z.string().brand("Channel")
    export type  Channel = z.infer<typeof Channel>

    export namespace Event {

        export const Type = z.string()
        export type  Type = z.infer<typeof Type>

        export const Base = z.object({
            channel: Channel,
            type:    Type,
        })

        /**
         * A domain's typed `create(type, rest)`, from its union: `rest` is exactly that member's own fields.
         * The event comes back without its channel — the publisher adds where it goes:
         *
         *   realtime.emitEvent({ ...Agent.Event.create("agent:thread:updated", { … }), channel })
         *
         * The schema only drives the types; nothing is parsed.
         */
        export function defineFactory<S extends z.ZodType<z.infer<typeof Base>>>(_schema: S) {

            type Member = z.infer<S>

            type OfType<T extends Member["type"]> = Extract<Member, { type: T }>

            type Rest<T extends Member["type"]> = Omit<OfType<T>, "channel" | "type">

            /** Members with no fields of their own take no second argument. */
            type RestArg<T extends Member["type"]> = {} extends Rest<T> ? [rest?: Rest<T>] : [rest: Rest<T>]

            return function create<T extends Member["type"]>(type: T, ...[rest]: RestArg<T>): Omit<OfType<T>, "channel"> {
                return { ...rest, type } as Omit<OfType<T>, "channel">
            }
        }
    }
    export type Event = z.infer<typeof Event.Base>

    /** What a browser sends on the socket. */
    export const ClientMessage = z.object({
        action:  z.enum(["subscribe", "unsubscribe"]),
        channel: Channel,
    })
    export type ClientMessage = z.infer<typeof ClientMessage>
}
