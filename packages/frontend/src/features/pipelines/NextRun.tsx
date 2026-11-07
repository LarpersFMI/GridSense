import { useEffect, useState } from 'react'
import { Tag } from '@blueprintjs/core'
import { PipelineSDK } from '@/SDKs/PipelineSDK/sdk'

// While a run is due and not yet moved on, the next one is asked again this often.
const OVERDUE_REFETCH_MS = 3_000

/** The clock, once a second. */
export function useNow(): Date {
    const [now, setNow] = useState(() => new Date())

    useEffect(() => {
        const interval = setInterval(() => setNow(new Date()), 1_000)

        return () => clearInterval(interval)
    }, [])

    return now
}

/** `0:42`, `12:05`, `3 h 05 min`. */
export function formatCountdown(milliseconds: number): string {
    const seconds = Math.max(0, Math.ceil(milliseconds / 1000))

    if (seconds >= 3600)
        return `${Math.floor(seconds / 3600)} h ${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')} min`

    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

/**
 * Time to a pipeline's next scheduled run, ticking. Once it's due, the PipelineRunner moves its scheduler on: the
 * pipelines are read again until the next run is in the future.
 */
export function NextRun({ at }: { at: Date }) {
    const now = useNow()
    const remaining = at.getTime() - now.getTime()
    const isDue = remaining <= 0

    useEffect(() => {
        if (!isDue)
            return

        const interval = setInterval(() => void PipelineSDK.invalidate(PipelineSDK.query.pipelines), OVERDUE_REFETCH_MS)

        void PipelineSDK.invalidate(PipelineSDK.query.pipelines)

        return () => clearInterval(interval)
    }, [isDue])

    if (isDue)
        return <Tag minimal intent='primary' icon='time'>due now</Tag>

    return (
        <Tag minimal intent='success' icon='time' title={at.toLocaleString()}>
            <span className='font-mono'>next in {formatCountdown(remaining)}</span>
        </Tag>
    )
}
