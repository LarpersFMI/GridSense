import type { Replay } from '@gridsense/shared/domain'
import { createWithEqualityFn } from 'zustand/traditional'
import { immer } from 'zustand/middleware/immer'
import { shallow } from 'zustand/shallow'
import { BaseSDK } from '../core/BaseSDK'
import { SDK } from '../SDKManager'
import { ReplayActions } from './actions'

/**
 * The replay: where it starts and where it is, a step (forecast then prices) and a reset. One small object for one
 * panel: query cache only, no store; refreshed whenever a pipeline run ends.
 */
@SDK('Replay')
export class ReplaySDKImpl extends BaseSDK<ReplaySDK.State> {

    public readonly useStore: BaseSDK.Store<ReplaySDK.State> = createWithEqualityFn(
        immer<ReplaySDK.State>(() => ({})),
        shallow,
    )

    public readonly actions: ReplaySDK.Actions = new ReplayActions(this)

    public override readonly query = {
        replay: {
            queryKey: ['replay'] as const,
            queryFn:  (): Promise<Replay.State> => this.actions.replay.get(),
        },
    }

    public override cleanup(): void {}
}

export const ReplaySDK = SDK.get<ReplaySDKImpl>('Replay')

export namespace ReplaySDK {

    export type State = Record<string, never>

    export type Actions = ReplayActions
}
