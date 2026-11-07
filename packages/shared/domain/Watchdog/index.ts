import * as QueueMod from "./queue"
import * as EventMod from "./Event"

/** Checks the admin's triggers when a dataset updates and on the clock; wakes the agent on a hit. */
export namespace Watchdog {

    export import Queue = QueueMod.Queue
    export import Event = EventMod.Event
}
