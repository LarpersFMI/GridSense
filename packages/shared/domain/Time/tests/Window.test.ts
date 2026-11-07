import { describe, expect, it } from "vitest"
import { Window } from "../Window"

const hour = (iso: string) => ({ at: new Date(iso) })

describe("Window.group", () => {

    it("keeps a stretch of consecutive hours together", () => {
        const hours = [hour("2026-05-09T09:00:00Z"), hour("2026-05-09T10:00:00Z"), hour("2026-05-09T11:00:00Z")]

        expect(Window.group(hours, { minHours: 2, maxHours: 6 })).toEqual([hours])
    })

    it("splits on a gap and drops pieces under minHours", () => {
        const hours = [hour("2026-05-09T09:00:00Z"), hour("2026-05-09T10:00:00Z"), hour("2026-05-09T13:00:00Z")]

        expect(Window.group(hours, { minHours: 2, maxHours: 6 })).toEqual([hours.slice(0, 2)])
    })

    it("cuts a long stretch into pieces of maxHours", () => {
        const hours = []

        for (let h = 6; h < 13; h++)
            hours.push(hour(`2026-05-09T${String(h).padStart(2, "0")}:00:00Z`))

        expect(Window.group(hours, { minHours: 1, maxHours: 3 }).map((piece) => piece.length)).toEqual([3, 3, 1])
    })

    it("doesn't join hours across local midnight", () => {
        // 20:00Z and 21:00Z on 9 May are 23:00 and 00:00 in Bucharest (UTC+3).
        const hours = [hour("2026-05-09T20:00:00Z"), hour("2026-05-09T21:00:00Z")]

        expect(Window.group(hours, { minHours: 1, maxHours: 6 })).toHaveLength(2)
    })
})

describe("Window.of", () => {

    it("spans its hours, end exclusive", () => {
        const window = Window.of([hour("2026-05-09T09:00:00Z"), hour("2026-05-09T10:00:00Z")])

        expect(window.key).toBe("20260509T0900Z-20260509T1100Z")
        expect(window.hours).toBe(2)
    })
})
