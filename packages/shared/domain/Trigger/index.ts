import * as Ids          from "../ids"
import * as OnMod        from "./On"
import * as SchemaMod    from "./Schema"
import * as ConditionMod from "./Condition"
import * as GroupingMod  from "./Grouping"
import * as CheckMod     from "./Check"
import * as HitMod       from "./Hit"
import * as PlaybookMod  from "./Playbook"
import * as EvaluateMod  from "./evaluate"
import * as ApiMod       from "./api"

/**
 * A condition an admin writes on the columns of the Forecaster's predictions or of the cleared prices, checked when
 * a dataset's hours change or on a schedule. When it holds, the Watchdog wakes the agent with a Hit; whether to act, and
 * how, is the agent's decision.
 */
export namespace Trigger {

    export import Id       = Ids.TriggerId
    export import createId = Ids.createTriggerId

    /** When it's checked: a dataset updated, or a cron. */
    export import On = OnMod.On

    /** A trigger, whole: as an admin writes it, with an id made in the browser, and as the server stores it. */
    export import Schema = SchemaMod.Schema

    /** A test on one hour, and how a trigger's tests combine (`Condition.Match`). */
    export import Condition = ConditionMod.Condition

    /** How matching hours become hits. */
    export import Grouping = GroupingMod.Grouping

    /** One check: its cause, its run, its hours. */
    export import Check = CheckMod.Check

    /** What the agent does with its hits. */
    export import Playbook = PlaybookMod.Playbook

    /** What the Watchdog hands the agent. */
    export import Hit = HitMod.Hit

    export import evaluate = EvaluateMod.evaluate

    /** `Trigger.API` for the browser, `Trigger.API.Internal` for the Watchdog. */
    export import API = ApiMod.API
}
export type Trigger = SchemaMod.Trigger
