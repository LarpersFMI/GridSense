import * as SchemaMod from "./Schema"
import * as ApiMod    from "./api"

/**
 * The replay: the trained models run day by day over a past period, for rehearsing and showing the demo. Its start is
 * set from the UI; one step is a `forecast` run then a `prices` run; a reset starts it over.
 */
export namespace Replay {

    export import LocalDate = SchemaMod.LocalDate
    export import Schema    = SchemaMod.Schema
    export import State     = SchemaMod.State
    export import RANGES    = SchemaMod.RANGES

    /** `Replay.API` for the browser, `Replay.API.Internal` for the PipelineRunner. */
    export import API       = ApiMod.API
}
export type Replay = SchemaMod.Replay
