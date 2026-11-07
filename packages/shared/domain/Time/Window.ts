import { z } from "zod"
import { Local } from "./Local"

const HOUR_MS = 60 * 60_000

/** Consecutive hours on one local day: what a trigger's hit is about, and what the agent announces. */
export namespace Window {

    /** `20260509T0900Z-20260509T1200Z`: the same hours across runs, so a later run's hit matches an earlier one. */
    export const Key = z.string().regex(/^\d{8}T\d{4}Z-\d{8}T\d{4}Z$/).brand("Time.Window.Key")
    export type  Key = z.infer<typeof Key>

    export const Schema = z.object({
        key:   Key,
        start: z.coerce.date(),
        end:   z.coerce.date(),                     // exclusive
        hours: z.number().int().positive(),
    })

    /** `2026-05-09T09:00:00.000Z` → `20260509T0900Z`. */
    const formatKeyInstant = (instant: Date) => {
        const iso = instant.toISOString()

        return `${iso.slice(0, 4)}${iso.slice(5, 7)}${iso.slice(8, 10)}T${iso.slice(11, 13)}${iso.slice(14, 16)}Z`
    }

    export const getKey = (start: Date, end: Date) => `${formatKeyInstant(start)}-${formatKeyInstant(end)}` as Key

    /** The window these hours span, given in order. */
    export function of(hours: readonly { at: Date }[]): Window {
        const start = hours[0].at
        const end = new Date(hours[hours.length - 1].at.getTime() + HOUR_MS)

        return {
            key:   getKey(start, end),
            start,
            end,
            hours: hours.length,
        }
    }

    /**
     * Splits hours into windows: each stretch of consecutive hours within one local day, cut into
     * pieces of at most maxHours. Pieces shorter than minHours are dropped.
     */
    export function group<T extends { at: Date }>(items: readonly T[], options: { minHours: number; maxHours: number }): T[][] {
        const sorted = [...items]

        sorted.sort((a, b) => a.at.getTime() - b.at.getTime())

        const stretches: T[][] = []

        for (const item of sorted) {
            const current = stretches[stretches.length - 1]

            if (current === undefined) {
                stretches.push([item])
                continue
            }

            const previous = current[current.length - 1]
            const consecutive = item.at.getTime() - previous.at.getTime() === HOUR_MS
            const sameDay = Local.of(item.at).day === Local.of(previous.at).day

            if (consecutive && sameDay)
                current.push(item)
            else
                stretches.push([item])
        }

        const windows: T[][] = []

        for (const stretch of stretches)
            for (let start = 0; start < stretch.length; start += options.maxHours) {
                const piece = stretch.slice(start, start + options.maxHours)

                if (piece.length >= options.minHours)
                    windows.push(piece)
            }

        return windows
    }
}
export type Window = z.infer<typeof Window.Schema>
