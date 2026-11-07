import { Trigger, type Dataset } from '@gridsense/shared/domain'

/** The column that grows as rows are appended to each dataset: a new trigger's default incremental column. */
export const INCREMENTAL_COLUMNS: Record<Dataset.Name, string> = {
    predictions: 'issue_ts',
    prices:      'ts_utc',
}

export const DEFAULT_CRON = '0 8 * * MON'

/** A new trigger as the editor starts it: on this dataset, no conditions yet. Its id is made here. */
export function createDraft(dataset: Dataset.Name): Trigger {
    return {
        id:          Trigger.createId(),
        name:        '',
        description: '',
        enabled:     true,
        on: {
            type:              'dataset',
            dataset,
            incrementalColumn: INCREMENTAL_COLUMNS[dataset],
        },
        match:      'all',
        conditions: [],
        grouping: {
            type:     'window',
            minHours: 2,
            maxHours: 6,
        },
        cooldownMinutes: 0,
    }
}
