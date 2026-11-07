import * as NameMod     from "./Name"
import * as SchemaMod   from "./Schema"
import * as ScheduleMod from "./Schedule"
import * as RunMod      from "./Run"
import * as EventMod    from "./Event"
import * as ApiMod      from "./api"

/**
 * A pipeline: a Python function (`gridsense.pipelines`) that appends rows to datasets — the day's prices, a forecast
 * run — and reports them, so the Watchdog checks the triggers on them. Defined in Python; when it runs is set from the
 * UI; the PipelineRunner runs it.
 */
export namespace Pipeline {

    export import Name     = NameMod.Name
    export import Schema   = SchemaMod.Schema

    /** When it runs: a cron, enabled or not. */
    export import Schedule = ScheduleMod.Schedule

    /** One run: its cause, status, what it appended. */
    export import Run      = RunMod.Run

    export import Event    = EventMod.Event

    /** `Pipeline.API` for the browser, `Pipeline.API.Internal` for the PipelineRunner. */
    export import API      = ApiMod.API
}
export type Pipeline = SchemaMod.Pipeline
