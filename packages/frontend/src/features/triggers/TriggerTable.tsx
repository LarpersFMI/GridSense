import { Button, HTMLTable, NonIdealState, Spinner, Switch, Tag } from '@blueprintjs/core'
import { Link } from '@tanstack/react-router'
import type { Trigger } from '@gridsense/shared/domain'
import { ErrorNotice } from '@/components/ErrorNotice'
import { TriggerSDK } from '@/SDKs/TriggerSDK/sdk'
import { WatchdogSDK } from '@/SDKs/WatchdogSDK/sdk'
import { formatCondition, formatCooldown, formatGrouping, formatOn } from './format'

/** Every trigger: what it watches, its conditions, its hits so far; switch one off, or open it. */
export function TriggerTable() {
    const [triggers, [triggersRequest]] = TriggerSDK.useWith(
        TriggerSDK.selectors.list,
        query => [query.triggers],
    )

    const [hitCounts] = WatchdogSDK.useWith(
        WatchdogSDK.selectors.hitCounts,
        query => [query.hits],
    )

    return (
        <div className='flex flex-col gap-4'>
            <div className='flex items-center justify-between'>
                <h2 className='bp6-heading m-0'>Triggers</h2>
                <Link to='/triggers/$id' params={{ id: 'new' }}>
                    <Button intent='primary' icon='plus' text='New trigger' />
                </Link>
            </div>

            {triggersRequest.isError && (
                <ErrorNotice title="Couldn't load the triggers" error={triggersRequest.error} />
            )}

            {triggersRequest.isPending && triggers.length === 0 && <Spinner />}

            {triggersRequest.isSuccess && triggers.length === 0 && (
                <NonIdealState
                    icon='antenna'
                    title='No triggers yet'
                    description='A trigger watches a dataset and hands the agent the hours that match.'
                />
            )}

            {triggers.length > 0 && (
                <HTMLTable className='w-full bg-white' interactive>
                    <thead>
                        <tr>
                            <th>Trigger</th>
                            <th>Checked on</th>
                            <th>Conditions</th>
                            <th>Hits</th>
                            <th>On</th>
                        </tr>
                    </thead>
                    <tbody>
                        {triggers.map(trigger => (
                            <TriggerRow
                                key={trigger.id}
                                trigger={trigger}
                                hits={hitCounts[trigger.id] ?? 0}
                            />
                        ))}
                    </tbody>
                </HTMLTable>
            )}
        </div>
    )
}

interface TriggerRowProps {
    trigger: Trigger
    hits:    number
}

function TriggerRow({ trigger, hits }: TriggerRowProps) {
    function handleEnabledChange() {
        void TriggerSDK.actions.trigger.setEnabled(trigger, !trigger.enabled)
    }

    return (
        <tr>
            <td>
                <Link to='/triggers/$id' params={{ id: trigger.id }} className='font-semibold'>
                    {trigger.name}
                </Link>
                <div className='text-xs text-gray-500'>{trigger.description}</div>
            </td>
            <td>
                <Tag minimal>{formatOn(trigger.on)}</Tag>
                <div className='mt-1 text-xs text-gray-500'>
                    {formatGrouping(trigger.grouping)} · cooldown {formatCooldown(trigger.cooldownMinutes)}
                </div>
            </td>
            <td>
                {trigger.conditions.length === 0 && <span className='text-gray-400'>always holds</span>}
                {trigger.conditions.map((condition, index) => (
                    <div key={index} className='font-mono text-xs'>
                        {index > 0 && <span className='text-gray-400'>{trigger.match === 'all' ? 'and ' : 'or '}</span>}
                        {formatCondition(condition)}
                    </div>
                ))}
            </td>
            <td>
                <Tag round intent={hits > 0 ? 'warning' : 'none'}>{hits}</Tag>
            </td>
            <td>
                <Switch
                    checked={trigger.enabled}
                    onChange={handleEnabledChange}
                    className='mb-0'
                />
            </td>
        </tr>
    )
}
