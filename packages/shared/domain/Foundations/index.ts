import * as IdMod     from "./Id"
import * as QueueMod  from "./Queue"
import * as ThreadMod from "./Thread"

/** Types every package depends on. */
export namespace Foundations {

    /** `Foundations.Id.define("X.Id")`: a concept's branded UUIDv7 id schema. */
    export import Id = IdMod.Id

    /** Queue contracts: `Foundations.Queue.define({ name, job, result, options })`. */
    export import Queue = QueueMod.Queue

    /** `Foundations.Thread.Id`: a hit's thread through the agent — its BullMQ job and its LangGraph thread. */
    export import Thread = ThreadMod.Thread

    export const uuidv7 = IdMod.uuidv7
}
