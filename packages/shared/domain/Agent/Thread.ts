import { z } from "zod"
import { Foundations } from "../Foundations"
import { TriggerId } from "../ids"
import { Hit } from "../Trigger/Hit"
import { Playbook } from "../Trigger/Playbook"
import { Action } from "./Action"
import { Analysis } from "./Analysis"
import { Message } from "./Message"
import { Decision } from "./Decision"

/**
 * One hit through the agent's graph, its id the hit's thread id: what it decided, what it did, and every step it
 * took — the node, when, what it read and concluded. The decision log an admin (and the EU AI Act) asks for.
 */
export namespace Thread {

    export import Id = Foundations.Thread.Id

    /** running a node · paused, awaiting-review · finished: acted, dismissed or failed. */
    export const Status = z.enum(["running", "awaiting-review", "acted", "dismissed", "failed"])
    export type  Status = z.infer<typeof Status>

    /** One node of the graph, run: its name as in the graph, and what it concluded. */
    export const Step = z.object({
        node:    z.string(),
        at:      z.coerce.date(),
        summary: z.string(),
        data:    z.record(z.string(), z.unknown()),
    })
    export type Step = z.infer<typeof Step>

    /** An admin's answer to a paused thread. */
    export const Review = z.object({
        decision: z.enum(["approve", "reject"]),
        note:     z.string().nullable(),
        at:       z.coerce.date(),
    })
    export type Review = z.infer<typeof Review>

    export const Schema = z.object({
        id:        Id,
        triggerId: TriggerId,
        playbook:  Playbook.Schema,
        status:    Status,
        hit:       Hit.Schema,
        decision:  Decision.Schema.nullable(),
        analysis:  Analysis.Schema.nullable().default(null),   // the impact analysis, when the decision had one
        actions:   Action.Schema.array(),
        steps:     Step.array(),
        review:    Review.nullable(),
        messages:  Message.Schema.array().default([]),         // the operator's questions and the agent's answers
        createdAt: z.coerce.date(),
        updatedAt: z.coerce.date(),
    })
}
export type Thread = z.infer<typeof Thread.Schema>
