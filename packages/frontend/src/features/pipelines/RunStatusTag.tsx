import { Spinner, Tag } from '@blueprintjs/core'
import type { Pipeline } from '@gridsense/shared/domain'

const INTENTS: Record<Pipeline.Run.Status, 'primary' | 'success' | 'danger'> = {
    running:   'primary',
    succeeded: 'success',
    failed:    'danger',
}

interface RunStatusTagProps {
    status:   Pipeline.Run.Status
    onClick?: () => void            // clickable (Blueprint's interactive tag): opens the run
}

export function RunStatusTag({ status, onClick }: RunStatusTagProps) {
    return (
        <Tag
            minimal
            intent={INTENTS[status]}
            icon={status === 'running' ? <Spinner size={12} /> : undefined}
            interactive={onClick !== undefined}
            onClick={onClick}
        >
            {status}
        </Tag>
    )
}
