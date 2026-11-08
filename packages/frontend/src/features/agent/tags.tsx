import { Tag, type Intent } from '@blueprintjs/core'
import type { Agent } from '@gridsense/shared/domain'

const LABEL_INTENT: Record<Agent.Decision.Label, Intent> = {
    confirmed: 'success',
    likely:    'success',
    possible:  'warning',
    cancel:    'danger',
    alert:     'primary',
    none:      'none',
}

const LABEL_TEXT: Record<Agent.Decision.Label, string> = {
    confirmed: 'Confirmed',
    likely:    'Likely',
    possible:  'Possible',
    cancel:    'Cancel',
    alert:     'Alert',
    none:      'Nothing to do',
}

const STATUS: Record<Agent.Thread.Status, { text: string; intent: Intent; icon: 'refresh' | 'hand' | 'tick' | 'cross' | 'error' }> = {
    'running':         { text: 'Running', intent: 'primary', icon: 'refresh' },
    'awaiting-review': { text: 'Waiting for you', intent: 'warning', icon: 'hand' },
    'acted':           { text: 'Acted', intent: 'success', icon: 'tick' },
    'dismissed':       { text: 'Dismissed', intent: 'none', icon: 'cross' },
    'failed':          { text: 'Failed', intent: 'danger', icon: 'error' },
}

/** The decision's label: Likely and Confirmed green, Possible amber (an operator decides), Cancel red. */
export function DecisionTag({ label }: { label: Agent.Decision.Label }) {
    return <Tag minimal intent={LABEL_INTENT[label]}>{LABEL_TEXT[label]}</Tag>
}

export function StatusTag({ status }: { status: Agent.Thread.Status }) {
    const { text, intent, icon } = STATUS[status]

    return <Tag minimal round intent={intent} icon={icon}>{text}</Tag>
}

// Purple: the one color for text an LLM wrote, everywhere in the app. Inline: Blueprint's Tag styles beat Tailwind's.
const AI_STYLE = { background: '#ede9fe', color: '#5b21b6' }

/** Marks text Claude wrote (from the agent's tools); numbers and decisions never carry it. */
export function AiBadge({ text = 'Written by Claude' }: { text?: string }) {
    return <Tag minimal round icon='clean' style={AI_STYLE}>{text}</Tag>
}
