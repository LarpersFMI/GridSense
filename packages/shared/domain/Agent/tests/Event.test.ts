import { describe, expect, it } from "vitest"
import { Foundations } from "../../Foundations"
import { Trigger } from "../../Trigger/Trigger"
import { Event } from "../Event"

const threadId = Foundations.Thread.Id.parse("trigger_20260509T0600Z-20260509T1100Z_run-1")

describe("Agent.Event", () => {

    it("addresses a thread's events to its own channel", () => {
        expect(Event.getThreadChannel(threadId)).toBe(`agent:thread:${threadId}`)
    })

    it("builds an event its schema accepts once the publisher adds the channel", () => {
        const event = {
            ...Event.create("agent:thread:updated", {
                threadId,
                triggerId: Trigger.createId(),
                status:    "running",
                step:      "decide",
                updatedAt: new Date("2026-05-07T07:01:00Z"),
            }),
            channel: Event.getThreadChannel(threadId),
        }

        expect(Event.Schema.parse(event).type).toBe("agent:thread:updated")
    })
})
