import * as ActionMod   from "./Action"
import * as AnalysisMod from "./Analysis"
import * as ApiMod      from "./api"
import * as DecisionMod from "./Decision"
import * as EventMod    from "./Event"
import * as GraphMod    from "./Graph"
import * as MessageMod  from "./Message"
import * as QueueMod    from "./queue"
import * as SlotMod     from "./Slot"
import * as ThreadMod   from "./Thread"

/**
 * Turns a trigger's hit into a decision and actions, as a LangGraph thread: load, decide on the model's numbers,
 * pause for an admin when unsure, act. What it does with a hit is the trigger's `Trigger.Playbook`.
 */
export namespace Agent {

    export import Queue    = QueueMod.Queue
    export import Event    = EventMod.Event
    export import Thread   = ThreadMod.Thread
    export import Decision = DecisionMod.Decision
    export import Action   = ActionMod.Action
    export import Analysis = AnalysisMod.Analysis
    export import Slot     = SlotMod.Slot
    export import Graph    = GraphMod.Graph
    export import Message  = MessageMod.Message
    export import API      = ApiMod.API
}
