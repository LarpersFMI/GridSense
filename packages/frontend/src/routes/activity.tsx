import { createFileRoute } from '@tanstack/react-router'
import { Page } from '@/components/Page'
import { ActivityPage } from '@/features/activity/ActivityPage'

export const Route = createFileRoute('/activity')({
    component: () => (
        <Page>
            <ActivityPage />
        </Page>
    ),
})
