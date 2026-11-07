/** Romanian wall-clock time. Timestamps are stored in UTC; days, hours and windows are read in local time. */
export namespace Local {

    export const TIME_ZONE = "Europe/Bucharest"

    const FORMAT = new Intl.DateTimeFormat("en-CA", {
        timeZone:  TIME_ZONE,
        year:      "numeric",
        month:     "2-digit",
        day:       "2-digit",
        hour:      "2-digit",
        hourCycle: "h23",
    })

    /** A UTC instant as its local day (`2026-05-09`) and hour (0–23). DST days have 23 or 25 hours. */
    export function of(instant: Date): { day: string; hour: number } {
        const parts: Record<string, string> = {}

        for (const part of FORMAT.formatToParts(instant))
            parts[part.type] = part.value

        return {
            day:  `${parts.year}-${parts.month}-${parts.day}`,
            hour: Number(parts.hour),
        }
    }

    /** The UTC instant a local day (`2026-05-09`) starts at: its 00:00 in Bucharest, UTC+2 or UTC+3. */
    export function startOfDay(day: string): Date {
        const midnightUtc = Date.parse(`${day}T00:00:00Z`)

        for (const offsetHours of [3, 2]) {
            const instant = new Date(midnightUtc - offsetHours * 60 * 60_000)
            const local = of(instant)

            if (local.day === day && local.hour === 0)
                return instant
        }

        throw new Error(`No local midnight found for ${day}`)
    }

    /** Monday = 0 … Sunday = 6, for a local day `2026-05-09`. */
    export const getWeekday = (day: string) => (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7
}
