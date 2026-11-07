import * as NameMod         from "./Name"
import * as DescriptionMod  from "./Description"
import * as PredictionsMod  from "./Predictions"
import * as PricesHourlyMod from "./PricesHourly"
import * as UpdateMod       from "./Update"
import * as ApiMod          from "./api"

/**
 * The parquet files our TypeScript packages read, as the Python side writes them (src/gridsense/schemas.py).
 * Data and ML engineers add or change a dataset here when they change it there.
 */
export namespace Dataset {

    export import Name         = NameMod.Name
    export import Description  = DescriptionMod.Description
    export import Predictions  = PredictionsMod.Predictions
    export import PricesHourly = PricesHourlyMod.PricesHourly

    /** Some hours of a dataset changed: what the Watchdog checks triggers on. */
    export import Update       = UpdateMod.Update

    /** `Dataset.API.describe(api, name)` for the condition editor; `Dataset.API.Internal.reportUpdate` for Python. */
    export import API = ApiMod.API
}
