import * as IdMod    from "./Id"
import * as QueueMod from "./Queue"

/** Types every package depends on. */
export namespace Foundations {

    /** `Foundations.Id.define("X.Id")`: a concept's branded UUIDv7 id schema. */
    export import Id = IdMod.Id

    /** Queue contracts: `Foundations.Queue.define({ name, job, result, options })`. */
    export import Queue = QueueMod.Queue

    export const uuidv7 = IdMod.uuidv7
}
