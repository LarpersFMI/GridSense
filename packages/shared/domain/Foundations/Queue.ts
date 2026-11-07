import { z } from "zod"

/**
 * The contract of a background-job queue: its name, the job payload, the
 * result, default options. Each package declares its own in its domain's
 * `queue.ts`; the BullMQ runtime lives in the packages that produce and process.
 */
export namespace Queue {

    /**
     * A queue's identity — Redis keys, processor routing and producers all
     * hang off it, so it's validated: `<package>.<job>`, kebab-case segments,
     * no colons (BullMQ uses them in keys).
     */
    export const Name = z.string()
        .regex(/^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$/, "Queue names are <package>.<job>, kebab-case")
        .brand("Foundations.Queue.Name")
    export type  Name = z.infer<typeof Name>

    /** Job retention: true = remove at once, a number = keep that many, or keep for `age` seconds (at most `count`). */
    export type Keep = boolean | number | { readonly age: number; readonly count?: number }

    /** The subset of BullMQ job options a queue may default — no BullMQ dependency here. */
    export interface Options {
        readonly attempts?:         number
        readonly backoff?:          { readonly type: "fixed" | "exponential"; readonly delay: number }
        readonly removeOnComplete?: Keep
        readonly removeOnFail?:     Keep
    }

    export interface Definition<J extends z.ZodType = z.ZodType, R extends z.ZodType = z.ZodType> {
        readonly name:     Name
        readonly job:      J
        readonly result:   R
        readonly options?: Options
    }

    /** Declares a queue. Throws at module load on a malformed name. */
    export const define = <J extends z.ZodType, R extends z.ZodType>(definition: {
        name:     string
        job:      J
        result:   R
        options?: Options
    }): Definition<J, R> => ({ ...definition, name: Name.parse(definition.name) })

    export type JobOf<Q extends Definition>    = z.output<Q["job"]>
    export type InputOf<Q extends Definition>  = z.input<Q["job"]>
    export type ResultOf<Q extends Definition> = z.output<Q["result"]>
}
