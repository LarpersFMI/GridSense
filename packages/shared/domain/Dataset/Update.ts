import { z } from "zod"
import { RunId } from "../ids"
import { Window } from "../Time/Window"
import { Name } from "./Name"

/**
 * Some hours of a dataset changed: a run wrote its forecast, the auction cleared a day. The Watchdog checks the
 * triggers on that dataset against those hours.
 */
export namespace Update {

    export const Schema = z.object({
        dataset: Name,
        start:   z.coerce.date(),
        end:     z.coerce.date(),               // exclusive
        runId:   RunId.nullable(),              // predictions: the run that wrote them; otherwise null
    }).refine((update) => update.start < update.end, { path: ["end"], message: "end must come after start" })

    /** `predictions_<runId>` · `prices_<window key>`: its queue job's id, so the same update reported twice is checked once. */
    export function getKey(update: Update): string {
        if (update.runId !== null)
            return `${update.dataset}_${update.runId}`

        return `${update.dataset}_${Window.getKey(update.start, update.end)}`
    }
}
export type Update = z.infer<typeof Update.Schema>
