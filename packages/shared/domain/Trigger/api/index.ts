import { z } from "zod"
import type { AxiosInstance } from "axios"
import { ThreadId, TriggerId } from "../../ids"
import { Hit } from "../Hit"
import { Schema } from "../Schema"
import * as InternalMod from "./internal"

/** The admin's triggers over HTTP — mirrors the server's trigger http controller. The Watchdog's is `Internal`. */
export namespace API {

    export import Internal = InternalMod.Internal

    const TriggerResponse = z.object({ trigger: Schema })

    export namespace List {

        export const Response = z.object({ triggers: z.record(TriggerId, Schema) })
        export type  Response = z.infer<typeof Response>
    }

    export namespace Get {

        export const Response = TriggerResponse
        export type  Response = z.infer<typeof Response>
    }

    /** Saves a new trigger, id included (made by the caller); 409 if that id exists. The Watchdog brings its schedules in line. */
    export namespace Create {

        export const Request = Schema
        export type  Request = z.infer<typeof Request>

        export const Response = TriggerResponse
        export type  Response = z.infer<typeof Response>
    }

    /** Replaces a saved trigger with this one — same id as in the path. The Watchdog brings its schedules in line. */
    export namespace Update {

        export const Request = Schema
        export type  Request = z.infer<typeof Request>

        export const Response = TriggerResponse
        export type  Response = z.infer<typeof Response>
    }

    /** Deletes a trigger and returns it as it was. */
    export namespace Delete {

        export const Response = TriggerResponse
        export type  Response = z.infer<typeof Response>
    }

    /** The latest hits, newest first, from the agent's queue — optionally one trigger's. */
    export namespace ListHits {

        export const Query = z.object({
            triggerId: TriggerId.optional(),
            limit:     z.coerce.number().int().min(1).max(1000).default(200),
        })
        export type Query = z.infer<typeof Query>

        export const Response = z.object({ hits: z.record(ThreadId, Hit.Queued.Schema) })
        export type  Response = z.infer<typeof Response>
    }

    export async function list(api: AxiosInstance): Promise<List.Response> {
        const { data } = await api.get("/api/triggers")

        return List.Response.parse(data)
    }

    export async function get(api: AxiosInstance, id: TriggerId): Promise<Get.Response> {
        const { data } = await api.get(`/api/triggers/${id}`)

        return Get.Response.parse(data)
    }

    export async function create(api: AxiosInstance, request: z.input<typeof Create.Request>): Promise<Create.Response> {
        const { data } = await api.post("/api/triggers", request)

        return Create.Response.parse(data)
    }

    export async function update(api: AxiosInstance, request: z.input<typeof Update.Request>): Promise<Update.Response> {
        const { data } = await api.put(`/api/triggers/${request.id}`, request)

        return Update.Response.parse(data)
    }

    export async function listHits(api: AxiosInstance, query: z.input<typeof ListHits.Query> = {}): Promise<ListHits.Response> {
        const { data } = await api.get("/api/hits", { params: query })

        return ListHits.Response.parse(data)
    }

    export async function remove(api: AxiosInstance, id: TriggerId): Promise<Delete.Response> {
        const { data } = await api.delete(`/api/triggers/${id}`)

        return Delete.Response.parse(data)
    }
}
