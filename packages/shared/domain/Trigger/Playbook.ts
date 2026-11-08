import { z } from "zod"

/**
 * What the agent does with a trigger's hits. The trigger says when; the playbook says what — the agent's graph routes
 * each hit by it.
 */
export namespace Playbook {

    export const Schema = z.enum(["announce-slot", "confirm-slot", "cancel-slot", "alert"])
    export type  Schema = z.infer<typeof Schema>

    export const DESCRIPTIONS: Record<Schema, { label: string; description: string }> = {
        "announce-slot": {
            label:       "Announce free hours",
            description: "Propose the window as zero-cost hours for customers: Likely goes out, Possible waits for an admin.",
        },
        "confirm-slot": {
            label:       "Confirm free hours",
            description: "The auction cleared cheap: confirm the announced slot, or announce it now if none was.",
        },
        "cancel-slot": {
            label:       "Cancel free hours",
            description: "The slot no longer holds: an admin approves cancelling what was announced over the window.",
        },
        "alert": {
            label:       "Alert",
            description: "Tell the right team (trading desk, data owner) what happened; no customer is affected.",
        },
    }
}
export type Playbook = Playbook.Schema
