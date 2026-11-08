import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Foundations } from "../../Foundations"
import { Graph } from "../Graph"
import { Message } from "../Message"
import { Slot } from "../Slot"
import { Thread } from "../Thread"

/** The central agent's records, kept by the server: its threads as they move, the slots, its graph. */
export namespace Internal {

    /** The thread as it is now, whole: created on its first step, replaced on each after. Goes out live. */
    export namespace SaveThread {

        export const Request = z.object({ thread: Thread.Schema })
        export type  Request = z.infer<typeof Request>

        export const Response = z.object({ thread: Thread.Schema })
        export type  Response = z.infer<typeof Response>
    }

    /** The slots overlapping [start, end) — the ones a hit on that window may confirm or cancel. */
    export namespace ListSlots {

        export const Query = z.object({
            start: z.coerce.date(),
            end:   z.coerce.date(),
        })
        export type Query = z.infer<typeof Query>

        export const Response = z.object({ slots: z.record(z.string(), Slot.Schema) })
        export type  Response = z.infer<typeof Response>
    }

    export namespace SaveSlot {

        export const Request = z.object({ slot: Slot.Schema })
        export type  Request = z.infer<typeof Request>

        export const Response = z.object({ slot: Slot.Schema })
        export type  Response = z.infer<typeof Response>
    }

    export namespace SaveGraph {

        export const Request = z.object({ graph: Graph.Schema })
        export type  Request = z.infer<typeof Request>
    }

    /** The agent's answer, added to the thread's conversation (a save of the thread leaves the conversation alone). */
    export namespace AddMessage {

        export const Request = z.object({ message: Message.Schema })
        export type  Request = z.infer<typeof Request>
    }

    export async function addMessage(api: AxiosInstance, id: Foundations.Thread.Id, request: AddMessage.Request): Promise<SaveThread.Response> {
        const { data } = await api.post(`/internal/agent/threads/${encodeURIComponent(id)}/messages`, request)

        return SaveThread.Response.parse(data)
    }

    export async function saveThread(api: AxiosInstance, request: SaveThread.Request): Promise<SaveThread.Response> {
        const { data } = await api.put(`/internal/agent/threads/${encodeURIComponent(request.thread.id)}`, request)

        return SaveThread.Response.parse(data)
    }

    export async function getThread(api: AxiosInstance, id: Foundations.Thread.Id): Promise<SaveThread.Response> {
        const { data } = await api.get(`/internal/agent/threads/${encodeURIComponent(id)}`)

        return SaveThread.Response.parse(data)
    }

    export async function listSlots(api: AxiosInstance, query: ListSlots.Query): Promise<ListSlots.Response> {
        const { data } = await api.get("/internal/agent/slots", {
            params: { start: query.start.toISOString(), end: query.end.toISOString() },
        })

        return ListSlots.Response.parse(data)
    }

    export async function saveSlot(api: AxiosInstance, request: SaveSlot.Request): Promise<SaveSlot.Response> {
        const { data } = await api.put(`/internal/agent/slots/${encodeURIComponent(request.slot.key)}`, request)

        return SaveSlot.Response.parse(data)
    }

    export async function saveGraph(api: AxiosInstance, request: SaveGraph.Request): Promise<void> {
        await api.put("/internal/agent/graph", request)
    }
}
