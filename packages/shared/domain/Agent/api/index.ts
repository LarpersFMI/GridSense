import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Foundations } from "../../Foundations"
import { Graph } from "../Graph"
import { Slot } from "../Slot"
import { Thread } from "../Thread"
import * as InternalMod from "./internal"

/** The agent over HTTP, for the browser: its threads, the review inbox, the slots, its graph. The agent's is `Internal`. */
export namespace API {

    export import Internal = InternalMod.Internal

    /** The latest threads, newest first; `status: awaiting-review` is the inbox. */
    export namespace ListThreads {

        export const Query = z.object({
            status: Thread.Status.optional(),
            limit:  z.coerce.number().int().min(1).max(500).default(100),
        })
        export type Query = z.infer<typeof Query>

        export const Response = z.object({ threads: z.record(Foundations.Thread.Id, Thread.Schema) })
        export type  Response = z.infer<typeof Response>
    }

    export namespace GetThread {

        export const Response = z.object({ thread: Thread.Schema })
        export type  Response = z.infer<typeof Response>
    }

    /** An admin's answer to a thread awaiting review: the agent resumes it (`agent.resume`). */
    export namespace Review {

        export const Request = Thread.Review.omit({ at: true })
        export type  Request = z.infer<typeof Request>

        export const Response = z.object({ queued: z.literal(true) })
        export type  Response = z.infer<typeof Response>
    }

    /** The operator asks the agent about a thread: the question goes on it at once, the answer comes live. */
    export namespace Ask {

        export const Request = z.object({ question: z.string().trim().min(1).max(1000) })
        export type  Request = z.infer<typeof Request>

        export const Response = z.object({ queued: z.literal(true) })
        export type  Response = z.infer<typeof Response>
    }

    /** Slots from a time on (default: all), by key. */
    export namespace ListSlots {

        export const Query = z.object({ from: z.coerce.date().optional() })
        export type  Query = z.infer<typeof Query>

        export const Response = z.object({ slots: z.record(z.string(), Slot.Schema) })
        export type  Response = z.infer<typeof Response>
    }

    export namespace GetGraph {

        export const Response = z.object({ graph: Graph.Schema.nullable() })      // null until the agent has started once
        export type  Response = z.infer<typeof Response>
    }

    /** The confirmed and likely slots as a calendar file (text/calendar). */
    export const CALENDAR_PATH = "/api/agent/calendar.ics"

    export async function listThreads(api: AxiosInstance, query: z.input<typeof ListThreads.Query> = {}): Promise<ListThreads.Response> {
        const { data } = await api.get("/api/agent/threads", { params: query })

        return ListThreads.Response.parse(data)
    }

    export async function getThread(api: AxiosInstance, id: Foundations.Thread.Id): Promise<GetThread.Response> {
        const { data } = await api.get(`/api/agent/threads/${encodeURIComponent(id)}`)

        return GetThread.Response.parse(data)
    }

    export async function review(api: AxiosInstance, id: Foundations.Thread.Id, request: Review.Request): Promise<Review.Response> {
        const { data } = await api.post(`/api/agent/threads/${encodeURIComponent(id)}/review`, request)

        return Review.Response.parse(data)
    }

    export async function ask(api: AxiosInstance, id: Foundations.Thread.Id, request: Ask.Request): Promise<Ask.Response> {
        const { data } = await api.post(`/api/agent/threads/${encodeURIComponent(id)}/questions`, request)

        return Ask.Response.parse(data)
    }

    export async function listSlots(api: AxiosInstance, query: z.input<typeof ListSlots.Query> = {}): Promise<ListSlots.Response> {
        const { data } = await api.get("/api/agent/slots", { params: query })

        return ListSlots.Response.parse(data)
    }

    export async function getGraph(api: AxiosInstance): Promise<GetGraph.Response> {
        const { data } = await api.get("/api/agent/graph")

        return GetGraph.Response.parse(data)
    }
}
