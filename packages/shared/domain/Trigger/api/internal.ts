import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Name } from "../../Dataset/Name"
import { TriggerId } from "../../ids"
import { Schema } from "../Schema"

/** For the Watchdog: the triggers it checks. */
export namespace Internal {

    const TriggersResponse = z.object({ triggers: z.record(TriggerId, Schema) })

    /** Enabled triggers checked when this dataset updates. */
    export namespace ListForDataset {

        export const Query = z.object({ dataset: Name })
        export type  Query = z.infer<typeof Query>

        export const Response = TriggersResponse
        export type  Response = z.infer<typeof Response>
    }

    /** Enabled triggers on a schedule: the job schedulers the Watchdog keeps. */
    export namespace ListScheduled {

        export const Response = TriggersResponse
        export type  Response = z.infer<typeof Response>
    }

    export namespace Get {

        export const Response = z.object({ trigger: Schema })
        export type  Response = z.infer<typeof Response>
    }

    export async function listForDataset(api: AxiosInstance, query: ListForDataset.Query): Promise<ListForDataset.Response> {
        const { data } = await api.get("/internal/triggers", { params: query })

        return ListForDataset.Response.parse(data)
    }

    export async function listScheduled(api: AxiosInstance): Promise<ListScheduled.Response> {
        const { data } = await api.get("/internal/triggers/scheduled")

        return ListScheduled.Response.parse(data)
    }

    export async function get(api: AxiosInstance, id: TriggerId): Promise<Get.Response> {
        const { data } = await api.get(`/internal/triggers/${id}`)

        return Get.Response.parse(data)
    }
}
