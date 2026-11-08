import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Schema, State } from "../Schema"
import * as InternalMod from "./internal"

/** The replay over HTTP, for the browser. The PipelineRunner's is `Internal`. */
export namespace API {

    export import Internal = InternalMod.Internal

    export namespace Get {

        export const Response = z.object({ replay: State })
        export type  Response = z.infer<typeof Response>
    }

    /** Moves the start, then resets: the replay begins again from it. */
    export namespace SetStart {

        export const Request = Schema
        export type  Request = z.infer<typeof Request>
    }

    /**
     * Starts over from the same day: the replay's dataset files and forecast runs removed, the triggers' watermarks reset (prices ones past
     * the history the first `prices` run adds), the agent's queued hits, threads, slots and checkpoints and the Watchdog's cooldowns cleared, the replay
     * pipelines' runs forgotten.
     */
    export namespace Reset {}

    /** One day: `forecast` then `prices` queued, in that order (the PipelineRunner runs one at a time). */
    export namespace Step {

        export const Response = z.object({ queued: z.literal(true) })
        export type  Response = z.infer<typeof Response>
    }

    export async function get(api: AxiosInstance): Promise<Get.Response> {
        const { data } = await api.get("/api/replay")

        return Get.Response.parse(data)
    }

    export async function setStart(api: AxiosInstance, request: SetStart.Request): Promise<Get.Response> {
        const { data } = await api.put("/api/replay", request)

        return Get.Response.parse(data)
    }

    export async function reset(api: AxiosInstance): Promise<Get.Response> {
        const { data } = await api.post("/api/replay/reset")

        return Get.Response.parse(data)
    }

    export async function step(api: AxiosInstance): Promise<Step.Response> {
        const { data } = await api.post("/api/replay/step")

        return Step.Response.parse(data)
    }
}
