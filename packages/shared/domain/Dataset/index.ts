import * as PredictionsMod  from "./Predictions"
import * as PricesHourlyMod from "./PricesHourly"

/**
 * The parquet files our TypeScript packages read, as the Python side writes them (src/gridsense/schemas.py).
 * Data and ML engineers add or change a dataset here when they change it there.
 */
export namespace Dataset {

    export import Predictions  = PredictionsMod.Predictions
    export import PricesHourly = PricesHourlyMod.PricesHourly
}
