import * as SignalMod from "./Signal"
import * as QueueMod  from "./queue"

/** Checks the admin's triggers against the Forecaster's runs, the auction and the clock; wakes the agent on a hit. */
export namespace Watchdog {

    export import Signal = SignalMod.Signal
    export import Queue  = QueueMod.Queue
}
