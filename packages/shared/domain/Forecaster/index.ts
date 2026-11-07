import * as RunMod   from "./Run"
import * as EventMod from "./Event"

/** Our prediction model: forecasts, 1–7 days ahead, how likely each hour is to clear near zero, and its price range. */
export namespace Forecaster {

    export import Run   = RunMod.Run
    export import Event = EventMod.Event

    export const HORIZON_DAYS = [1, 2, 3, 4, 5, 6, 7] as const
}
