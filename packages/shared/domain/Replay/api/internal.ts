import { z } from "zod"
import type { AxiosInstance } from "axios"
import { Schema } from "../Schema"

/** For the PipelineRunner: the start it hands the replay pipelines (REPLAY_START). */
export namespace Internal {

    export namespace Get {

        export const Response = z.object({ replay: Schema })
        export type  Response = z.infer<typeof Response>
    }

    export async function get(api: AxiosInstance): Promise<Get.Response> {
        const { data } = await api.get("/internal/replay")

        return Get.Response.parse(data)
    }
}
