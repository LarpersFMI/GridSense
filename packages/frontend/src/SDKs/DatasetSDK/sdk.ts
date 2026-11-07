import type { Dataset } from '@gridsense/shared/domain'
import { keepPreviousData } from '@tanstack/react-query'
import { createWithEqualityFn } from 'zustand/traditional'
import { immer } from 'zustand/middleware/immer'
import { shallow } from 'zustand/shallow'
import { BaseSDK } from '../core/BaseSDK'
import { SDK } from '../SDKManager'
import { DatasetActions } from './actions'

// A file's columns change only when the Python side changes its schema.
const DESCRIBE_STALE_TIME = 60_000

// Rows are appended while a replay or the pipeline runs; a Watchdog check on the dataset refreshes it sooner.
const PREVIEW_STALE_TIME = 10_000

const PREVIEW_ROWS = 200

// The preview's limit (Dataset.API.GetPreview): about six weeks of hourly prices, or a run's 168 hours several times over.
const CHART_ROWS = 1000

/**
 * The datasets as the viewer and the condition editor read them: columns and latest rows. Read-only, each for one
 * screen and its parameters: query cache only, no store.
 */
@SDK('Dataset')
export class DatasetSDKImpl extends BaseSDK<DatasetSDK.State> {

    public readonly useStore: BaseSDK.Store<DatasetSDK.State> = createWithEqualityFn(
        immer<DatasetSDK.State>(() => ({})),
        shallow,
    )

    public readonly actions: DatasetSDK.Actions = new DatasetActions(this)

    public override readonly query = {
        describe: (name: Dataset.Name) => ({
            queryKey:  ['datasets', name, 'schema'] as const,
            queryFn:   () => this.actions.dataset.describe(name),
            staleTime: DESCRIBE_STALE_TIME,
        }),

        /** Every preview of a dataset, whatever its order: what a check on it invalidates. */
        previews: (name: Dataset.Name) => ({
            queryKey: ['datasets', name, 'preview'] as const,
        }),

        preview: (name: Dataset.Name, orderBy: string | null) => ({
            queryKey:  ['datasets', name, 'preview', orderBy] as const,
            queryFn:   () => this.actions.dataset.getPreview(name, { limit: PREVIEW_ROWS, orderBy: orderBy ?? undefined }),
            staleTime: PREVIEW_STALE_TIME,
        }),

        /** The most rows the preview gives, newest first by `orderBy`: what a chart plots. Under `previews`, so a check refreshes it. */
        chartRows: (name: Dataset.Name, orderBy: string) => ({
            queryKey:        ['datasets', name, 'preview', 'chart', orderBy] as const,
            queryFn:         () => this.actions.dataset.getPreview(name, { limit: CHART_ROWS, orderBy }),
            staleTime:       PREVIEW_STALE_TIME,
            placeholderData: keepPreviousData,
        }),
    }

    public override cleanup(): void {}
}

export const DatasetSDK = SDK.get<DatasetSDKImpl>('Dataset')

export namespace DatasetSDK {

    export type State = Record<string, never>

    export type Actions = DatasetActions
}
