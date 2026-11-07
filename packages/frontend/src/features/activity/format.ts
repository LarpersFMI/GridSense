import type { Trigger } from '@gridsense/shared/domain'
import { formatLocal } from '@/utils/format'

export { formatClock, formatLocal, formatWindow } from '@/utils/format'

/** `prices up to Sat 16 May, 23:00` — the new rows a check read — or `schedule`. */
export function formatCause(cause: Trigger.Check.Cause): string {
    if (cause.type === 'schedule')
        return `schedule, ${formatLocal(cause.firedAt)}`

    return `${cause.dataset} up to ${formatLocal(cause.upTo)}`
}
