import { z } from "zod"
import type { AxiosInstance } from "axios"
import { PipelineRunId } from "../../ids"
import { Name } from "../Name"
import { Run } from "../Run"
import { Schedule } from "../Schedule"
import { Schema } from "../Schema"

/** For the PipelineRunner: the pipelines Python defines, their schedules, and the runs it starts. */
export namespace Internal {

    /**
     * The pipelines Python defines now: new ones are saved with their default cron, disabled; known ones are updated;
     * ones Python no longer has are marked unavailable (their runs are kept).
     */
    export namespace SyncDefinitions {

        export const Request = z.object({ pipelines: Schema.array() })
        export type  Request = z.infer<typeof Request>

        export const Response = z.object({ pipelines: z.record(Name, Schema) })
        export type  Response = z.infer<typeof Response>
    }

    /** The enabled schedules of available pipelines: the job schedulers the PipelineRunner keeps. */
    export namespace ListScheduled {

        export const Response = z.object({ schedules: z.record(Name, Schedule.Schema) })
        export type  Response = z.infer<typeof Response>
    }

    /** A run starts: saved as running, and announced. */
    export namespace StartRun {

        export const Request = z.object({
            pipeline: Name,
            cause:    Run.Cause,
        })
        export type Request = z.infer<typeof Request>

        export const Response = z.object({ run: Run.Schema })
        export type  Response = z.infer<typeof Response>
    }

    /** A run ended: its status, what it appended, its error and its whole log. */
    export namespace FinishRun {

        export const Request = z.object({
            status:       Run.Status.exclude(["running"]),
            rowsAppended: z.record(z.string(), z.number().int().nonnegative()),
            error:        z.string().nullable(),
            log:          z.string(),
        })
        export type Request = z.infer<typeof Request>

        export const Response = z.object({ run: Run.Schema })
        export type  Response = z.infer<typeof Response>
    }

    export async function syncDefinitions(api: AxiosInstance, request: SyncDefinitions.Request): Promise<SyncDefinitions.Response> {
        const { data } = await api.put("/internal/pipelines", request)

        return SyncDefinitions.Response.parse(data)
    }

    export async function listScheduled(api: AxiosInstance): Promise<ListScheduled.Response> {
        const { data } = await api.get("/internal/pipelines/scheduled")

        return ListScheduled.Response.parse(data)
    }

    export async function startRun(api: AxiosInstance, request: StartRun.Request): Promise<StartRun.Response> {
        const { data } = await api.post("/internal/pipelines/runs", request)

        return StartRun.Response.parse(data)
    }

    export async function finishRun(api: AxiosInstance, id: PipelineRunId, request: FinishRun.Request): Promise<FinishRun.Response> {
        const { data } = await api.put(`/internal/pipelines/runs/${id}`, request)

        return FinishRun.Response.parse(data)
    }
}
