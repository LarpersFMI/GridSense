import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Run } from "../Run"

/** The Python pipeline reports runs; the Watchdog reads them. */
export namespace Internal {

    const RunResponse = z.object({ run: Run.Schema })

    /** Records a run whose rows are fully written, and reports the predictions updated. Reporting the same issueTs again returns that run. */
    export namespace ReportRun {

        export const Request = Run.Report.Schema
        export type  Request = z.infer<typeof Request>

        export const Response = RunResponse
        export type  Response = z.infer<typeof Response>
    }

    export namespace GetRun {

        export const Response = RunResponse
        export type  Response = z.infer<typeof Response>
    }

    /** The run whose rows have this issue_ts — what the Watchdog's hours came from. Null if it was never reported. */
    export namespace FindRun {

        export const Query = z.object({ issueTs: z.coerce.date() })
        export type  Query = z.infer<typeof Query>

        export const Response = z.object({ run: Run.Schema.nullable() })
        export type  Response = z.infer<typeof Response>
    }

    export async function reportRun(api: AxiosInstance, request: z.input<typeof ReportRun.Request>): Promise<ReportRun.Response> {
        const { data } = await api.post("/internal/runs", request)

        return ReportRun.Response.parse(data)
    }

    export async function findRun(api: AxiosInstance, query: FindRun.Query): Promise<FindRun.Response> {
        const { data } = await api.get("/internal/runs", { params: { issueTs: query.issueTs.toISOString() } })

        return FindRun.Response.parse(data)
    }

    export async function getRun(api: AxiosInstance, id: Run.Id): Promise<GetRun.Response> {
        const { data } = await api.get(`/internal/runs/${id}`)

        return GetRun.Response.parse(data)
    }
}
