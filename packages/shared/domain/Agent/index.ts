import * as QueueMod from "./queue"

/** Turns a trigger's hit into a decision and actions, pausing for an admin when it isn't sure. */
export namespace Agent {

    export import Queue = QueueMod.Queue
}
