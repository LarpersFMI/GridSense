import { createFileRoute } from '@tanstack/react-router'
import { Page } from '@/components/Page'
import { TriggerTable } from '@/features/triggers/TriggerTable'

export const Route = createFileRoute('/triggers/')({
    component: () => (
        <Page>
            <TriggerTable />
        </Page>
    ),
})
