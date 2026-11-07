import { ActionGroup, log } from '../../core'
import type { ForecasterSDKImpl } from '../sdk'
import { RunActions } from './run'

/** `ForecasterSDK.actions`: its groups, by what they act on. */
export class ForecasterActions extends ActionGroup<ForecasterSDKImpl> {

    protected readonly log = log.withContext('Forecaster.Actions')

    public readonly run = new RunActions(this.sdk)
}
