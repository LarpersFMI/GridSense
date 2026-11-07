import * as QueueMod from "./queue"

/** Runs the pipelines Python defines, on their schedules or now, as subprocesses; streams their logs live. */
export namespace PipelineRunner {

    export import Queue = QueueMod.Queue
}
