import { Tag, type IconName } from '@blueprintjs/core'
import { Trigger } from '@gridsense/shared/domain'

export const PLAYBOOK_ICONS: Record<Trigger.Playbook, IconName> = {
    'announce-slot': 'flash',
    'confirm-slot':  'tick-circle',
    'cancel-slot':   'cross-circle',
    'alert':         'notifications',
}

/** What the agent does with a trigger's hits, as a tag: on trigger cards and on the agent's threads. */
export function PlaybookTag({ playbook }: { playbook: Trigger.Playbook }) {
    const { label, description } = Trigger.Playbook.DESCRIPTIONS[playbook]

    return (
        <Tag minimal round intent='primary' icon={PLAYBOOK_ICONS[playbook]} title={description}>
            {label}
        </Tag>
    )
}
