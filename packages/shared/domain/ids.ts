import { z } from "zod"
import { Id, uuidv7 } from "./Foundations/Id"

/**
 * Every concept's id, in one place: anything may import from here without importing the concept itself, so ids
 * never close an import cycle. Each concept re-exports its own (`Trigger.Id`, `Forecaster.Run.Id`).
 */

export const RunId = Id.define("Forecaster.Run.Id")
export type  RunId = z.infer<typeof RunId>
export const createRunId = () => uuidv7() as RunId

export const TriggerId = Id.define("Trigger.Id")
export type  TriggerId = z.infer<typeof TriggerId>
export const createTriggerId = () => uuidv7() as TriggerId

/**
 * A hit's thread through the agent: its BullMQ job and its LangGraph thread. Deterministic, not a UUID — the same
 * hit reported twice gets the same id, so it's handled once (`Trigger.Hit.getThreadId`).
 */
export const ThreadId = z.string().min(1).brand("Foundations.Thread.Id")
export type  ThreadId = z.infer<typeof ThreadId>
