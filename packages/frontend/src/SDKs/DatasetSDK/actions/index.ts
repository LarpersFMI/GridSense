import { ActionGroup, log } from '../../core'
import type { DatasetSDKImpl } from '../sdk'
import { DatasetReadActions } from './dataset'

/** `DatasetSDK.actions`: its groups, by what they act on. */
export class DatasetActions extends ActionGroup<DatasetSDKImpl> {

    protected readonly log = log.withContext('Dataset.Actions')

    public readonly dataset = new DatasetReadActions(this.sdk)
}
