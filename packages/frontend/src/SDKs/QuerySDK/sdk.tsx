import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isAxiosError, isCancel } from 'axios'
import { SDK } from '../SDKManager'

const DEFAULT_STALE_TIME = 30_000
const MAX_QUERY_RETRIES = 1
// A gateway between us and the server failed — the server may not have seen the request.
const RETRYABLE_STATUSES = new Set([502, 504])

/** The one QueryClient (Quarry's QuerySDK): every SDK's queries live in it. */
@SDK('Query')
export class QuerySDKImpl {

    public readonly client = new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: DEFAULT_STALE_TIME,
                // Only transient failures: no response at all, or a gateway error. Any other status is the server's answer.
                retry: (failureCount, error) => {
                    if (failureCount >= MAX_QUERY_RETRIES)
                        return false

                    if (!isAxiosError(error) || isCancel(error))
                        return false

                    const status = error.response?.status

                    return status === undefined || RETRYABLE_STATUSES.has(status)
                },
            },
        },
    })

    public cleanup(): void {
        void this.client.cancelQueries()
        this.client.clear()
    }

    public Provider = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={this.client}>
            {children}
        </QueryClientProvider>
    )
}

export const QuerySDK = SDK.get<QuerySDKImpl>('Query')
