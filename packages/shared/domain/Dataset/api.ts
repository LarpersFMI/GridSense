import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Description } from "./Description"
import { Name } from "./Name"
import { Preview } from "./Preview"
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

    /** The latest rows, newest first by `orderBy` (default: the file's first timestamp column). */
    export namespace GetPreview {

        export const Params = z.object({ name: Name })
        export type  Params = z.infer<typeof Params>

        export const Query = z.object({
            limit:   z.coerce.number().int().min(1).max(1000).default(200),
            orderBy: z.string().min(1).optional(),
        })
        export type Query = z.infer<typeof Query>

        export const Response = z.object({ preview: Preview.Schema })
        export type  Response = z.infer<typeof Response>
    }

    export async function getPreview(api: AxiosInstance, name: Name, query: z.input<typeof GetPreview.Query> = {}): Promise<GetPreview.Response> {
        const { data } = await api.get(`/api/datasets/${name}/preview`, { params: query })

        return GetPreview.Response.parse(data)
    }

    export async function describe(api: AxiosInstance, name: Name): Promise<Describe.Response> {
        const { data } = await api.get(`/api/datasets/${name}/schema`)

        return Describe.Response.parse(data)
    }

    /** For the Python pipeline. */
    export namespace Internal {

        /**
         * Rows were appended to a dataset's file outside a run — the auction's prices for a day. Call it once they're
         * fully written. A run's predictions are reported with `Forecaster.API.Internal.reportRun`, which updates them itself.
         */
        export namespace ReportUpdate {

            export const Params = z.object({ name: Name })
            export type  Params = z.infer<typeof Params>

            export const Response = z.object({ update: Update.Schema })
            export type  Response = z.infer<typeof Response>
        }

        export async function reportUpdate(api: AxiosInstance, name: Name): Promise<ReportUpdate.Response> {
            const { data } = await api.post(`/internal/datasets/${name}/updates`)

            return ReportUpdate.Response.parse(data)
        }
    }
}
