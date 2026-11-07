import { createFileRoute } from '@tanstack/react-router'
import { Page } from '@/components/Page'
import { PipelinesPage } from '@/features/pipelines/PipelinesPage'

export const Route = createFileRoute('/pipelines')({
    component: () => (
        <Page>
            <PipelinesPage />
        </Page>
    ),
})
