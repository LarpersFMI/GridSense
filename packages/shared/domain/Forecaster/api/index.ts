import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Run } from "../Run"
import * as InternalMod from "./internal"

/** The Forecaster's runs over HTTP, for the browser. The pipeline's and the Watchdog's are `Internal`. */
export namespace API {

    export import Internal = InternalMod.Internal

    /** Newest first. */
    export namespace ListRuns {

        export const Query = z.object({
            limit: z.coerce.number().int().min(1).max(200).default(50),
        })
        export type  Query = z.infer<typeof Query>

        export const Response = z.object({ runs: Run.Schema.array() })
        export type  Response = z.infer<typeof Response>
    }

    export async function listRuns(api: AxiosInstance, query: z.input<typeof ListRuns.Query> = {}): Promise<ListRuns.Response> {
        const { data } = await api.get("/api/runs", { params: query })

        return ListRuns.Response.parse(data)
    }
}
