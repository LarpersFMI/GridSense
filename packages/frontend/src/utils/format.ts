import { Time } from '@gridsense/shared/domain'

const DAY = new Intl.DateTimeFormat('en-GB', {
    timeZone: Time.Local.TIME_ZONE,
    weekday:  'short',
    day:      'numeric',
    month:    'short',
})

const HOUR = new Intl.DateTimeFormat('en-GB', {
    timeZone: Time.Local.TIME_ZONE,
    hour:     '2-digit',
    minute:   '2-digit',
})

const CLOCK = new Intl.DateTimeFormat('en-GB', {
    hour:   '2-digit',
    minute: '2-digit',
    second: '2-digit',
})

const COUNT = new Intl.NumberFormat('en-GB')

/** `Sat 16 May, 10:00`, Romanian time. */
export const formatLocal = (instant: Date) => `${DAY.format(instant)}, ${HOUR.format(instant)}`

/** `Sat 16 May, 10:00–15:00`, Romanian time; the end is exclusive. */
export function formatWindow(window: Time.Window): string {
    return `${DAY.format(window.start)}, ${HOUR.format(window.start)}–${HOUR.format(window.end)}`
}

/** When something happened here, on this machine's clock. */
export const formatClock = (instant: Date) => CLOCK.format(instant)

/** `13,937` */
export const formatCount = (count: number) => COUNT.format(count)
