import { Dataset, Watchdog } from '@gridsense/shared/domain'
import { api } from '../../api'
import { ActionGroup, log } from '../../core'
import { RealtimeSDK } from '../../RealtimeSDK/sdk'
import type { DatasetSDKImpl } from '../sdk'

/** `DatasetSDK.actions.dataset` */
export class DatasetReadActions extends ActionGroup<DatasetSDKImpl> {

    protected readonly log = log.withContext('Dataset.Actions.Dataset')

    /** The file's columns as they are now, and the ones the Watchdog computes. */
    public async describe(name: Dataset.Name): Promise<Dataset.Description> {
        const data = await Dataset.API.describe(api, name)

        return data.description
    }

    /** The file's latest rows. */
    public async getPreview(name: Dataset.Name, query: Dataset.API.GetPreview.Query): Promise<Dataset.Preview> {
        const data = await Dataset.API.getPreview(api, name, query)

        return data.preview
    }

    /** Refreshes a dataset's previews whenever the Watchdog checks it (rows were appended), until the returned function is called. */
    public watch(): () => void {
        return RealtimeSDK.subscribeToChannel(Watchdog.Event.ACTIVITY_CHANNEL, Watchdog.Event.Check.Completed.Schema, check => {
            if (check.source.type === 'dataset')
                void this.sdk.invalidate(this.sdk.query.previews(check.source.dataset))
        })
    }
}
