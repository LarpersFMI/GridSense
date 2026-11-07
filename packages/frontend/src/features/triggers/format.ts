import type { Trigger } from '@gridsense/shared/domain'

const OPERATOR_LABELS: Record<Trigger.Condition.Operator, string> = {
    '>=':      '≥',
    '<=':      '≤',
    '>':       '>',
    '<':       '<',
    '==':      '=',
    '!=':      '≠',
    'between': 'between',
    'in':      'in',
}

export const formatOperator = (operator: Trigger.Condition.Operator) => OPERATOR_LABELS[operator]

/** `predictions.p_near_zero ≥ 0.75`, `predictions.local_hour between 9 and 17`. */
export function formatCondition(condition: Trigger.Condition): string {
    const column = `${condition.dataset}.${condition.column}`
    const operator = formatOperator(condition.operator)

    if (condition.operator === 'between' && Array.isArray(condition.value))
        return `${column} between ${condition.value[0]} and ${condition.value[1]}`

    if (Array.isArray(condition.value))
        return `${column} ${operator} [${condition.value.join(', ')}]`

    return `${column} ${operator} ${condition.value}`
}

export function formatOn(on: Trigger.On): string {
    if (on.type === 'schedule')
        return `cron ${on.cron}`

    return `${on.dataset} · new ${on.incrementalColumn}`
}

export function formatGrouping(grouping: Trigger.Grouping): string {
    switch (grouping.type) {
        case 'hour':
            return 'one hit per hour'

        case 'window':
            return `windows of ${grouping.minHours}–${grouping.maxHours} h`

        case 'run':
            return 'one hit per check'
    }
}

export function formatCooldown(minutes: number): string {
    if (minutes === 0)
        return 'none'

    if (minutes % 60 === 0)
        return `${minutes / 60} h`

    return `${minutes} min`
}
