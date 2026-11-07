import { Callout } from '@blueprintjs/core'
import { errorMessage } from '@/SDKs/api'

interface ErrorNoticeProps {
    title: string
    error: unknown
}

export function ErrorNotice({ title, error }: ErrorNoticeProps) {
    return (
        <Callout intent='danger' title={title}>
            {errorMessage(error)}
        </Callout>
    )
}
