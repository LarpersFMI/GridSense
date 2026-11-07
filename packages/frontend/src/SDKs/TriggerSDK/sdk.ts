import type { Trigger } from '@gridsense/shared/domain'
import { createWithEqualityFn } from 'zustand/traditional'
import { immer } from 'zustand/middleware/immer'
import { shallow } from 'zustand/shallow'
import { BaseSDK } from '../core/BaseSDK'
import { SDK } from '../SDKManager'
import { TriggerActions } from './actions'
import { triggerSelectors } from './selectors'

/** The admin's triggers: in the store by id, shared by the list, the editor and the activity view. */
@SDK('Trigger')
export class TriggerSDKImpl extends BaseSDK<TriggerSDK.State> {

    public readonly useStore: BaseSDK.Store<TriggerSDK.State> = createWithEqualityFn(
        immer<TriggerSDK.State>(() => ({
            triggers: {},
        })),
        shallow,
    )

    public readonly actions: TriggerSDK.Actions = new TriggerActions(this)

    public readonly selectors = triggerSelectors

    public override readonly query = {
        triggers: {
            queryKey: ['triggers'] as const,
            queryFn:  () => this.actions.trigger.list(),
        },

        trigger: (id: Trigger.Id) => ({
            queryKey: ['triggers', id] as const,
            queryFn:  () => this.actions.trigger.get(id),
        }),
    }

    public override cleanup(): void {
        this.setState({
            triggers: {},
        })
    }
}

export const TriggerSDK = SDK.get<TriggerSDKImpl>('Trigger')

export namespace TriggerSDK {

    export type State = {
        triggers: Record<Trigger.Id, Trigger>
    }

    export type Actions = TriggerActions
}
