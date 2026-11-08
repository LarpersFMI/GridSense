import { describe, expect, it } from "vitest"
import { Foundations } from "../../Foundations"
import { Trigger } from "../../Trigger"
import { Event } from "../Event"

const threadId = Foundations.Thread.Id.parse("trigger_20260509T0600Z-20260509T1100Z_run-1")

describe("Agent.Event", () => {

    it("builds a thread event its schema accepts once the publisher adds the channel", () => {
        const event = {
            ...Event.create("agent:thread:updated", {
                thread: {
                    id:        threadId,
                    triggerId: Trigger.createId(),
                    playbook:  "announce-slot",
                    status:    "running",
                    hit: {
                        triggerId:    Trigger.createId(),
                        cause:        { type: "schedule", firedAt: new Date("2026-05-07T07:00:00Z") },
                        runId:        null,
                        window:       null,
                        matchedHours: 0,
                        evidence:     {},
                    },
                    decision:  null,
                    analysis:  null,
                    messages:  [],
                    actions:   [],
                    steps:     [],
                    review:    null,
                    createdAt: new Date("2026-05-07T07:01:00Z"),
                    updatedAt: new Date("2026-05-07T07:01:00Z"),
                },
            }),
            channel: Event.THREADS_CHANNEL,
        }

        expect(Event.Schema.parse(event).type).toBe("agent:thread:updated")
    })
})
