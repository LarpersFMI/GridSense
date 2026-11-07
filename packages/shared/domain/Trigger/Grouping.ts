import { z } from "zod"
import { Window } from "../Time/Window"
import type { Check } from "./Check"

/**
 * How matching hours become hits. `hour`: one per hour · `window`: one per stretch of consecutive matching hours
 * on one local day, cut to at most maxHours and dropped under minHours · `run`: one for all of them together.
 */
export namespace Grouping {

    export const Schema = z.discriminatedUnion("type", [
        z.object({ type: z.literal("hour") }),
        z.object({ type: z.literal("window"), minHours: z.number().int().min(1), maxHours: z.number().int().min(1) }),
        z.object({ type: z.literal("run") }),
    ])

    /** One group per future hit: its hours, and the window they span (null for `run`). */
    export interface Group {
        hours:  Check.Hour[]
        window: Window | null
    }

    export function split(grouping: Grouping, hours: Check.Hour[]): Group[] {
        const groups: Group[] = []

        switch (grouping.type) {
            case "hour":
                for (const hour of hours)
                    groups.push({ hours: [hour], window: Window.of([hour]) })

                break

            case "window":
                for (const piece of Window.group(hours, grouping))
                    groups.push({ hours: piece, window: Window.of(piece) })

                break

            case "run":
                groups.push({ hours, window: null })

                break
        }

        return groups
    }
}
export type Grouping = z.infer<typeof Grouping.Schema>
