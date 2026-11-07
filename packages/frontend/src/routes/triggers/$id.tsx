import { Spinner } from '@blueprintjs/core'
import { createFileRoute } from '@tanstack/react-router'
import { Trigger } from '@gridsense/shared/domain'
import { ErrorNotice } from '@/components/ErrorNotice'
import { Page } from '@/components/Page'
import { TriggerEditor } from '@/features/triggers/TriggerEditor'
import { createDraft } from '@/features/triggers/draft'
import { TriggerSDK } from '@/SDKs/TriggerSDK/sdk'

/** `/triggers/new` writes a new trigger; `/triggers/<id>` edits a saved one. */
export const Route = createFileRoute('/triggers/$id')({
    component: TriggerPage,
})

function TriggerPage() {
    const { id } = Route.useParams()

    if (id === 'new') {
        return (
            <Page>
                <TriggerEditor trigger={createDraft('predictions')} isNew />
            </Page>
        )
    }

    return (
        <Page>
            <SavedTrigger id={Trigger.Id.parse(id)} />
        </Page>
    )
}

function SavedTrigger({ id }: { id: Trigger.Id }) {
    const [trigger, [triggerRequest]] = TriggerSDK.useWith(
        TriggerSDK.selectors.byId(id),
        query => [query.trigger(id)],
    )

    if (triggerRequest.isError)
        return <ErrorNotice title="Couldn't load the trigger" error={triggerRequest.error} />

    if (trigger === null)
        return <Spinner />

    return <TriggerEditor key={trigger.id} trigger={trigger} isNew={false} />
}
