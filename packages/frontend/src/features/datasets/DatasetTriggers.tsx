import { useState } from 'react'
import { Button, Card, NonIdealState, Spinner, Switch, Tag } from '@blueprintjs/core'
import type { Dataset, Trigger } from '@gridsense/shared/domain'
import { ErrorNotice } from '@/components/ErrorNotice'
import { TriggerSDK } from '@/SDKs/TriggerSDK/sdk'
import { WatchdogSDK } from '@/SDKs/WatchdogSDK/sdk'
import { TriggerEditor } from '../triggers/TriggerEditor'
import { TemplatePicker } from '../triggers/TemplatePicker'
import { PlaybookTag } from '../triggers/playbooks'
import { formatCondition, formatCooldown, formatGrouping } from '../triggers/format'

/** What the panel shows: the dataset's triggers, or the editor on a new or a saved one. */
type Editing =
    | { kind: 'pick' }
    | { kind: 'new'; draft: Trigger }
    | { kind: 'saved'; id: Trigger.Id }
    | null

interface DatasetTriggersProps {
    dataset: Dataset.Triggerable
}

/** The triggers that watch this dataset, with their hits; write a new one here, next to the rows it'll read. */
export function DatasetTriggers({ dataset }: DatasetTriggersProps) {
    const [editing, setEditing] = useState<Editing>(null)

    const [triggers, [triggersRequest]] = TriggerSDK.useWith(
        TriggerSDK.selectors.list,
        query => [query.triggers],
    )

    const [hitCounts] = WatchdogSDK.useWith(
        WatchdogSDK.selectors.hitCounts,
        query => [query.hits],
    )

    const watching = triggers.filter(trigger => trigger.on.type === 'dataset' && trigger.on.dataset === dataset)

    if (editing?.kind === 'pick') {
        return (
            <TemplatePicker
                dataset={dataset}
                onPick={draft => setEditing({ kind: 'new', draft })}
                onCancel={() => setEditing(null)}
            />
        )
    }

    if (editing?.kind === 'new')
        return <TriggerEditor trigger={editing.draft} isNew onDone={() => setEditing(null)} />

    if (editing?.kind === 'saved') {
        const trigger = triggers.find(candidate => candidate.id === editing.id)

        if (trigger) {
            return <TriggerEditor key={trigger.id} trigger={trigger} isNew={false} onDone={() => setEditing(null)} />
        }
    }

    return (
        <div className='flex flex-col gap-3'>
            <div className='flex items-center justify-between'>
                <h4 className='bp6-heading m-0'>Triggers on {dataset}</h4>
                <Button
                    intent='primary'
                    icon='plus'
                    text='New trigger'
                    onClick={() => setEditing({ kind: 'pick' })}
                />
            </div>

            {triggersRequest.isError && <ErrorNotice title="Couldn't load the triggers" error={triggersRequest.error} />}

            {triggersRequest.isPending && triggers.length === 0 && <Spinner />}

            {triggersRequest.isSuccess && watching.length === 0 && (
                <NonIdealState
                    icon='antenna'
                    title={`Nothing watches ${dataset} yet`}
                    description='A trigger reads the rows appended to it and hands the agent the hours that match.'
                />
            )}

            {watching.map(trigger => (
                <TriggerCard
                    key={trigger.id}
                    trigger={trigger}
                    hits={hitCounts[trigger.id] ?? 0}
                    onEdit={() => setEditing({ kind: 'saved', id: trigger.id })}
                />
            ))}
        </div>
    )
}

interface TriggerCardProps {
    trigger: Trigger
    hits:    number
    onEdit:  () => void
}

function TriggerCard({ trigger, hits, onEdit }: TriggerCardProps) {
    function handleEnabledChange() {
        void TriggerSDK.actions.trigger.setEnabled(trigger, !trigger.enabled)
    }

    return (
        <Card compact className='flex flex-col gap-2'>
            <div className='flex items-start justify-between gap-2'>
                <div>
                    <div className='font-semibold'>{trigger.name}</div>
                    <div className='text-xs text-gray-500'>{trigger.description}</div>
                </div>
                <div className='flex items-center gap-2'>
                    <Tag round intent={hits > 0 ? 'warning' : 'none'}>{hits} hits</Tag>
                    <Switch checked={trigger.enabled} onChange={handleEnabledChange} className='mb-0' />
                </div>
            </div>

            <div className='font-mono text-xs'>
                {trigger.conditions.length === 0 && <span className='text-gray-400'>every new hour</span>}
                {trigger.conditions.map((condition, index) => (
                    <div key={index}>
                        {index > 0 && <span className='text-gray-400'>{trigger.match === 'all' ? 'and ' : 'or '}</span>}
                        {formatCondition(condition)}
                    </div>
                ))}
            </div>

            <div className='flex items-center justify-between'>
                <div className='flex items-center gap-2'>
                    <PlaybookTag playbook={trigger.playbook} />
                    <span className='text-xs text-gray-500'>
                        {formatGrouping(trigger.grouping)} · cooldown {formatCooldown(trigger.cooldownMinutes)}
                    </span>
                </div>
                <Button icon='edit' text='Edit' variant='minimal' size='small' onClick={onEdit} />
            </div>
        </Card>
    )
}
