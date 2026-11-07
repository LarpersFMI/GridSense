import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Run } from "../Run"

/** The Python pipeline reports runs; the Watchdog reads them. */
export namespace Internal {

    const RunResponse = z.object({ run: Run.Schema })

    /** Records a run whose rows are fully written, and reports the predictions updated to the Watchdog. Reporting the same issueTs again returns that run. */
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

    /** The run issued before this one — what p_near_zero_change compares against. Null for the first run. */
    export namespace GetPreviousRun {

        export const Response = z.object({ run: Run.Schema.nullable() })
        export type  Response = z.infer<typeof Response>
    }

    /** The latest run issued before an instant — at an auction, the forecast the delivery day had. Null if none was. */
    export namespace GetLatestRun {

        export const Query = z.object({ before: z.coerce.date() })
        export type  Query = z.infer<typeof Query>

        export const Response = z.object({ run: Run.Schema.nullable() })
        export type  Response = z.infer<typeof Response>
    }

    export async function reportRun(api: AxiosInstance, request: z.input<typeof ReportRun.Request>): Promise<ReportRun.Response> {
        const { data } = await api.post("/internal/runs", request)

        return ReportRun.Response.parse(data)
    }

    export async function getLatestRun(api: AxiosInstance, query: GetLatestRun.Query): Promise<GetLatestRun.Response> {
        const { data } = await api.get("/internal/runs/latest", { params: { before: query.before.toISOString() } })

        return GetLatestRun.Response.parse(data)
    }

    export async function getRun(api: AxiosInstance, id: Run.Id): Promise<GetRun.Response> {
        const { data } = await api.get(`/internal/runs/${id}`)

        return GetRun.Response.parse(data)
    }

    export async function getPreviousRun(api: AxiosInstance, id: Run.Id): Promise<GetPreviousRun.Response> {
        const { data } = await api.get(`/internal/runs/${id}/previous`)

        return GetPreviousRun.Response.parse(data)
    }
}
