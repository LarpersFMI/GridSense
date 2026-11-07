import { useQueries, type UseQueryResult } from '@tanstack/react-query'
import type { StoreApi, UseBoundStore } from 'zustand'
import type { Mutate } from 'zustand/vanilla'
import { QuerySDK } from '../QuerySDK/sdk'

/** Quarry's BaseSDK: a Zustand + Immer store, the SDK's queries, and `useWith` to read both in a component. */
export abstract class BaseSDK<T_State> {

    public abstract readonly useStore: BaseSDK.Store<T_State>

    public readonly query: object = {}

    public useWith = <Selected, const Queries extends readonly BaseSDK.Query[]>(
        selector: (state: T_State) => Selected,
        queries: (query: this['query']) => Queries,
    ) => {
        const results = useQueries({ queries: [...queries(this.query)] })

        const selected = this.useStore(selector)

        return [selected, results as BaseSDK.QueryResults<Queries>] as const
    }

    public fetch = <Result>(query: BaseSDK.Query<Result>): Promise<Result> =>
        QuerySDK.client.fetchQuery(query)

    public prefetch = (query: BaseSDK.Query): Promise<void> =>
        QuerySDK.client.prefetchQuery(query)

    public invalidate = (query: Pick<BaseSDK.Query, 'queryKey'>): Promise<void> =>
        QuerySDK.client.invalidateQueries({ queryKey: query.queryKey })

    public get state() { return this.useStore.getState() }
    public get subscribe() { return this.useStore.subscribe }
    public get setState() { return this.useStore.setState }

    public abstract cleanup(): void
}

export namespace BaseSDK {

    export type Query<Result = unknown> = {
        queryKey:         readonly unknown[]
        queryFn:          () => Promise<Result>
        staleTime?:       number
        enabled?:         boolean
        refetchInterval?: number | false
    }

    export type QueryResults<Queries extends readonly Query[]> = {
        [Index in keyof Queries]: Queries[Index] extends Query<infer Result>
            ? UseQueryResult<Result, Error>
            : never
    }

    export type Store<State> = UseBoundStore<
        Mutate<StoreApi<State>, [['zustand/immer', never]]>
    >
}
