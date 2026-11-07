import { z } from "zod"
import type { AxiosInstance } from "axios"
import { PipelineRunId } from "../../ids"
import { Name } from "../Name"
import { Run } from "../Run"
import { Schedule } from "../Schedule"
import { Schema } from "../Schema"
import * as InternalMod from "./internal"

/** Pipelines over HTTP, for the browser. The PipelineRunner's is `Internal`. */
export namespace API {

    export import Internal = InternalMod.Internal

    /** Every pipeline Python defines (and ones it no longer does, `available: false`), its schedule and its last run. */
    export namespace List {

        export const Response = z.object({
            pipelines: z.record(Name, Schema.extend({ available: z.boolean() })),
            schedules: z.record(Name, Schedule.Schema),
            lastRuns:  z.record(Name, Run.Schema),
        })
        export type Response = z.infer<typeof Response>
    }

    /** Changes when a pipeline runs, or switches it on or off. The PipelineRunner brings its schedulers in line. */
    export namespace SetSchedule {

        export const Request = Schedule.Schema.omit({ pipeline: true })
        export type  Request = z.infer<typeof Request>

        export const Response = z.object({ schedule: Schedule.Schema })
        export type  Response = z.infer<typeof Response>
    }

    /** Queues a run now; the run itself shows up live (`Pipeline.Event`) once the PipelineRunner starts it. */
    export namespace RunNow {

        export const Response = z.object({ queued: z.literal(true) })
        export type  Response = z.infer<typeof Response>
    }

    /** The latest runs, newest first: every pipeline's, or one's. */
    export namespace ListRuns {

        export const Query = z.object({
            pipeline: Name.optional(),
            limit:    z.coerce.number().int().min(1).max(500).default(50),
        })
        export type Query = z.infer<typeof Query>

        export const Response = z.object({ runs: z.record(PipelineRunId, Run.Schema) })
        export type  Response = z.infer<typeof Response>
    }

    /** A run and its whole log. */
    export namespace GetRun {

        export const Response = z.object({
            run: Run.Schema,
            log: z.string(),
        })
        export type Response = z.infer<typeof Response>
    }

    export async function list(api: AxiosInstance): Promise<List.Response> {
        const { data } = await api.get("/api/pipelines")

        return List.Response.parse(data)
    }

    export async function setSchedule(api: AxiosInstance, name: Name, request: SetSchedule.Request): Promise<SetSchedule.Response> {
        const { data } = await api.put(`/api/pipelines/${name}/schedule`, request)

        return SetSchedule.Response.parse(data)
    }

    export async function runNow(api: AxiosInstance, name: Name): Promise<RunNow.Response> {
        const { data } = await api.post(`/api/pipelines/${name}/runs`)

        return RunNow.Response.parse(data)
    }

    export async function listRuns(api: AxiosInstance, query: z.input<typeof ListRuns.Query> = {}): Promise<ListRuns.Response> {
        const { data } = await api.get("/api/pipelines/runs", { params: query })

        return ListRuns.Response.parse(data)
    }

    export async function getRun(api: AxiosInstance, id: PipelineRunId): Promise<GetRun.Response> {
        const { data } = await api.get(`/api/pipelines/runs/${id}`)

        return GetRun.Response.parse(data)
    }
}
