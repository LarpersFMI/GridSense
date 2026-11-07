import { ActionGroup, log } from '../../core'
import type { PipelineSDKImpl } from '../sdk'
import { PipelineScheduleActions } from './pipeline'
import { RunActions } from './run'

/** `PipelineSDK.actions`: its groups, by what they act on. */
export class PipelineActions extends ActionGroup<PipelineSDKImpl> {

    protected readonly log = log.withContext('Pipeline.Actions')

    public readonly pipeline = new PipelineScheduleActions(this.sdk)

    public readonly run = new RunActions(this.sdk)
}
