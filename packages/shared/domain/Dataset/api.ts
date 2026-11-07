import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Description } from "./Description"
import { Name } from "./Name"
import { Update } from "./Update"

/** The datasets over HTTP: described for the browser, updated by the Python pipeline. */
export namespace API {

    /** A dataset's columns and their types, read from its file — the condition editor's columns. */
    export namespace Describe {

        export const Params = z.object({ name: Name })
        export type  Params = z.infer<typeof Params>

        export const Response = z.object({ description: Description.Schema })
        export type  Response = z.infer<typeof Response>
    }

    export async function describe(api: AxiosInstance, name: Name): Promise<Describe.Response> {
        const { data } = await api.get(`/api/datasets/${name}/schema`)

        return Describe.Response.parse(data)
    }

    /** For the Python pipeline. */
    export namespace Internal {

        /**
         * Hours of a dataset changed outside a run — the auction cleared a day: [local midnight, next local midnight).
         * A run's predictions are reported with `Forecaster.API.Internal.reportRun`, which updates them itself.
         */
        export namespace ReportUpdate {

            export const Params = z.object({ name: Name })
            export type  Params = z.infer<typeof Params>

            export const Request = z.object({
                start: z.coerce.date(),
                end:   z.coerce.date(),
            }).refine((request) => request.start < request.end, { path: ["end"], message: "end must come after start" })
            export type Request = z.infer<typeof Request>

            export const Response = z.object({ update: Update.Schema })
            export type  Response = z.infer<typeof Response>
        }

        export async function reportUpdate(api: AxiosInstance, name: Name, request: z.input<typeof ReportUpdate.Request>): Promise<ReportUpdate.Response> {
            const { data } = await api.post(`/internal/datasets/${name}/updates`, request)

            return ReportUpdate.Response.parse(data)
        }
    }
}
