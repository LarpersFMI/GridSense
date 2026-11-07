import type { Forecaster } from '@gridsense/shared/domain'
import { createWithEqualityFn } from 'zustand/traditional'
import { immer } from 'zustand/middleware/immer'
import { shallow } from 'zustand/shallow'
import { BaseSDK } from '../core/BaseSDK'
import { SDK } from '../SDKManager'
import { ForecasterActions } from './actions'

const RUNS_SHOWN = 50

/** The Forecaster's runs, as Python reports them: listed once, then kept live from `forecaster:runs`. */
@SDK('Forecaster')
export class ForecasterSDKImpl extends BaseSDK<ForecasterSDK.State> {

    public readonly useStore: BaseSDK.Store<ForecasterSDK.State> = createWithEqualityFn(
        immer<ForecasterSDK.State>(() => ({
            runs: {},
        })),
        shallow,
    )

    public readonly actions: ForecasterSDK.Actions = new ForecasterActions(this)

    public readonly selectors = {

        /** Newest first. */
        runs: (state: ForecasterSDK.State): Forecaster.Run[] => {
            const runs = Object.values(state.runs)

            runs.sort((a, b) => b.issueTs.getTime() - a.issueTs.getTime())

            return runs
        },
    }

    public override readonly query = {
        runs: {
            queryKey: ['runs'] as const,
            queryFn:  () => this.actions.run.list(RUNS_SHOWN),
        },
    }

    public override cleanup(): void {
        this.setState({
            runs: {},
        })
    }
}

export const ForecasterSDK = SDK.get<ForecasterSDKImpl>('Forecaster')

export namespace ForecasterSDK {

    export type State = {
        runs: Record<Forecaster.Run.Id, Forecaster.Run>
    }

    export type Actions = ForecasterActions
}
