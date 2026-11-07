import { z } from "zod"
import { Name } from "./Name"

/**
 * A dataset's file changed: a run appended its forecast, the auction's prices for a day were appended. It says
 * only which dataset — each trigger on it finds its own new rows, past its watermark on its incremental column.
 */
export namespace Update {

    export const Schema = z.object({
        dataset: Name,
    })
}
export type Update = z.infer<typeof Update.Schema>
