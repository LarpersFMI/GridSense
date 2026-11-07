import type { IconName } from '@blueprintjs/core'
import type { Dataset, Trigger } from '@gridsense/shared/domain'
import { createDraft } from './draft'

/** A trigger to start from: the ones GridSense's agent needs, with thresholds to tune before saving. */
export interface TriggerTemplate {
    key:         string
    icon:        IconName
    dataset:     Dataset.Name             // the dataset it watches: the sidebar offers the templates on its own
    trigger:     Pick<Trigger, 'name' | 'description' | 'match' | 'conditions' | 'grouping' | 'cooldownMinutes'>
}

export const TRIGGER_TEMPLATES: TriggerTemplate[] = [
    {
        key:     'zero-cost-window',
        icon:    'flash',
        dataset: 'predictions',
        trigger: {
            name:        'Zero-cost window',
            description: 'Daytime hours likely to clear near zero: candidate free hours to announce.',
            match:       'all',
            conditions: [
                { dataset: 'predictions', column: 'p_near_zero', operator: '>=', value: 0.75 },
                { dataset: 'predictions', column: 'local_hour', operator: 'between', value: [9, 17] },
                { dataset: 'predictions', column: 'data_quality', operator: '==', value: 'ok' },
            ],
            grouping:        { type: 'window', minHours: 2, maxHours: 6 },
            cooldownMinutes: 1440,
        },
    },
    {
        key:     'forecast-dropped',
        icon:    'trending-down',
        dataset: 'predictions',
        trigger: {
            name:        'Forecast dropped',
            description: "A daytime hour's chance of near-zero fell sharply since the last run: an announced slot may not hold.",
            match:       'all',
            conditions: [
                { dataset: 'predictions', column: 'p_near_zero_change', operator: '<=', value: -0.15 },
                { dataset: 'predictions', column: 'local_hour', operator: 'between', value: [9, 17] },
            ],
            grouping:        { type: 'window', minHours: 1, maxHours: 6 },
            cooldownMinutes: 360,
        },
    },
    {
        key:     'degraded-data',
        icon:    'warning-sign',
        dataset: 'predictions',
        trigger: {
            name:        'Degraded data',
            description: "A run's inputs were degraded or failed checks: its forecast is less sure.",
            match:       'all',
            conditions: [
                { dataset: 'predictions', column: 'data_quality', operator: 'in', value: ['degraded', 'failed'] },
            ],
            grouping:        { type: 'run' },
            cooldownMinutes: 720,
        },
    },
    {
        key:     'evening-scarcity',
        icon:    'moon',
        dataset: 'predictions',
        trigger: {
            name:        'Evening scarcity',
            description: 'Evening hours forecast expensive: worth an alert to shift consumption away from them.',
            match:       'all',
            conditions: [
                { dataset: 'predictions', column: 'price_p50', operator: '>=', value: 150 },
                { dataset: 'predictions', column: 'local_hour', operator: 'between', value: [18, 22] },
            ],
            grouping:        { type: 'window', minHours: 1, maxHours: 5 },
            cooldownMinutes: 720,
        },
    },
    {
        key:     'forecast-miss',
        icon:    'cross-circle',
        dataset: 'prices',
        trigger: {
            name:        'Forecast miss',
            description: 'Hours we called near zero that cleared above 20 EUR/MWh at the auction: cancel the slot.',
            match:       'all',
            conditions: [
                { dataset: 'predictions', column: 'p_near_zero', operator: '>=', value: 0.7 },
                { dataset: 'prices', column: 'price_mean', operator: '>', value: 20 },
            ],
            grouping:        { type: 'hour' },
            cooldownMinutes: 0,
        },
    },
    {
        key:     'negative-prices-cleared',
        icon:    'tick-circle',
        dataset: 'prices',
        trigger: {
            name:        'Negative prices cleared',
            description: 'The auction cleared at or below zero in daytime: free hours confirmed for tomorrow.',
            match:       'all',
            conditions: [
                { dataset: 'prices', column: 'price_mean', operator: '<=', value: 0 },
                { dataset: 'prices', column: 'local_hour', operator: 'between', value: [9, 17] },
            ],
            grouping:        { type: 'window', minHours: 1, maxHours: 8 },
            cooldownMinutes: 0,
        },
    },
]

/** A new trigger from a template — or blank, without one — on this dataset; its id is made here. */
export function createFromTemplate(dataset: Dataset.Name, template: TriggerTemplate | null): Trigger {
    const draft = createDraft(dataset)

    if (template === null)
        return draft

    return {
        ...draft,
        ...structuredClone(template.trigger),
    }
}
